"""Task templates behind one registry, so a new template plugs in without touching the worker.

    @register_task
    class TriageReview:            # a later PR: sem_agg over held-back alerts
        template = "triage_review"
        ...

Permissions belong to the template, not to whoever triggers it: `triggers` says who may submit it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ValidationError

from ..providers import DataSource
from ..semantic import LotusModel
from .model import TaskOutcome, TaskRun


class ParamsError(ValueError):
    pass


@dataclass(frozen=True)
class Deps:
    source: DataSource  # PostgreSQL serving tables (providers.pg) or the scenario files (providers.scenarios)
    model: LotusModel


class TaskHandler(Protocol):
    template: ClassVar[str]
    triggers: ClassVar[frozenset[str]]
    priority: ClassVar[int]  # lower runs first; the clinical path is 0
    batch_size: ClassVar[int]  # tasks of this template claimed (and sent to LOTUS) together

    def validate(self, params: dict[str, Any]) -> dict[str, Any]: ...

    def run(self, runs: list[TaskRun]) -> list[TaskOutcome]: ...


HANDLERS: dict[str, type] = {}


def register_task(cls: type) -> type:
    HANDLERS[cls.template] = cls
    return cls


def build_handlers(deps: Deps) -> dict[str, TaskHandler]:
    from . import handlers  # noqa: F401  (registers the bundled templates)

    return {name: cls(deps) for name, cls in HANDLERS.items()}


def parse_params(model: type[BaseModel], params: dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(params)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'params'}: {e['msg']}" for e in exc.errors())
        raise ParamsError(problems) from None
