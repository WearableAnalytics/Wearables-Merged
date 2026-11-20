"""Profile device behaviour in an Apple Health export (streamed; multi-GB safe).

Per source family (apple_watch, iphone, garmin, other apps) and HealthKit type:
records per day, inter-sample gaps split by context (workout, sleep, still, moving),
duration and write-delay (creationDate - endDate) quantiles, clock-grid detection and
long-gap counts. Heart-rate gaps are fitted with lognormal mixtures so the generator
reproduces the mixture (background cadence, dense workout mode, dropouts).
"""

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..sources.healthkit_xml import HK, HKC, export_files, family, parse_date, xml_entries
from ..util import fit_lognormal_mixture

QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)


@dataclass
class _Series:
    starts: list[float] = field(default_factory=list)
    ends: list[float] = field(default_factory=list)
    lags: list[float] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    categories: Counter[str] = field(default_factory=Counter)
    hardware: Counter[str] = field(default_factory=Counter)
    record_hardware: list[str] = field(default_factory=list)  # heart rate only


def _windows(pairs: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    pairs.sort()
    merged: list[list[float]] = []
    for a, b in pairs:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    arr = np.asarray(merged) if merged else np.zeros((0, 2))
    return arr[:, 0], arr[:, 1]


def _inside(window: tuple[np.ndarray, np.ndarray], t: np.ndarray) -> np.ndarray:
    starts, ends = window
    if not len(starts):
        return np.zeros(t.shape, dtype=bool)
    k = np.searchsorted(starts, t, side="right") - 1
    return (k >= 0) & (t < ends[np.clip(k, 0, None)])


def _quantiles(values: Iterable[float]) -> list[float] | None:
    arr = np.asarray(list(values), dtype=float)
    if not arr.size:
        return None
    return [round(float(np.quantile(arr, q)), 3) for q in QUANTILES]


def _grid(gaps: np.ndarray) -> dict[str, float] | None:
    if gaps.size < 50:
        return None
    rounded = np.round(gaps)
    values, counts = np.unique(rounded, return_counts=True)
    mode = float(values[np.argmax(counts)])
    share = float(counts.max() / gaps.size)
    return {"mode_seconds": mode, "share_at_mode": round(share, 4)}


def profile_export(archive: Path, *, holdout_start: datetime | None = None) -> dict[str, Any]:
    series: dict[tuple[str, str], _Series] = defaultdict(_Series)
    sleep: list[tuple[float, float]] = []
    workouts: list[tuple[float, float]] = []
    moving: list[tuple[float, float]] = []
    hardware_timeline: dict[str, dict[str, list[float]]] = defaultdict(dict)
    daily_steps: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))
    defaultdict(list)  # (local start hour-ish, minutes)
    sleep_local: dict[str, list[tuple[float, float, int]]] = defaultdict(list)
    found = False
    ecg_dates: list[str] = []
    for kind, member, stream in export_files(archive):
        if kind == "ecg":
            if m := re.search(r"(\d{4}-\d{2}-\d{2})", member):
                ecg_dates.append(m.group(1))
            continue
        if kind != "health-xml":
            continue
        found = True
        for entry in xml_entries(stream):
            if entry.tag not in ("Record", "Workout"):
                continue
            source = entry.get("sourceName", "unknown")
            fam = family(source, entry.get("device"))
            metric = entry.get("type") or "Workout:" + entry.get("workoutActivityType", "")
            started, ended, created = entry.get("startDate"), entry.get("endDate"), entry.get("creationDate")
            if not started:
                continue
            a = parse_date(started).timestamp()
            b = parse_date(ended).timestamp() if ended else a
            s = series[(fam, metric)]
            s.starts.append(a)
            s.ends.append(b)
            if created:
                s.lags.append(parse_date(created).timestamp() - b)
            value = entry.get("value")
            if value is not None:
                try:
                    s.values.append(float(value))
                except ValueError:
                    s.categories[value] += 1
            hw = ""
            if (device := entry.get("device")) and (m := re.search(r"hardware:([^,>]+)", device)):
                hw = m.group(1).strip()
                s.hardware[hw] += 1
                span = hardware_timeline[fam].setdefault(hw, [a, a])
                span[0], span[1] = min(span[0], a), max(span[1], a)
            if metric == HK + "HeartRate":
                s.record_hardware.append(hw)
            if metric == HK + "StepCount" and value:
                local_day = datetime.fromisoformat(started).date().isoformat()
                daily_steps[fam][local_day] += float(value)
            if (
                metric == HKC + "SleepAnalysis"
                and (value or "").startswith("HKCategoryValueSleepAnalysisAsleep")
                and b > a
            ):
                offset = datetime.fromisoformat(started).utcoffset()
                sleep_local[fam].append((a, b, int(offset.total_seconds()) if offset else 0))
            if entry.tag == "Workout" and b > a:
                workouts.append((a, b))
            elif (
                metric == HKC + "SleepAnalysis"
                and (value or "").startswith("HKCategoryValueSleepAnalysisAsleep")
                and b > a
            ):
                sleep.append((a, b))
            elif (
                metric == HK + "StepCount"
                and fam == "apple_watch"
                and b > a
                and value
                and float(value) / max((b - a) / 60, 1e-6) >= 60
            ):
                moving.append((a, b))
    if not found:
        raise ValueError(f"No Apple Health export XML found in {archive.name}")
    sleep_w, workout_w, moving_w = _windows(sleep), _windows(workouts), _windows(moving)
    cutoff = holdout_start.timestamp() if holdout_start else None
    sources: dict[str, dict[str, Any]] = defaultdict(dict)
    for (fam, metric), s in sorted(series.items()):
        starts = np.asarray(s.starts)
        order = np.argsort(starts)
        starts = starts[order]
        ends = np.asarray(s.ends)[order]
        days = max(1.0, (starts[-1] - starts[0]) / 86400) if starts.size else 1.0
        entry: dict[str, Any] = {
            "records": int(starts.size),
            "per_day": round(starts.size / days, 3),
            "first": datetime.fromtimestamp(float(starts[0])).date().isoformat(),
            "last": datetime.fromtimestamp(float(starts[-1])).date().isoformat(),
            "duration_quantiles": _quantiles(ends - starts),
            "lag_quantiles": _quantiles(s.lags),
            "value_quantiles": _quantiles(s.values),
            "categories": dict(s.categories.most_common(8)),
            "hardware": dict(s.hardware.most_common(6)),
            "active_days": int(np.unique(np.floor(starts / 86400)).size),
            "span_days": round(days, 1),
        }
        gaps = np.diff(starts)
        positive = gaps > 0
        entry["gap_quantiles"] = _quantiles(gaps[positive])
        entry["long_gaps"] = {
            "over_1h": int((gaps > 3600).sum()),
            "over_6h": int((gaps > 6 * 3600).sum()),
            "over_1d": int((gaps > 86400).sum()),
            "over_3d": int((gaps > 3 * 86400).sum()),
        }
        entry["grid"] = _grid(gaps[positive & (gaps <= 3600)])
        if metric == HK + "HeartRate" and starts.size > 100:
            prev, curr = starts[:-1], starts[1:]
            ok = positive & (gaps <= 900)
            ctx = np.where(
                _inside(workout_w, prev) & _inside(workout_w, curr),
                "workout",
                np.where(
                    _inside(sleep_w, prev) & _inside(sleep_w, curr),
                    "sleep",
                    np.where(_inside(moving_w, prev) | _inside(moving_w, curr), "moving", "still"),
                ),
            )
            periods = {"fit": np.ones(len(prev), dtype=bool)}
            if cutoff is not None:
                periods = {"fit": prev < cutoff, "holdout": prev >= cutoff}
            hardware = (
                np.asarray(s.record_hardware, dtype=object)[order] if len(s.record_hardware) == starts.size else None
            )
            if hardware is not None:
                same = hardware[:-1] == hardware[1:]
                for hw in sorted(set(hardware.tolist()) - {""}):
                    periods[f"hardware:{hw}"] = same & (hardware[:-1] == hw)
            entry["cadence"] = {}
            for period, mask in periods.items():
                entry["cadence"][period] = {}
                for c in ("workout", "sleep", "still", "moving"):
                    g = gaps[ok & mask & (ctx == c)]
                    if g.size >= 20:
                        entry["cadence"][period][c] = {
                            "count": int(g.size),
                            "quantiles": _quantiles(g),
                            "mixture": fit_lognormal_mixture(g),
                        }
            seconds = np.mod(starts, 60)
            entry["second_of_minute_uniformity"] = round(
                float(np.histogram(seconds, bins=12, range=(0, 60))[0].std() / max(1, starts.size / 12)), 4
            )
        sources[fam][metric] = entry
    habits: dict[str, Any] = {}
    for fam, days in daily_steps.items():
        totals = np.asarray(list(days.values()))
        habits.setdefault(fam, {})["daily_steps_quantiles"] = _quantiles(totals[totals > 0])
    for fam, rows in sleep_local.items():
        rows.sort()
        sessions: list[list[float]] = []
        for a, b, off in rows:
            if sessions and a - sessions[-1][1] < 3 * 3600:
                sessions[-1][1] = max(sessions[-1][1], b)
                sessions[-1][2] += b - a
            else:
                sessions.append([a, b, b - a, off])
        main = [x for x in sessions if x[2] >= 3 * 3600]
        if main:
            mids = [(((x[0] + x[1]) / 2 + x[3]) % 86400) / 3600 for x in main]
            mids = [m - 24 if m > 15 else m for m in mids]
            habits.setdefault(fam, {}).update(
                {
                    "asleep_hours_quantiles": _quantiles([x[2] / 3600 for x in main]),
                    "midsleep_hour_quantiles": _quantiles(mids),
                    "nights": len(main),
                    "utc_offset_minutes": int(Counter(x[3] for x in main).most_common(1)[0][0] // 60),
                }
            )
    return {
        "version": 2,
        "origin": "real-derived",
        "archive": archive.name,
        "habits": habits,
        "ecg": {
            "recordings": len(ecg_dates),
            "first": min(ecg_dates, default=None),
            "last": max(ecg_dates, default=None),
        },
        "sources": dict(sources),
        "hardware_timeline": {
            f: {
                hw: [datetime.fromtimestamp(a).date().isoformat(), datetime.fromtimestamp(b).date().isoformat()]
                for hw, (a, b) in hw_map.items()
            }
            for f, hw_map in hardware_timeline.items()
        },
    }


def _toml_mixture(entry: dict[str, Any], period: str = "fit") -> dict[str, list[list[float]]]:
    if period not in entry.get("cadence", {}):
        period = "fit"
    cadence = entry.get("cadence", {}).get(period, {})
    return {c: v["mixture"] for c, v in cadence.items()}


def write_overlays(
    profiles: dict[str, dict[str, Any]], out_dir: Path, *, model_for_family: dict[str, str], period: str = "fit"
) -> list[Path]:
    import tomli_w

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, profile in profiles.items():
        overlay: dict[str, Any] = {
            "meta": {"target": "devices", "version": f"calibration:{profile['archive']}"},
            "models": {},
        }
        for fam, model in model_for_family.items():
            hr = profile["sources"].get(fam, {}).get(HK + "HeartRate")
            if not hr or "cadence" not in hr:
                continue
            grid = hr.get("grid") or {}
            if grid.get("share_at_mode", 0) > 0.9:
                spec: dict[str, Any] = {"mode": "samples", "grid_seconds": grid["mode_seconds"], "quality": True}
            else:
                spec = {"mode": "samples", "cadence": _toml_mixture(hr, period), "quality": True}
            overlay["models"][model] = {
                "metrics": {
                    "source": f"calibrated: fitted locally from {profile['archive']} ({fam}, {period})",
                    "heart_rate": spec,
                }
            }
        path = out_dir / f"devices-{name}.toml"
        path.write_text(tomli_w.dumps(overlay), encoding="utf-8")
        written.append(path)
    return written


def anchor_overlay(profiles: dict[str, tuple[dict[str, Any], str]]) -> dict[str, Any]:
    """Build a cohorts overlay containing personal anchor traits.

    ``profiles`` maps anchor name -> (export profile, wearable family).
    """

    def median(entry: dict[str, Any] | None) -> float | None:
        return entry["value_quantiles"][2] if entry and entry.get("value_quantiles") else None

    overlay: dict[str, Any] = {
        "meta": {"target": "cohorts", "version": "calibration:anchors"},
        "anchors": {"profiles": {}},
    }
    for name, (profile, fam) in profiles.items():
        sources = profile["sources"]
        wearable = sources.get(fam, {})
        traits: dict[str, float] = {}
        if (v := median(wearable.get(HK + "RestingHeartRate"))) is not None:
            traits["rhr"] = v
        if (v := median(wearable.get(HK + "VO2Max"))) is not None:
            traits["vo2max"] = v
        if (v := median(wearable.get(HK + "HeartRateVariabilitySDNN"))) is not None:
            traits["ln_rmssd"] = round(math.log(v) - 0.25, 3)  # SDNN/RMSSD ~1.3 (assumption)
        for fam_any in sources.values():
            if (v := median(fam_any.get(HK + "BodyMass"))) is not None:
                traits.setdefault("weight_kg", v)
            if (v := median(fam_any.get(HK + "Height"))) is not None:
                traits.setdefault("height_cm", v)
        habit = profile.get("habits", {}).get(fam, {})
        hr = wearable.get(HK + "HeartRate")
        if hr and hr.get("span_days"):
            traits["adherence"] = round(min(0.995, hr["active_days"] / hr["span_days"]), 3)
            if habit.get("nights"):
                traits["night_wear"] = round(min(0.995, habit["nights"] / max(1, hr["active_days"])), 3)
        if habit.get("midsleep_hour_quantiles"):
            traits["midsleep_hour"] = habit["midsleep_hour_quantiles"][2]
        if habit.get("daily_steps_quantiles"):
            traits["activity_level"] = round(min(1.0, max(0.05, (habit["daily_steps_quantiles"][2] - 3000) / 12000)), 3)
            traits["daily_steps_target"] = habit["daily_steps_quantiles"][2]
        if habit.get("asleep_hours_quantiles"):
            traits["sleep_need_hours"] = round(habit["asleep_hours_quantiles"][2] + 0.4, 2)
            traits["asleep_hours_target"] = habit["asleep_hours_quantiles"][2]
        ecg = profile.get("ecg", {})
        if ecg.get("recordings") and ecg.get("first") and ecg.get("last"):
            weeks = max(1.0, (datetime.fromisoformat(ecg["last"]) - datetime.fromisoformat(ecg["first"])).days / 7)
            traits["ecg_per_week"] = round(ecg["recordings"] / weeks, 3)
        entry: dict[str, Any] = {"source": f"calibrated: profiled locally from {profile['archive']}", "traits": traits}
        timeline = profile.get("hardware_timeline", {}).get(fam, {})
        if fam == "apple_watch" and len(timeline) > 1:
            ordered = sorted(timeline.items(), key=lambda kv: kv[1][0])
            entry["wearable"] = "apple_watch_legacy"
            entry["upgrades"] = [[span[0], "apple_watch"] for _, span in ordered[1:]]
        overlay["anchors"]["profiles"][name] = entry
    return overlay


def calibrate(
    exports: dict[str, tuple[Path, str]], out_dir: Path, *, holdout_start: datetime | None = None
) -> dict[str, Path]:
    """Profile exports and write calibration overlays.

    ``exports`` maps anchor name -> (archive path, wearable family), for example
    ``{"person_b": (Path(".local/personal/<name>/export.tar.xz"), "apple_watch")}``.
    Writes ``<name>.profile.json``, ``devices-<name>.toml`` and ``anchors.toml`` to ``out_dir``.
    The anchor overlay holds personal values.
    """
    import json

    import tomli_w

    out_dir.mkdir(parents=True, exist_ok=True)
    profiles: dict[str, dict[str, Any]] = {}
    written: dict[str, Path] = {}
    for name, (archive, _) in exports.items():
        profiles[name] = profile_export(archive, holdout_start=holdout_start)
        path = out_dir / f"{name}.profile.json"
        path.write_text(json.dumps(profiles[name], indent=1, sort_keys=True), encoding="utf-8")
        written[f"profile:{name}"] = path
    # Each Apple Watch generation gets the cadence fitted on its own hardware's records.
    models = {
        "apple_watch": [("apple_watch", "hardware:Watch7"), ("apple_watch_legacy", "hardware:Watch6")],
        "garmin": [("garmin", "fit")],
    }
    for name, (_, fam) in exports.items():
        for model, period in models.get(fam, []):
            for path in write_overlays(
                {f"{name}-{model}": profiles[name]}, out_dir, model_for_family={fam: model}, period=period
            ):
                written[path.stem] = path
    anchors = anchor_overlay({name: (profiles[name], fam) for name, (_, fam) in exports.items()})
    path = out_dir / "anchors.toml"
    path.write_text(tomli_w.dumps(anchors), encoding="utf-8")
    written["anchors"] = path
    return written


__all__ = ["anchor_overlay", "calibrate", "family", "fit_lognormal_mixture", "profile_export", "write_overlays"]


def daily_series(archive: Path, wearable: str, start: datetime, end: datetime) -> dict[str, dict[str, float]]:
    """Summarize heart-rate record counts, wearable steps and asleep hours by local date."""
    days: dict[str, dict[str, float]] = defaultdict(lambda: {"hr_records": 0.0, "steps": 0.0, "asleep_hours": 0.0})
    lo, hi = start.timestamp(), end.timestamp()
    for kind, _, stream in export_files(archive):
        if kind != "health-xml":
            continue
        for entry in xml_entries(stream):
            if entry.tag != "Record" or not (started := entry.get("startDate")):
                continue
            if family(entry.get("sourceName", ""), entry.get("device")) != wearable:
                continue
            local = datetime.fromisoformat(started)
            if not lo <= local.timestamp() < hi:
                continue
            day = local.date().isoformat()
            metric = entry.get("type")
            if metric == HK + "HeartRate":
                days[day]["hr_records"] += 1
            elif metric == HK + "StepCount":
                days[day]["steps"] += float(entry.get("value", "0"))
            elif metric == HKC + "SleepAnalysis" and entry.get("value", "").startswith(
                "HKCategoryValueSleepAnalysisAsleep"
            ):
                ended = datetime.fromisoformat(entry.get("endDate", started))
                wake_day = ended.date().isoformat()
                days[wake_day]["asleep_hours"] += (ended - local).total_seconds() / 3600
    return dict(sorted(days.items()))
