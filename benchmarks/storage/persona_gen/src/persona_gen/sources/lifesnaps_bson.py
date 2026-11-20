"""Per-person profiles from the LifeSnaps MongoDB dump (``fitbit.bson``, ~9.7 GB, 71 people).

The dump holds Fitbit Sense data at Fitbit Web API resolution: heart rate every 5-15 s,
steps per minute, 30-second sleep stages, nightly HRV, SpO2 and breathing rate, daily
resting HR and VO2max, and exercise logs. Timestamps are local wall clock without a zone,
so every time here is "local seconds" (wall clock read as if it were UTC).

The file is mostly grouped by participant. One skip-scan indexes each participant's byte
runs; participants are then profiled in parallel. Heart-rate and step documents (90% of
the file) are parsed on a fast path that reads only the timestamp and the value.

Profiles contain medians, quantiles and gap histograms. LifeSnaps is licensed under
CC BY 4.0 (Yfantidou et al. 2022, doi:10.1038/s41597-022-01764-x).
"""

import math
import mmap
import os
import struct
from array import array
from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..util import fit_lognormal_mixture

DAY = 86400
CONTEXTS = ("workout", "sleep", "still", "moving")
DEFAULTS_DIR = Path(__file__).resolve().parent.parent / "params" / "defaults"
MAX_GAP = 900  # seconds; longer gaps are off-wrist, not cadence (as in the Apple Health profiler)
_DETAILED = frozenset(
    {
        "Profile",
        "sleep",
        "exercise",
        "resting_heart_rate",
        "demographic_vo2_max",
        "Daily Heart Rate Variability Summary",
        "Heart Rate Variability Details",
        "Respiratory Rate Summary",
        "Daily SpO2",
    }
)

# Minimal BSON reading (maybe just use pymongo?)


def _decode(buf: bytes | memoryview, i: int, end: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    while i < end - 1:
        kind = buf[i]
        i += 1
        j = bytes(buf[i : i + 256]).index(0) + i
        key = bytes(buf[i:j]).decode()
        i = j + 1
        value: Any
        if kind == 0x01:
            value = struct.unpack_from("<d", buf, i)[0]
            i += 8
        elif kind == 0x02:
            n = struct.unpack_from("<i", buf, i)[0]
            value = bytes(buf[i + 4 : i + 3 + n]).decode("utf-8", "replace")
            i += 4 + n
        elif kind in (0x03, 0x04):
            n = struct.unpack_from("<i", buf, i)[0]
            value = _decode(buf, i + 4, i + n)
            if kind == 0x04:
                value = list(value.values())
            i += n
        elif kind == 0x05:
            n = struct.unpack_from("<i", buf, i)[0]
            value = None
            i += 5 + n
        elif kind == 0x07:
            value = bytes(buf[i : i + 12]).hex()
            i += 12
        elif kind == 0x08:
            value = bool(buf[i])
            i += 1
        elif kind == 0x09:
            value = struct.unpack_from("<q", buf, i)[0] / 1000
            i += 8
        elif kind == 0x0A:
            value = None
        elif kind == 0x10:
            value = struct.unpack_from("<i", buf, i)[0]
            i += 4
        elif kind in (0x11, 0x12):
            value = struct.unpack_from("<q", buf, i)[0]
            i += 8
        else:
            raise ValueError(f"Unsupported BSON element type {kind:#x}")
        out[key] = value
    return out


def _header(buf: bytes | memoryview, pos: int) -> tuple[str, str, int]:
    head = bytes(buf[pos : pos + 160])
    k = head.find(b"\x07id\x00")
    uid = head[k + 4 : k + 16].hex()
    t = head.find(b"\x02type\x00")
    n = struct.unpack_from("<i", head, t + 6)[0]
    return uid, head[t + 10 : t + 9 + n].decode(), pos + t + 10 + n


def _documents(path: Path, runs: list[tuple[int, int]]) -> Iterator[tuple[bytes | memoryview, int, int]]:
    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as source:
        for start, end in runs:
            with memoryview(source)[start:end] as buf:
                pos = 0
                while pos < len(buf):
                    n = struct.unpack_from("<i", buf, pos)[0]
                    if n < 5 or pos + n > len(buf) or buf[pos + n - 1] != 0:
                        raise ValueError(f"Invalid BSON document at offset {start + pos}")
                    yield buf, pos, n
                    pos += n


def index_participants(path: Path, chunk: int = 64 << 20) -> dict[str, list[tuple[int, int]]]:
    """Byte runs per participant (a skip-scan: ~1 minute for the full dump)."""
    runs: dict[str, list[tuple[int, int]]] = defaultdict(list)
    size = path.stat().st_size
    with path.open("rb") as stream:
        offset, buf, pos = 0, b"", 0
        current, run_start = None, 0
        while offset < size:
            if len(buf) - pos < 1 << 16:
                buf, pos = buf[pos:] + stream.read(chunk), 0
            n = struct.unpack_from("<i", buf, pos)[0]
            if n < 5 or offset + n > size:
                raise ValueError(f"Invalid BSON document at offset {offset}")
            if len(buf) - pos < n:
                buf, pos = buf[pos:] + stream.read(max(chunk, n)), 0
            uid, _, _ = _header(buf, pos)
            if uid != current:
                if current is not None:
                    runs[current].append((run_start, offset))
                current, run_start = uid, offset
            offset += n
            pos += n
        if current is not None:
            runs[current].append((run_start, offset))
    return dict(runs)


def _local(text: str) -> float:
    text = text.strip().rstrip("Z")
    if "/" in text:
        stamp = datetime.strptime(
            text[:17] if len(text) > 8 else text, "%m/%d/%y %H:%M:%S" if len(text) > 8 else "%m/%d/%y"
        )
    else:
        stamp = datetime.fromisoformat(text[:19])
    return (stamp - datetime(1970, 1, 1)).total_seconds()


def _q(values: Any, qs: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9)) -> list[float] | None:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    return [round(float(v), 3) for v in np.quantile(arr, qs)] if arr.size else None


