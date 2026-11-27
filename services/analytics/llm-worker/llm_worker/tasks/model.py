"""A task is the unit of work. A suspicious event from the pipeline and a question from the chat are both tasks.

`params` decide which data a task reads; `prompt` only carries the meaning (the question) and never widens the scope.
"""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..dto import NumericCondition

__all__ = ["NumericCondition", "TaskOutcome", "TaskRequest", "TaskRun", "may_notify"]

Trigger = Literal["pipeline", "chat"]
MAX_PROMPT_CHARS = 1000

# Templates whose result may notify a clinician. Checked by the worker, whatever a handler returns.
NOTIFYING_TEMPLATES = frozenset({"alert_triage"})


class TaskRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    template: str
    params: dict[str, Any] = Field(default_factory=dict)
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    trigger: Trigger
    submitted_by: str
    dedup_key: str | None = None  # set for pipeline events, so the same night is enqueued once


@dataclass(frozen=True)
class TaskRun:
    """One claimed row of `tasks.task_runs`."""

    task_id: int
    template: str
    params: dict[str, Any]
    prompt: str
    trigger: str
    submitted_by: str
    attempts: int


class TaskOutcome(BaseModel):
    answer: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    notify: bool = False
    error: str | None = None  # this task failed on its own; it is retried, the rest of the batch is not
    model: str | None = None
    spec_versions: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def failed(cls, error: str) -> "TaskOutcome":
        return cls(error=error)


def may_notify(run: TaskRun) -> bool:
    return run.template in NOTIFYING_TEMPLATES and run.trigger == "pipeline"
