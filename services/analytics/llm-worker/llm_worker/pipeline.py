"""Batch pipeline: every stage sees all candidates of a claimed batch at once (LOTUS works on DataFrames)."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from psycopg import Connection

from .dto import AlertCandidate, EvidenceBundle, Explanation, TriageDecision
from .render import RenderedRow


@dataclass(frozen=True)
class Event:
    """One row of the queue table, as claimed. `to_candidate()` turns it into the DTO the stages use."""

    event_id: int
    patient_id: str
    night_date: date
    reasons: str | None
    red_flag: bool
    features: dict[str, Any]
    attempts: int

    def to_candidate(self) -> AlertCandidate:
        reasons = [r.strip() for r in (self.reasons or "").split(",") if r.strip()]
        return AlertCandidate(
            candidate_id=self.event_id,
            patient_id=self.patient_id,
            night_date=self.night_date,
            trigger_reasons=reasons,
            red_flag=self.red_flag,
            l2_score=self.features.get("l2_score"),
            sync_batch_id=self.features.get("sync_batch_id"),
        )


@dataclass
class Context:
    event: Event
    bundle: EvidenceBundle | None = None
    rendered: RenderedRow | None = None
    decision: TriageDecision | None = None
    explained: Explanation | None = None
    result: dict[str, Any] = field(default_factory=dict)
    explanation: str | None = None
    notify: bool = True  # only a `suppress` decision holds the notification back
    stop: bool = False  # this candidate is done; later stages skip it
    error: str | None = None  # this candidate failed; it is retried on its own


class Stage(Protocol):
    name: str

    def run(self, batch: list[Context], conn: Connection | None) -> list[Any]: ...


def run_pipeline(events: Iterable[Event], stages: Iterable[Stage], conn: Connection | None) -> list[Context]:
    ctxs = [Context(event) for event in events]
    for stage in stages:
        active = [ctx for ctx in ctxs if not ctx.stop and ctx.error is None]
        if not active:
            break
        outputs = stage.run(active, conn)
        if len(outputs) != len(active):
            raise RuntimeError(f"stage {stage.name} returned {len(outputs)} outputs for {len(active)} candidates")
        for ctx, output in zip(active, outputs, strict=True):
            ctx.result[stage.name] = output
    return ctxs
