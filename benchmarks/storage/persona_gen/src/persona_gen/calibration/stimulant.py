"""Estimate a stimulant's daytime heart-rate effect from an export and a dose log.

Compares low-motion daytime heart rate (10:00-17:00 local, outside workouts, away from
step bursts) on dose days with skip days inside the log's date range. The result is an
overlay trait for the anchor twin; the population keeps its conservative default.
"""

# TODO: Use more relistic timings and dosage curves + model patient hr reponse variablitiy
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..persona.sampler import load_dose_log
from ..sources.healthkit_xml import HK, export_files, family, xml_entries


def dose_effect(
    archive: Path, dose_log: Path, *, wearable: str = "apple_watch", hours: tuple[float, float] = (10.0, 17.0)
) -> dict[str, Any]:
    """Difference in median low-motion daytime heart rate between dose days and skip days in the log's date range,
    with a bootstrap interval.
    """
    log = load_dose_log(dose_log)
    if not log:
        raise ValueError("Empty dose log")
    first, last = min(log), max(log)
    by_day: dict[date, list[tuple[float, float]]] = defaultdict(list)
    busy: list[tuple[float, float]] = []
    for kind, _, stream in export_files(archive):
        if kind != "health-xml":
            continue
        for entry in xml_entries(stream):
            if entry.tag == "Workout" and (s := entry.get("startDate")) and (e := entry.get("endDate")):
                busy.append((datetime.fromisoformat(s).timestamp(), datetime.fromisoformat(e).timestamp() + 600))
                continue
            if entry.tag != "Record":
                continue
            metric = entry.get("type")
            start = entry.get("startDate")
            if not start or family(entry.get("sourceName", ""), entry.get("device")) != wearable:
                continue
            local = datetime.fromisoformat(start)
            if metric == HK + "StepCount" and (end := entry.get("endDate")) and entry.get("value"):
                minutes = max((datetime.fromisoformat(end) - local).total_seconds() / 60, 0.1)
                if float(entry.get("value", "0")) / minutes > 30:
                    busy.append((local.timestamp() - 300, datetime.fromisoformat(end).timestamp() + 300))
            elif metric == HK + "HeartRate" and first <= local.date() <= last:
                hour = local.hour + local.minute / 60
                if hours[0] <= hour < hours[1]:
                    by_day[local.date()].append((local.timestamp(), float(entry.get("value", "nan"))))
    busy.sort()
    starts = np.asarray([b[0] for b in busy])
    ends = np.asarray([b[1] for b in busy])
    day_means: dict[date, float] = {}
    for day, samples in by_day.items():
        t = np.asarray([s[0] for s in samples])
        v = np.asarray([s[1] for s in samples])
        k = np.searchsorted(starts, t, side="right") - 1
        moving = (k >= 0) & (t < ends[np.clip(k, 0, None)]) if starts.size else np.zeros(t.size, dtype=bool)
        v = v[~moving & np.isfinite(v)]
        if v.size >= 20:
            day_means[day] = float(np.median(v))
    dose = [v for d, v in day_means.items() if d in log]
    skip = [v for d, v in day_means.items() if d not in log]
    result: dict[str, Any] = {
        "dose_days": len(dose),
        "skip_days": len(skip),
        "range": [first.isoformat(), last.isoformat()],
    }
    if len(dose) >= 5 and len(skip) >= 5:
        rng = np.random.default_rng(0)
        diffs = [np.median(rng.choice(dose, len(dose))) - np.median(rng.choice(skip, len(skip))) for _ in range(2000)]
        result.update(
            {
                "awake_hr_delta": round(float(np.median(dose) - np.median(skip)), 2),
                "ci95": [round(float(np.quantile(diffs, 0.025)), 2), round(float(np.quantile(diffs, 0.975)), 2)],
            }
        )
    return result


def dose_overlay(effect: dict[str, Any], anchor: str, dose_log: Path) -> dict[str, Any]:
    traits: dict[str, float] = {}
    if "awake_hr_delta" in effect:
        traits["stimulant_awake_hr_delta"] = max(0.0, float(effect["awake_hr_delta"]))
    return {
        "meta": {"target": "cohorts", "version": "calibration:dose-log"},
        "anchors": {
            "profiles": {
                anchor: {
                    "source": (
                        f"calibrated: dose days vs skip days from the owner's log "
                        f"({effect['dose_days']} vs {effect['skip_days']} days)"
                    ),
                    "dose_log": str(dose_log),
                    "traits": traits,
                }
            }
        },
    }
