"""Localhost web API and page for the demo. It only submits and reads tasks; the worker process runs them.

There is no endpoint that creates an alert_triage task from user input: /api/demo/pipeline stands in for the pipeline.
"""

from importlib.resources import files
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

from ..providers import DataSource
from ..providers.scenarios import SIGNALS
from ..settings import Settings
from ..tasks import repository, service
from ..tasks.demo import DEMO_PROMPTS
from ..tasks.model import MAX_PROMPT_CHARS
from ..tasks.registry import TaskHandler
from ..tasks.router import RouteError, route


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    submitted_by: Literal["doctor", "ds"]
    patient_id: str | None = None
    template: str | None = None
    filters: list[dict] = Field(default_factory=list, max_length=3)  # [{signal, op, z}], validated by the template
    match: Literal["any", "all"] = "any"


def create_app(
    pool: ConnectionPool, handlers: dict[str, TaskHandler], source: DataSource, settings: Settings
) -> FastAPI:
    app = FastAPI(title="Semantic Task Worker (demo)")
    page = files("llm_worker.web").joinpath("static/index.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page

    @app.get("/api/status")
    def status() -> dict:
        return {
            "model": settings.llm_model,
            "templates": sorted(handlers),
            "today": source.today.isoformat(),
            "data_source": settings.data_source,
            "signals": [{"signal": name, "unit": unit} for name, (unit, _) in SIGNALS.items()],
        }

    @app.get("/api/patients")
    def patients() -> list[dict]:
        return source.patients()

    @app.get("/api/demo/prompts")
    def demo_prompts() -> list[dict]:
        return DEMO_PROMPTS

    @app.post("/api/chat", status_code=201)
    def chat(body: ChatIn) -> dict:
        try:
            routed = route(
                body.text,
                submitted_by=body.submitted_by,
                known_patients=set(source.patient_ids()),
                patient_id=body.patient_id or None,
                template=body.template or None,
                filters=body.filters or None,
                match=body.match,
            )
        except RouteError as exc:
            raise HTTPException(400, str(exc)) from None
        with pool.connection() as conn:
            try:
                submitted = service.submit(conn, routed.request, handlers)
            except service.TaskRejected as exc:
                code = 403 if "cannot be started from" in str(exc) else 400
                raise HTTPException(code, str(exc)) from None
        return {
            "task_id": submitted.task_id,
            "template": submitted.template,
            "params": submitted.params,
            "notice": routed.notice,
        }

    @app.post("/api/demo/pipeline")
    def simulate_pipeline() -> dict:
        with pool.connection() as conn:
            created, total = service.simulate_pipeline(conn, source, handlers)
        return {"created": created, "total": total}

    @app.get("/api/tasks")
    def tasks(trigger: Literal["pipeline", "chat"] | None = None) -> list[dict]:
        with pool.connection() as conn:
            return repository.list_tasks(conn, trigger=trigger)

    @app.get("/api/tasks/{task_id}")
    def task(task_id: int) -> dict:
        with pool.connection() as conn:
            row = repository.get_task(conn, task_id)
        if row is None:
            raise HTTPException(404, f"no task {task_id}")
        return row

    @app.get("/api/notifications")
    def notifications() -> list[dict]:
        with pool.connection() as conn:
            return repository.list_notifications(conn)

    return app
