"""UTC instants as float seconds, timezone timelines and local-day helpers.

Internally all instants are POSIX seconds (float64, UTC). Local wall-clock meaning comes
from a persona's timezone timeline, which changes with travel and follows real DST rules
through ``zoneinfo``. Outputs store UTC plus the UTC offset in effect at that instant.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np

DAY = 86_400.0
HOUR = 3_600.0
MINUTE = 60.0


def utc_seconds(day: date) -> float:
    return datetime.combine(day, time.min, UTC).timestamp()


@lru_cache(maxsize=256)
def zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


@lru_cache(maxsize=1024)
def _transitions(name: str, year: int) -> tuple[tuple[float, ...], tuple[int, ...]]:
    tz = zone(name)

    def offset(t: float) -> int:
        delta = datetime.fromtimestamp(t, tz).utcoffset()
        return int(delta.total_seconds() // 60) if delta is not None else 0

    start = datetime(year, 1, 1, tzinfo=UTC).timestamp()
    instants, offsets = [start], [offset(start)]
    previous = start
    for day in range(1, 367):
        current = start + day * DAY
        if offset(current) != offset(previous):
            low, high = previous, current
            while high - low > 1:
                middle = (low + high) / 2
                low, high = (middle, high) if offset(middle) == offset(previous) else (low, middle)
            instants.append(float(round(high)))
            offsets.append(offset(high))
        previous = current
    return tuple(instants), tuple(offsets)


def offsets_minutes(name: str, instants: np.ndarray) -> np.ndarray:
    if instants.size == 0:
        return np.zeros(0, dtype=np.int16)
    years = range(
        datetime.fromtimestamp(float(instants.min()), UTC).year,
        datetime.fromtimestamp(float(instants.max()), UTC).year + 1,
    )
    points: list[float] = []
    values: list[int] = []
    for year in years:
        p, v = _transitions(name, year)
        points.extend(p)
        values.extend(v)
    index = np.searchsorted(np.asarray(points), instants, side="right") - 1
    return np.asarray(values, dtype=np.int16)[np.clip(index, 0, None)]


@dataclass(frozen=True, slots=True)
class ZoneSpan:
    start: float
    end: float
    zone: str


class ZoneTimeline:
    def __init__(self, home: str, spans: list[ZoneSpan] | None = None) -> None:
        self.home = home
        self.spans = sorted(spans or [], key=lambda s: s.start)
        self._starts = [s.start for s in self.spans]

    def zone_at(self, instant: float) -> str:
        index = bisect_right(self._starts, instant) - 1
        if index >= 0 and instant < self.spans[index].end:
            return self.spans[index].zone
        return self.home

    def offsets(self, instants: np.ndarray) -> np.ndarray:
        result = offsets_minutes(self.home, instants)
        for span in self.spans:
            mask = (instants >= span.start) & (instants < span.end)
            if mask.any():
                result[mask] = offsets_minutes(span.zone, instants[mask])
        return result

    def local_to_utc(self, day: date, hours: float, name: str | None = None) -> float:
        """UTC instant of a wall-clock time ``hours`` after local midnight of ``day``.

        Hours may exceed 24 or be negative. Nonexistent DST times resolve with ``fold=0``.
        """
        tz = zone(name or self.home)
        wall = datetime.combine(day, time.min) + timedelta(hours=hours)
        return wall.replace(tzinfo=tz).timestamp()

    def zone_for_day(self, day: date) -> str:
        """Zone in effect at local noon of ``day``."""
        noon = self.local_to_utc(day, 12.0)
        return self.zone_at(noon)


def local_hour(instants: np.ndarray, offsets: np.ndarray) -> np.ndarray:
    return ((instants + offsets.astype(np.float64) * MINUTE) % DAY) / HOUR


def daylight_fraction_hours(day_of_year: int, latitude: float) -> tuple[float, float]:
    """Approximate local sunrise and sunset hours (solar time) for a latitude."""
    declination = 23.44 * np.sin(np.radians(360 / 365 * (day_of_year - 81)))
    x = -np.tan(np.radians(latitude)) * np.tan(np.radians(declination))
    half = float(np.degrees(np.arccos(np.clip(x, -1.0, 1.0))) / 15.0)
    return 12.0 - half, 12.0 + half
