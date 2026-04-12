from collections.abc import Iterable
from datetime import UTC, datetime


def ordered_unique[T](values: Iterable[T]) -> list[T]:
    """Return values in input order with duplicates removed."""
    return list(dict.fromkeys(values))


def to_utc(dt: datetime) -> datetime:
    """Return a UTC-aware datetime for naive or timezone-aware input."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