def _median(values: Any) -> float | None:
    q = _q(values, (0.5,))
    return q[0] if q else None


def _robust_sd(values: Any) -> float | None:
    arr = np.asarray(values, dtype=float)
    if arr.size < 5:
        return None
    return round(float(1.4826 * np.median(np.abs(arr - np.median(arr)))), 3)


def _inside(starts: np.ndarray, ends: np.ndarray, t: np.ndarray) -> np.ndarray:
    if not starts.size:
        return np.zeros(t.shape, dtype=bool)
    order = np.argsort(starts)
    starts, ends = starts[order], np.maximum.accumulate(ends[order])
    k = np.searchsorted(starts, t, side="right") - 1
    return (k >= 0) & (t < ends[np.clip(k, 0, None)])


def _sparse(counts: np.ndarray) -> dict[str, int]:
    return {str(i): int(c) for i, c in enumerate(counts) if c}


# One participant


def _fast_value(buf: bytes | memoryview, after_type: int, n_end: int, key: bytes) -> tuple[bytes, float] | None:
    raw = bytes(buf[after_type:n_end])
    k = raw.find(b"\x02dateTime\x00")
    if k < 0:
        return None
    length = struct.unpack_from("<i", raw, k + 10)[0]
    stamp = raw[k + 14 : k + 13 + length]
    v = raw.find(key, k)
    if v < 0:
        return None
    kind, start = raw[v - 1], v + len(key)
    if kind == 0x10:
        return stamp, float(struct.unpack_from("<i", raw, start)[0])
    if kind == 0x01:
        return stamp, struct.unpack_from("<d", raw, start)[0]
    if kind == 0x02:
        size = struct.unpack_from("<i", raw, start)[0]
        try:
            return stamp, float(raw[start + 4 : start + 3 + size])
        except ValueError:
            return None
    return None


def _seconds(stamps: bytearray, width: int = 19) -> np.ndarray:
    if not stamps:
        return np.zeros(0, dtype=np.int64)
    return np.frombuffer(bytes(stamps), dtype=f"S{width}").astype("datetime64[s]").astype(np.int64)


