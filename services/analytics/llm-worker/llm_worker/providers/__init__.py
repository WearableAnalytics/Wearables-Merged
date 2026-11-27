"""Where the evidence comes from. The rest of the worker only sees these interfaces and the DTOs (plan §4.1).

Two implementations with the same contract (tests/test_pg_source.py):
- `providers.pg`: the `vitals` / `patient_context` serving tables in PostgreSQL (what the worker and the demo use);
- `providers.scenarios`: the YAML fixtures directly (unit tests without a database, and the loader's input).
"""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from typing import Literal, Protocol

from ..dto import AlertCandidate, ContextItem, DescriptiveContext, NumericCondition, NumericContext

# Text written before this moment may explain the night; anything later is the future and must never be read.
AS_OF_TIME = time(12, 0)

Match = Literal["any", "all"]


def as_of_for(night_date: date) -> datetime:
    """The night of 3/14 ends on the morning of 3/15; context is read up to 3/15 12:00."""
    return datetime.combine(night_date + timedelta(days=1), AS_OF_TIME)


class NumericContextProvider(Protocol):
    def get(self, patient_id: str, night_date: date) -> NumericContext: ...


class DescriptiveContextProvider(Protocol):
    def get(self, patient_id: str, night_date: date, as_of: datetime, max_items: int = 20) -> DescriptiveContext: ...


class DataSource(Protocol):
    """Everything the task handlers read: per patient-night evidence, the patient list, and exact numeric queries."""

    numeric: NumericContextProvider
    descriptive: DescriptiveContextProvider

    @property
    def today(self) -> date: ...  # the latest night in the data

    def patient_ids(self) -> list[str]: ...

    def has_patient(self, patient_id: str) -> bool: ...

    def patients(self) -> list[dict]: ...

    def all_candidates(self) -> list[AlertCandidate]: ...

    def nights_matching(
        self, conditions: list[NumericCondition], match: Match, since_days: int, patient_id: str | None = None
    ) -> list[tuple[str, date]]: ...


def visible_items(
    items: Iterable[ContextItem], night_date: date, as_of: datetime, max_items: int
) -> tuple[list[ContextItem], int]:
    """Context written before `as_of`, undated first, then the most recent dated ones. Returns (items, truncated)."""
    visible = [item for item in items if item.ts is None or item.ts < as_of]
    visible.sort(key=lambda item: (item.ts is not None, item.ts or datetime.min))
    undated = [item for item in visible if item.ts is None]
    dated = [item for item in visible if item.ts is not None]
    keep = max(max_items - len(undated), 0)
    kept = undated + dated[len(dated) - keep :] if keep else undated
    out = [
        item.model_copy(update={"days_before": None if item.ts is None else (night_date - item.ts.date()).days})
        for item in kept
    ]
    return out, len(visible) - len(out)


def condition_holds(z_by_signal: dict[str, float | None], conditions: list[NumericCondition], match: Match) -> bool:
    results = [c.holds(z_by_signal.get(c.signal)) for c in conditions]
    return all(results) if match == "all" else any(results)
