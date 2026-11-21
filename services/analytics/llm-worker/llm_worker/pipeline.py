from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

from psycopg import Connection


@dataclass(frozen=True)
class Event:
    event_id: int
    patient_id: str
    night_date: date
    reasons: str | None
    red_flag: bool
    features: dict[str, Any]
    attempts: int


@dataclass
class Context:
    event: Event
    patient: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    explanation: str | None = None
    stop: bool = False


class Stage(Protocol):
    name: str

    def run(self, ctx: Context, conn: Connection) -> Any: ...


def run_pipeline(event: Event, stages: Iterable[Stage], conn: Connection | None) -> Context:
    ctx = Context(event)
    for stage in stages:
        ctx.result[stage.name] = stage.run(ctx, conn)
        if ctx.stop:
            break
    return ctx
