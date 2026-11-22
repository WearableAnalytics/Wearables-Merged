"""Where the evidence comes from. Only these two interfaces are visible to the rest of the worker (plan §4.1).

Today both are backed by scenario fixtures (`providers.scenarios`). Later implementations, without touching the
stages: `vitals` serving tables in PostgreSQL (numbers), `patient_context` / db_lord / FHIR (text), ClickHouse.
"""

from datetime import date, datetime, time, timedelta
from typing import Protocol

from ..dto import DescriptiveContext, NumericContext

# Text written before this moment may explain the night; anything later is the future and must never be read.
AS_OF_TIME = time(12, 0)


def as_of_for(night_date: date) -> datetime:
    """The night of 3/14 ends on the morning of 3/15; context is read up to 3/15 12:00."""
    return datetime.combine(night_date + timedelta(days=1), AS_OF_TIME)


class NumericContextProvider(Protocol):
    def get(self, patient_id: str, night_date: date) -> NumericContext: ...


class DescriptiveContextProvider(Protocol):
    def get(self, patient_id: str, night_date: date, as_of: datetime, max_items: int = 20) -> DescriptiveContext: ...
