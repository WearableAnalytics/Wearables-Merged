"""Submitting tasks. Every entry point (pipeline, chat, CLI) goes through `submit`, so the rules live in one place."""

from dataclasses import dataclass
from typing import Any

from psycopg import Connection

from ..providers import DataSource
from . import repository
from .bridge import pipeline_requests
from .model import TaskRequest
from .registry import ParamsError, TaskHandler


class TaskRejected(ValueError):
    pass


@dataclass(frozen=True)
class Submitted:
    task_id: int
    created: bool
    template: str
    params: dict[str, Any]


def submit(conn: Connection, request: TaskRequest, handlers: dict[str, TaskHandler]) -> Submitted:
    handler = handlers.get(request.template)
    if handler is None:
        raise TaskRejected(f"unknown template {request.template!r}; available: {sorted(handlers)}")
    if request.trigger not in handler.triggers:
        allowed = ", ".join(sorted(handler.triggers))
        raise TaskRejected(f"{request.template} cannot be started from {request.trigger} (only: {allowed})")
    try:
        params = handler.validate(request.params)
    except ParamsError as exc:
        raise TaskRejected(str(exc)) from None

    normalised = request.model_copy(update={"params": params})
    task_id, created = repository.enqueue(conn, normalised, priority=handler.priority)
    return Submitted(task_id, created, request.template, params)


def simulate_pipeline(conn: Connection, source: DataSource, handlers: dict[str, TaskHandler]) -> tuple[int, int]:
    """Stand-in for the data pipeline: one alert_triage task per flagged night (`vitals.nightly_flags`).

    Returns (created, total). Idempotent: a night already queued is not queued again.
    """
    results = [submit(conn, r, handlers) for r in pipeline_requests(source)]
    return sum(r.created for r in results), len(results)