def profile_participant(path: Path, runs: list[tuple[int, int]]) -> dict[str, Any]:
    hr_t, hr_v = bytearray(), array("f")
    st_t, st_v = bytearray(), array("f")
    docs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    uid = None
    for buf, pos, n in _documents(path, runs):
        uid, kind, after = _header(buf, pos)
        if kind == "heart_rate":
            got = _fast_value(buf, after, pos + n, b"bpm\x00")
            if got and len(got[0]) == 19 and got[1] > 0:
                hr_t += got[0]
                hr_v.append(got[1])
        elif kind == "steps":
            got = _fast_value(buf, after, pos + n, b"value\x00")
            if got and len(got[0]) == 19:
                st_t += got[0]
                st_v.append(got[1])
        elif kind in _DETAILED:
            data = _decode(buf, pos + 4, pos + n).get("data")
            if isinstance(data, dict):
                docs[kind].append(data)

    out: dict[str, Any] = {"id": uid}
    prof = (docs.get("Profile") or [{}])[0]
    out["profile"] = {"gender": prof.get("gender"), "age": prof.get("age"), "bmi": prof.get("bmi")}

    # Intervals: sleep logs and exercise.
    sleeps = []
    for s in docs.get("sleep", []):
        try:
            a, b = _local(s["startTime"]), _local(s["endTime"])
        except KeyError, ValueError:
            continue
        sleeps.append((a, b, s))
    sleep_s = np.asarray([a for a, _, _ in sleeps])
    sleep_e = np.asarray([b for _, b, _ in sleeps])
    exercises = []
    for e in docs.get("exercise", []):
        try:
            a = _local(e["startTime"])
        except KeyError, ValueError:
            continue
        exercises.append((a, a + float(e.get("activeDuration") or e.get("duration") or 0) / 1000, e))
    ex_s = np.asarray([a for a, _, _ in exercises])
    ex_e = np.asarray([b for _, b, _ in exercises])

    # Steps per minute.
    steps_t = _seconds(st_t)
    steps_v = np.asarray(st_v, dtype=float)
    moving_minutes = np.unique(steps_t[steps_v > 0] // 60)

    # Heart rate: wear, cadence by context, diurnal profile.
    t = _seconds(hr_t)
    bpm = np.asarray(hr_v, dtype=float)
    order = np.argsort(t, kind="stable")
    t, bpm = t[order], bpm[order]
    keep = np.concatenate([[True], np.diff(t) > 0]) if t.size else np.zeros(0, dtype=bool)
    t, bpm = t[keep], bpm[keep]
    hr: dict[str, Any] = {"samples": int(t.size)}
    worn_days: np.ndarray = np.zeros(0, dtype=np.int64)
    full_days: set[int] = set()
    if t.size > 1000:
        minutes = np.unique(t // 60)
        day_of_minute = minutes // 1440
        days, per_day = np.unique(day_of_minute, return_counts=True)
        worn = per_day >= 60
        worn_days = days[worn]
        full_days = set(days[per_day >= 12 * 60].tolist())
        span = int(days[-1] - days[0] + 1)
        night = np.bincount(
            np.searchsorted(days, day_of_minute[(minutes % 1440 >= 60) & (minutes % 1440 < 300)]),
            minlength=days.size,
        )
        hr.update(
            span_days=span,
            worn_days=int(worn.sum()),
            wear_fraction=round(float(worn.sum() / span), 4),
            night_wear=round(float((night[worn] >= 120).mean()), 4),
            worn_hours_per_day=_q(per_day[worn] / 60),
        )
        gaps = np.diff(t).astype(float)
        prev, curr = t[:-1], t[1:]
        in_sleep = _inside(sleep_s, sleep_e, prev) & _inside(sleep_s, sleep_e, curr)
        in_workout = _inside(ex_s, ex_e, prev) & _inside(ex_s, ex_e, curr)
        if moving_minutes.size:
            k = np.clip(np.searchsorted(moving_minutes, prev // 60), 0, moving_minutes.size - 1)
            in_moving = moving_minutes[k] == prev // 60
        else:
            in_moving = np.zeros(prev.shape, dtype=bool)
        context = np.where(in_workout, 0, np.where(in_sleep, 1, np.where(in_moving, 3, 2)))
        ok = gaps <= MAX_GAP
        hr["gap_histogram"] = {
            c: _sparse(np.bincount(gaps[ok & (context == i)].astype(int), minlength=MAX_GAP + 1))
            for i, c in enumerate(CONTEXTS)
        }
        hr["long_gaps_per_worn_day"] = round(float((gaps > 3600).sum() / max(1, worn.sum())), 3)
        hour = (t % DAY) // 3600
        asleep = _inside(sleep_s, sleep_e, t)
        hr["awake_by_hour"] = [_median(bpm[(hour == h) & ~asleep]) for h in range(24)]
        hr["asleep_median"] = _median(bpm[asleep])
        hr["awake_quantiles"] = _q(bpm[~asleep], (0.05, 0.25, 0.5, 0.75, 0.95, 0.99))
    out["heart_rate"] = hr

    # Daily steps (days with >= 12 h of heart rate, so partial wear does not bias totals).
    steps: dict[str, Any] = {}
    if steps_t.size:
        day = steps_t // DAY
        totals = np.bincount(day - day.min(), weights=steps_v)
        dates = np.arange(day.min(), day.max() + 1)
        sel = np.asarray([d in full_days for d in dates], dtype=bool) if full_days else totals > 0
        daily, sel_dates = totals[sel], dates[sel]
        weekday = (sel_dates + 3) % 7  # 1970-01-01 was a Thursday; 0 = Monday
        if daily.size >= 7:
            steps.update(
                days=int(daily.size),
                daily=_q(daily),
                cv=round(float(daily.std() / max(daily.mean(), 1.0)), 4),
                weekend_weekday_ratio=round(
                    float(np.median(daily[weekday >= 5]) / max(np.median(daily[weekday < 5]), 1.0)), 4
                )
                if (weekday >= 5).sum() >= 3 and (weekday < 5).sum() >= 5
                else None,
            )
        if moving_minutes.size > 10:
            breaks = np.flatnonzero(np.diff(moving_minutes) > 1)
            lengths = np.diff(np.concatenate([[-1], breaks, [moving_minutes.size - 1]]))
            steps["bout_minutes"] = _q(lengths, (0.5, 0.75, 0.9, 0.99))
            steps["steps_per_active_minute"] = _q(steps_v[steps_v > 0], (0.25, 0.5, 0.75, 0.95))
            steps["active_minutes_per_day"] = round(float(moving_minutes.size / max(1, worn_days.size)), 1)
    out["steps"] = steps

    # Sleep: main sleep timing and architecture; naps.
    main = [(a, b, s) for a, b, s in sleeps if s.get("mainSleep", True) and b - a >= 3 * 3600]
    by_night: dict[str, tuple[float, float, dict[str, Any]]] = {}
    for a, b, s in main:
        key = str(s.get("dateOfSleep", ""))
        if key not in by_night or b - a > by_night[key][1] - by_night[key][0]:
            by_night[key] = (a, b, s)
    sleep: dict[str, Any] = {"nights": len(by_night)}
    if len(by_night) >= 7:
        nights = sorted(by_night.values(), key=lambda x: x[0])
        mid = np.asarray([((a + b) / 2 % DAY) / 3600 for a, b, _ in nights])
        mid = np.where(mid > 18, mid - 24, mid)
        weekend = np.asarray(
            [datetime.fromisoformat(str(s["dateOfSleep"])).weekday() >= 5 for _, _, s in nights], dtype=bool
        )
        asleep = np.asarray([float(s.get("minutesAsleep", 0)) / 60 for _, _, s in nights])
        stages: dict[str, list[float]] = defaultdict(list)
        bouts: dict[str, Counter[int]] = defaultdict(Counter)
        for _, _, s in nights:
            levels = s.get("levels") or {}
            summary = levels.get("summary") or {}
            total = sum(float((summary.get(k) or {}).get("minutes", 0)) for k in ("deep", "light", "rem", "wake"))
            if s.get("type") == "stages" and total > 0:
                for k in ("deep", "light", "rem", "wake"):
                    stages[k].append(float((summary.get(k) or {}).get("minutes", 0)) / total)
                for seg in levels.get("data") or []:
                    bouts[str(seg.get("level"))][round(float(seg.get("seconds", 0)) / 30)] += 1
        sleep.update(
            midsleep_hour=_q(mid),
            midsleep_weekend_shift=round(float(np.median(mid[weekend]) - np.median(mid[~weekend])), 3)
            if weekend.sum() >= 3 and (~weekend).sum() >= 5
            else None,
            midsleep_sd_minutes=None if (sd := _robust_sd(mid)) is None else round(sd * 60, 1),
            asleep_hours=_q(asleep),
            asleep_sd_minutes=round(float(asleep.std() * 60), 1),
            efficiency=_median([float(s.get("efficiency", 0)) for _, _, s in nights]),
            stage_share={k: _median(v) for k, v in stages.items()},
            stage_bout_epochs={k: {str(e): c for e, c in sorted(v.items())} for k, v in bouts.items()},
            stages_share_of_nights=round(sum(1 for _, _, s in nights if s.get("type") == "stages") / len(nights), 3),
        )
        naps = [b - a for a, b, s in sleeps if not s.get("mainSleep", True) or b - a < 3 * 3600]
        weeks = max(1.0, (nights[-1][0] - nights[0][0]) / (7 * DAY))
        sleep["naps_per_week"] = round(len(naps) / weeks, 3)
        sleep["nap_minutes"] = _q(np.asarray(naps) / 60, (0.25, 0.5, 0.75)) if naps else None
    out["sleep"] = sleep

    # Daily summaries.
    def values(kind: str, *path: str) -> list[float]:
        found = []
        for d in docs.get(kind, []):
            node: Any = d
            for part in path:
                node = node.get(part) if isinstance(node, dict) else None
            if isinstance(node, (int, float)) and math.isfinite(node) and node > 0:
                found.append(float(node))
        return found

    out["daily"] = {
        "resting_hr": _q(values("resting_heart_rate", "value", "value")),
        "vo2max": _q(values("demographic_vo2_max", "value", "filteredDemographicVO2Max")),
        "rmssd": _q(values("Daily Heart Rate Variability Summary", "rmssd")),
        "nrem_hr": _q(values("Daily Heart Rate Variability Summary", "nremhr")),
        "breathing_rate": _q(values("Respiratory Rate Summary", "full_sleep_breathing_rate")),
        "spo2": _q(values("Daily SpO2", "average_value")),
    }
    details = sorted(_local(d["timestamp"]) for d in docs.get("Heart Rate Variability Details", []) if "timestamp" in d)
    gaps = np.diff(np.asarray(details))
    out["hrv_detail_gap_seconds"] = _q(gaps[(gaps > 0) & (gaps <= 3600)], (0.25, 0.5, 0.75))

    # Exercise logs.
    if exercises and worn_days.size:
        weeks = max(1.0, worn_days.size / 7)
        out["exercise"] = {
            "per_week": round(len(exercises) / weeks, 3),
            "auto_detected_share": round(
                sum(1 for *_, e in exercises if e.get("logType") == "auto_detected") / len(exercises), 3
            ),
            "minutes": _q([(b - a) / 60 for a, b, _ in exercises]),
            "names": dict(Counter(str(e.get("activityName")) for *_, e in exercises).most_common()),
            "average_hr": _median([float(e["averageHeartRate"]) for *_, e in exercises if e.get("averageHeartRate")]),
        }
    else:
        out["exercise"] = {"per_week": 0.0}
    return out


def _profile_job(job: tuple[str, list[tuple[int, int]]]) -> dict[str, Any]:
    path, runs = job
    return profile_participant(Path(path), runs)


def profile_lifesnaps_bson(
    path: Path, *, workers: int | None = None, participants: Iterator[str] | list[str] | None = None
) -> dict[str, Any]:
    index = index_participants(path)
    wanted = sorted(index) if participants is None else [p for p in participants if p in index]
    jobs = [(str(path), index[p]) for p in wanted]
    with ProcessPoolExecutor(max_workers=workers or min(8, os.cpu_count() or 1)) as pool:
        people = list(pool.map(_profile_job, jobs))
    return {"version": 1, "origin": "real-derived: LifeSnaps fitbit.bson (CC BY 4.0)", "participants": people}


# Device readout minus persona truth for the fitbit_sense model, measured on synthetic twins
# of the LifeSnaps anchors (median over 8 twins, 28 days). Anchor traits are truth, so the
# Fitbit summaries are shifted back by these offsets (assumption; re-measure after model changes).
RHR_DEVICE_BIAS = 4.2  # bpm: awake-still low quantile reads above the truth resting HR
BREATHING_DEVICE_BIAS = -1.3  # breaths/min: the sleep readout is below the persona's resting rate

AGE = {"<30": 25, ">=30": 40}  # LifeSnaps only reports two age bands
BMI = {"<19": 18.3, ">=25": 26.5, ">=30": 32.0}


def _bmi(value: Any) -> float | None:
    if value in BMI:
        return BMI[value]
    try:
        return float(value)
    except TypeError, ValueError:
        return None


def _usable(p: Mapping[str, Any]) -> bool:
    hr, sleep, steps = p.get("heart_rate", {}), p.get("sleep", {}), p.get("steps", {})
    return bool(
        p.get("profile", {}).get("gender")
        and hr.get("worn_days", 0) >= 42
        and sleep.get("nights", 0) >= 14
        and sleep.get("midsleep_hour")
        and steps.get("daily")
        and p.get("daily", {}).get("resting_hr")
    )


def structured_workouts_per_week(exercise: Mapping[str, Any]) -> float:
    """Exercise logs per week without walks: Fitbit auto-detects every walk of 10+ minutes."""
    names = exercise.get("names") or {}
    total = sum(names.values())
    if not total:
        return 0.0
    return float(exercise.get("per_week", 0.0)) * (total - names.get("Walk", 0)) / total


def _archetype(steps: float, workouts: float, weekend_ratio: float | None) -> str:
    """Rule-based archetype from observed daily steps and structured workouts per week (assumption).

    People who walk a lot but log no other exercise get ``older_daily_walker`` whatever
    their age: it is the archetype whose behaviour is daily walking without workouts.
    """
    if workouts < 0.5:
        return "sedentary" if steps < 5000 else "older_daily_walker"
    if steps >= 11000 and workouts >= 3.0:
        return "athlete"
    if weekend_ratio is not None and weekend_ratio >= 1.3 and workouts < 2.0:
        return "weekend_warrior"
    return "regular_exerciser" if workouts >= 1.0 else "weekend_warrior"


def anchor_traits(p: Mapping[str, Any]) -> dict[str, Any]:
    hr, sleep, steps, daily = p["heart_rate"], p["sleep"], p["steps"], p["daily"]
    age = AGE.get(p["profile"].get("age") or "", 30)
    ex = p.get("exercise", {})
    daily_steps = steps["daily"][2]
    traits: dict[str, float] = {
        "rhr": round(daily["resting_hr"][2] - RHR_DEVICE_BIAS, 1),
        "adherence": round(min(0.995, hr["wear_fraction"]), 3),
        "night_wear": round(min(0.995, max(0.05, hr["night_wear"])), 3),
        "midsleep_hour": round(sleep["midsleep_hour"][2], 3),
        "daily_steps_target": round(daily_steps),
        "activity_level": round(min(1.0, max(0.05, (daily_steps - 3000) / 12000)), 3),
        "asleep_hours_target": round(sleep["asleep_hours"][2], 3),
        "sleep_need_hours": round(sleep["asleep_hours"][2] + 0.4, 2),
    }
    if daily.get("vo2max"):
        traits["vo2max"] = round(daily["vo2max"][2], 2)
    if daily.get("rmssd"):
        # Fitbit reports RMSSD from deep-sleep windows, which reads higher than the
        # whole-night value the generator's ln_rmssd describes (assumption: ~20%).
        traits["ln_rmssd"] = round(math.log(daily["rmssd"][2]) - 0.2, 3)
    if daily.get("breathing_rate"):
        traits["respiratory_rate"] = round(daily["breathing_rate"][2] - BREATHING_DEVICE_BIAS, 2)
    if daily.get("spo2"):
        traits["spo2"] = round(daily["spo2"][2], 2)
    if sleep.get("midsleep_weekend_shift") is not None:
        traits["weekend_shift_hours"] = round(max(0.0, sleep["midsleep_weekend_shift"]), 3)
    if sleep.get("midsleep_sd_minutes"):
        traits["regularity_minutes"] = round(min(180.0, max(10.0, sleep["midsleep_sd_minutes"])), 1)
    if (bmi := _bmi(p["profile"].get("bmi"))) is not None:
        traits["bmi"] = bmi
    return {
        "age": age,
        "sex": "F" if p["profile"]["gender"] == "FEMALE" else "M",
        "archetype": _archetype(daily_steps, structured_workouts_per_week(ex), steps.get("weekend_weekday_ratio")),
        "wearable": "fitbit_sense",
        "phone": "android_phone",
        "conditions": [],
        "medications": [],
        "traits": traits,
    }


def _features(p: Mapping[str, Any]) -> list[float]:
    return [
        math.log(p["steps"]["daily"][2]),
        p["daily"]["resting_hr"][2],
        p["sleep"]["midsleep_hour"][2],
        p["sleep"]["asleep_hours"][2],
        structured_workouts_per_week(p.get("exercise", {})),
        1.0 if p["profile"]["gender"] == "FEMALE" else 0.0,
    ]


def select_anchors(people: Sequence[Mapping[str, Any]], k: int) -> list[Mapping[str, Any]]:
    """k medoids on standardized steps, resting HR, sleep timing/duration, exercise and sex.

    Medoids are real, typical participants that together span the cohort; extremes are
    left to the population sampler. Deterministic: start from evenly spaced points along
    the first principal component, then alternate assignment and medoid updates.
    """
    usable = sorted((p for p in people if _usable(p)), key=lambda p: str(p["id"]))
    if len(usable) <= k:
        return usable
    x = np.asarray([_features(p) for p in usable])
    x = (x - x.mean(axis=0)) / np.maximum(x.std(axis=0), 1e-9)
    dist = np.linalg.norm(x[:, None] - x[None], axis=2)
    component = np.linalg.svd(x, full_matrices=False)[2][0]
    ranked = np.argsort(x @ component, kind="stable")
    medoids = [int(ranked[int(i)]) for i in np.linspace(0, len(usable) - 1, k + 2)[1:-1].round()]
    for _ in range(50):
        labels = np.argmin(dist[:, medoids], axis=1)
        updated = []
        for c in range(k):
            members = np.flatnonzero(labels == c)
            updated.append(int(members[np.argmin(dist[np.ix_(members, members)].sum(axis=1))]))
        if updated == medoids:
            break
        medoids = updated
    return [usable[i] for i in sorted(medoids, key=lambda i: str(usable[i]["id"]))]


def anchors_overlay(profile: Mapping[str, Any], k: int = 8) -> dict[str, Any]:
    chosen = select_anchors(list(profile["participants"]), k)
    profiles: dict[str, Any] = {}
    for i, p in enumerate(chosen, 1):
        entry = anchor_traits(p)
        entry["source"] = (
            f"calibrated: LifeSnaps fitbit.bson participant {p['id']} (CC BY 4.0), medians over "
            f"{p['heart_rate']['worn_days']} worn days; age from the dataset's two-band field"
        )
        profiles[f"lifesnaps_{i:02d}"] = entry
    return {
        "meta": {"target": "cohorts", "version": "calibration:lifesnaps-bson", "replace": ["anchors.profiles"]},
        "anchors": {"profiles": profiles},
    }


def _pooled_gaps(people: Sequence[Mapping[str, Any]], context: str, cap: int, seed: int = 0) -> np.ndarray:
    counts = np.zeros(MAX_GAP + 1)
    for p in people:
        for gap, c in p.get("heart_rate", {}).get("gap_histogram", {}).get(context, {}).items():
            counts[int(gap)] += c
    total = counts.sum()
    if not total:
        return np.zeros(0)
    if total > cap:
        counts = np.random.default_rng(seed).multinomial(cap, counts / total)
    return np.repeat(np.arange(MAX_GAP + 1, dtype=float), counts.astype(int))


def device_overlay(profile: Mapping[str, Any]) -> dict[str, Any]:
    people = [p for p in profile["participants"] if p.get("heart_rate", {}).get("gap_histogram")]
    cadence = {}
    for c in CONTEXTS:
        gaps = _pooled_gaps(people, c, 200_000)
        if gaps.size >= 100:
            cadence[c] = fit_lognormal_mixture(gaps)
    hrv = [q[1] for p in profile["participants"] if (q := p.get("hrv_detail_gap_seconds"))]
    metrics: dict[str, Any] = {
        "source": (
            f"calibrated: LifeSnaps fitbit.bson ({len(people)} people, Fitbit Sense, CC BY 4.0); HR cadence = "
            "2-component lognormal mixtures per context pooled across people; HRV window cadence from "
            "'Heart Rate Variability Details'; resting HR method chosen by comparing Fitbit RHR "
            "with awake and asleep HR quantiles"
        ),
        "heart_rate": {"mode": "samples", "cadence": cadence, "quality": True},
        # Fitbit's daily resting HR is ~1 bpm above the 5th percentile of awake HR in LifeSnaps
        # (median over people), not the lowest half hour of the night.
        "resting_heart_rate": {"mode": "daily", "method": "awake_still_low_quantile"},
    }
    if hrv:
        metrics["hrv"] = {
            "mode": "hrv",
            "nightly_only": True,
            "cadence": {"sleep": [[1.0, float(np.median(hrv)), 0.1]]},
        }
    return {
        "meta": {"target": "devices", "version": "calibration:lifesnaps-bson"},
        "models": {
            "fitbit_sense": {
                "source": "spec: Fitbit Sense as worn in LifeSnaps (2021-22); writes to Health Connect on Android",
                "extends": "fitbit",
                "kind": "watch",
                "hardware": "Fitbit Sense",
                "available_from": "2020-09-25",
                "features": ["wrist_temperature"],
                "metrics": metrics,
            }
        },
    }


def write_lifesnaps_overlays(profile: Mapping[str, Any], out_dir: Path, *, k: int = 8) -> dict[str, Path]:
    import tomli_w

    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    devices = device_overlay(profile)
    devices["ownership"] = {"android_wearables": {"fitbit": 0.15, "fitbit_sense": 0.10}}
    for name, overlay in (
        ("anchors-lifesnaps", anchors_overlay(profile, k)),
        ("devices-fitbit-sense", devices),
    ):
        path = out_dir / f"{name}.toml"
        path.write_text(_HEADER + tomli_w.dumps(overlay), encoding="utf-8")
        written[name] = path
    return written


def calibrate_lifesnaps(
    bson: Path, out_dir: Path = DEFAULTS_DIR, *, profile_dir: Path, k: int = 8, workers: int | None = None
) -> dict[str, Path]:
    """Profile ``fitbit.bson`` and write overlays to ``out_dir`` (defaults to ``params/defaults/``).

    Write the JSON profile to ``profile_dir``, with one entry per participant.
    """
    import json

    profile = profile_lifesnaps_bson(bson, workers=workers)
    profile_dir.mkdir(parents=True, exist_ok=True)
    target = profile_dir / "lifesnaps_bson.profile.json"
    target.write_text(json.dumps(profile, indent=1, sort_keys=True), encoding="utf-8")
    return {"profile": target, **write_lifesnaps_overlays(profile, out_dir, k=k)}


_HEADER = (
    "# Generated by persona_gen.calibration.calibrate_lifesnaps from the LifeSnaps\n"
    "# dataset (Yfantidou et al. 2022, CC BY 4.0). Do not edit by hand; re-run the calibration.\n\n"
)

__all__ = [
    "anchor_traits",
    "anchors_overlay",
    "calibrate_lifesnaps",
    "device_overlay",
    "index_participants",
    "profile_lifesnaps_bson",
    "profile_participant",
    "select_anchors",
    "structured_workouts_per_week",
    "write_lifesnaps_overlays",
]
