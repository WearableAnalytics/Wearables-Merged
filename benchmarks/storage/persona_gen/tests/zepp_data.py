"""A small synthetic export in the Kaggle Apple Health layout, with the structure the Zepp fit reads."""

import csv
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from persona_gen.sources.raw import KAGGLE_COLUMNS

ZONE = timezone(timedelta(hours=5, minutes=30))


def _stamp(moment: datetime) -> list[str]:
    return [moment.date().isoformat(), moment.strftime("%I:%M:%S %p"), moment.strftime("%p"), "+0530"]


def write_zepp_csv(path: Path, *, days: int = 16, first: datetime | None = None) -> Path:
    """HR every 60 s (59 s records), 5-minute bursts every 3 s on half the days, 599 s step records and
    minute-aligned sleep stages, all written one to a few days late."""
    rng = random.Random(7)
    first = first or datetime(2024, 6, 1, tzinfo=ZONE)

    def row(kind: str, unit: str, start: datetime, end: datetime, value: str, lag: float) -> list[str]:
        return [kind, "Zepp", "1", unit, *_stamp(end + timedelta(seconds=lag)), *_stamp(start), *_stamp(end), value, ""]

    def lag() -> float:
        return math.exp(rng.gauss(11.5, 1.0)) if rng.random() < 0.7 else math.exp(rng.gauss(9.0, 1.0))

    with path.open("w", newline="", encoding="utf-8") as stream:
        out = csv.writer(stream)
        out.writerow(KAGGLE_COLUMNS)
        for day in range(days):
            midnight = first + timedelta(days=day)
            burst = day % 2 == 0
            for minute in range(8 * 60, 22 * 60):
                start = midnight + timedelta(minutes=minute)
                if burst and 12 * 60 <= minute < 12 * 60 + 5:
                    for k in range(20):
                        t = start + timedelta(seconds=3 * k)
                        out.writerow(row("HeartRate", "count/min", t, t, str(80 + k % 7), lag()))
                    continue
                out.writerow(row("HeartRate", "count/min", start, start + timedelta(seconds=59), "70", lag()))
            for minute in range(8 * 60, 22 * 60, 10):
                start = midnight + timedelta(minutes=minute)
                out.writerow(row("StepCount", "count", start, start + timedelta(seconds=599), "120", lag()))
            bed = midnight + timedelta(hours=23)
            out.writerow(
                row("SleepAnalysis", "", bed, bed + timedelta(hours=8), "HKCategoryValueSleepAnalysisInBed", 9e4)
            )
            cursor = bed
            stages = ["Core", "Deep", "Core", "REM", "Awake"] * 5
            for stage in stages:
                seconds = 59 if stage == "Awake" else 719
                value = f"HKCategoryValueSleepAnalysis{'Awake' if stage == 'Awake' else 'Asleep' + stage}"
                out.writerow(row("SleepAnalysis", "", cursor, cursor + timedelta(seconds=seconds), value, 9e4))
                cursor += timedelta(seconds=seconds + 1)
    return path
