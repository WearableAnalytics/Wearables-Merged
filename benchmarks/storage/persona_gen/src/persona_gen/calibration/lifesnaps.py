"""Between-person spread and within-person dynamics from the LifeSnaps daily CSV.

Missing values are excluded. Non-wear days (no steps, or 1440 sedentary minutes) are excluded from activity statistics
and counted for wear. Study reminders likely inflated adherence, so wear figures are an upper bound for app users.
"""

import itertools
from collections import defaultdict
from csv import DictReader
from datetime import date
from math import isfinite
from pathlib import Path
from statistics import median, quantiles
from typing import Any

import numpy as np

METRICS = ("steps", "minutesAsleep", "resting_hr", "rmssd", "sedentary_minutes")
MOODS = ("TIRED", "SAD", "TENSE/ANXIOUS", "HAPPY", "RESTED/RELAXED")


def _number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if isfinite(number) else None


def _spread(values: list[float]) -> dict[str, float]:
    cuts = quantiles(values, n=10, method="inclusive") if len(values) > 1 else [values[0]] * 9
    return {
        "people": len(values),
        "p10": round(cuts[0], 3),
        "median": round(median(values), 3),
        "p90": round(cuts[-1], 3),
    }


def profile_lifesnaps_daily(path: Path) -> dict[str, Any]:
    """Profile the LifeSnaps daily CSV: spread of per-person medians and within-person dynamics (wear, step variability,
    weekend ratio, sleep spread, workout days).
    """
    people: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(encoding="utf-8", newline="") as stream:
        rows = DictReader(stream)
        if rows.fieldnames is None or not {"id", "date", *METRICS}.issubset(rows.fieldnames):
            raise ValueError("Expected the LifeSnaps daily CSV")
        for row in rows:
            if row["id"]:
                people[row["id"]].append(row)
    summary: dict[str, Any] = {}
    for metric in METRICS:
        medians = []
        days = 0
        for rows_ in people.values():
            values = [v for r in rows_ if (v := _number(r[metric])) is not None]
            days += len(values)
            if values:
                medians.append(median(values))
        if medians:
            summary[metric] = {**_spread(medians), "days": days}
    dynamics: dict[str, list[float]] = defaultdict(list)
    mood_ratio: list[float] = []
    for rows_ in people.values():
        rows_ = sorted(rows_, key=lambda r: r["date"])
        dates = [date.fromisoformat(r["date"][:10]) for r in rows_]
        span = (max(dates) - min(dates)).days + 1
        worn = {}
        for r, d in zip(rows_, dates, strict=True):
            steps, sedentary = _number(r["steps"]), _number(r["sedentary_minutes"])
            if steps and steps > 0 and (sedentary is None or sedentary < 1440):
                worn[d] = steps
        dynamics["wear_fraction"].append(len(worn) / span)
        if len(worn) < 14:
            continue
        values = np.asarray(list(worn.values()))
        dynamics["steps_cv"].append(float(values.std() / values.mean()))
        series = [worn.get(d) for d in sorted(set(dates))]
        pairs = [(a, b) for a, b in itertools.pairwise(series) if a is not None and b is not None]
        if len(pairs) > 10:
            x, y = np.asarray(pairs).T
            dynamics["steps_lag1"].append(float(np.corrcoef(x, y)[0, 1]))
        weekend = [v for d, v in worn.items() if d.weekday() >= 5]
        weekday = [v for d, v in worn.items() if d.weekday() < 5]
        if len(weekend) >= 4 and len(weekday) >= 8:
            dynamics["weekend_weekday_steps"].append(float(np.median(weekend) / np.median(weekday)))
        sleep = [v for r in rows_ if (v := _number(r["minutesAsleep"])) is not None and v > 120]
        if len(sleep) >= 10:
            dynamics["sleep_sd_minutes"].append(float(np.std(sleep)))
        workouts = sum(
            1 for r, d in zip(rows_, dates, strict=True) if d in worn and r.get("activityType", "") not in ("", "[]")
        )
        dynamics["workout_day_share"].append(workouts / len(worn))
        low = [
            worn[d]
            for r, d in zip(rows_, dates, strict=True)
            if d in worn and any(r.get(m) == "1.0" for m in ("TIRED", "SAD"))
        ]
        if len(low) >= 3:
            mood_ratio.append(float(np.median(low) / np.median(values)))
    if mood_ratio:
        dynamics["steps_on_tired_or_sad_days_ratio"] = mood_ratio
    return {
        "version": 2,
        "origin": "real-derived",
        "metrics": summary,
        "dynamics": {k: _spread(v) for k, v in dynamics.items() if v},
    }


def lifesnaps_overlay(profile: dict[str, Any]) -> dict[str, Any]:
    metrics = profile["metrics"]
    spread: dict[str, Any] = {
        "source": "calibrated: LifeSnaps daily CSV, p10/p90 of per-person medians (missing days excluded)"
    }
    if "steps" in metrics:
        spread["steps_p10_p90"] = [round(metrics["steps"]["p10"]), round(metrics["steps"]["p90"])]
    if "minutesAsleep" in metrics:
        spread["sleep_minutes_p10_p90"] = [
            round(metrics["minutesAsleep"]["p10"]),
            round(metrics["minutesAsleep"]["p90"]),
        ]
    if "resting_hr" in metrics:
        spread["resting_hr_p10_p90"] = [round(metrics["resting_hr"]["p10"], 1), round(metrics["resting_hr"]["p90"], 1)]
    dynamics = {"source": "calibrated: LifeSnaps daily CSV, within-person dynamics (median and p10/p90 across people)"}
    for key, value in profile.get("dynamics", {}).items():
        dynamics[key] = [value["p10"], value["median"], value["p90"]]
    return {
        "meta": {"target": "references", "version": "calibration:lifesnaps"},
        "spread": spread,
        "dynamics": dynamics,
    }
