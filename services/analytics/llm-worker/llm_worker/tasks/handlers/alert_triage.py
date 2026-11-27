"""alert_triage: a suspicious event from the pipeline. The only template that may notify a clinician.

It wraps the existing batch pipeline (evidence -> L3 sem_filter -> L4 sem_map) unchanged.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from ...pipeline import Event, run_pipeline
from ...render import RENDER_VERSION
from ...stages import triage_stages
from ..model import TaskOutcome, TaskRun
from ..registry import Deps, ParamsError, parse_params, register_task
from .common import evidence, recent_nights

EVIDENCE_NIGHTS = 7  # the flagged night and the six before it, shown next to the explanation


class AlertParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    night: date
    trigger_reasons: list[str] = Field(default_factory=list)
    red_flag: bool = False
    l2_score: float | None = None


@register_task
class AlertTriage:
    template = "alert_triage"
    triggers = frozenset({"pipeline"})
    priority = 0
    batch_size = 8

    def __init__(self, deps: Deps):
        self.source = deps.source
        self.stages = triage_stages(deps.source, deps.model)

    def validate(self, params: dict) -> dict:
        p = parse_params(AlertParams, params)
        if not self.source.has_patient(p.patient_id):
            raise ParamsError(f"unknown patient {p.patient_id}")
        return p.model_dump(mode="json")

    def run(self, runs: list[TaskRun]) -> list[TaskOutcome]:
        ctxs = run_pipeline([_event(r) for r in runs], self.stages, None)
        return [self._outcome(ctx) for ctx in ctxs]

    def _outcome(self, ctx) -> TaskOutcome:
        if ctx.error is not None:
            return TaskOutcome.failed(ctx.error)
        stages = {s.name: s for s in self.stages}
        return TaskOutcome(
            answer=ctx.explanation,
            result={**ctx.result, "verdict": ctx.decision.verdict, "evidence": self._evidence(ctx)},
            notify=ctx.notify,
            model=ctx.decision.model or (ctx.explained.model if ctx.explained else None),
            spec_versions={
                "triage": stages["triage"].operator.spec.ref,
                "explain": stages["explain"].operator.spec.ref,
                "render": RENDER_VERSION,
            },
        )

    def _evidence(self, ctx) -> dict:
        """What the model saw for this night (same ids: n:rhr, c:104), plus the nights before, as data."""
        nights = recent_nights(self.source, ctx.event.patient_id, EVIDENCE_NIGHTS, end=ctx.event.night_date)
        return evidence(nights, ctx.bundle.descriptive, ids="tonight")


def _event(run: TaskRun) -> Event:
    p = AlertParams.model_validate(run.params)
    return Event(
        event_id=run.task_id,
        patient_id=p.patient_id,
        night_date=p.night,
        reasons=", ".join(p.trigger_reasons),
        red_flag=p.red_flag,
        features={"l2_score": p.l2_score},
        attempts=run.attempts,
    )
