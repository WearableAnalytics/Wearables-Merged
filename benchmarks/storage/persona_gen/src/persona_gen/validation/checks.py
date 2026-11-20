"""Dataset checks. Each report returns plain dicts with ``passed`` flags and numbers.

These operate on whole tables in memory and suit validation-sized datasets (hundreds of
personas, weeks to months). For full-size datasets point DuckDB at the Parquet files.
"""

import itertools
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from ..config import Params
from ..dataset import Dataset

GRID_FREE_SOURCES = ("Apple Watch",)
POINT_METRICS = ("heart_rate", "respiratory_rate", "oxygen_saturation")


def _col(table: pa.Table, name: str) -> np.ndarray:
    column = table[name]
    t = column.type
    if pa.types.is_dictionary(t):
        out = np.empty(len(column), dtype=object)
        offset = 0
        for chunk in column.chunks:
            values = np.asarray([*chunk.dictionary.to_pylist(), None], dtype=object)
            codes = chunk.indices.fill_null(-1).to_numpy(zero_copy_only=False)
            out[offset : offset + len(chunk)] = values[codes]
            offset += len(chunk)
        return out
    if pa.types.is_timestamp(t):
        scale = {"s": 1, "ms": 1e3, "us": 1e6, "ns": 1e9}[t.unit]
        return pc.cast(column, pa.int64()).to_numpy(zero_copy_only=False).astype(np.float64) / scale
    if pa.types.is_string(t):
        return np.asarray(column.to_pylist(), dtype=object)
    return column.to_numpy(zero_copy_only=False)


def _check(name: str, passed: bool, **detail: Any) -> dict[str, Any]:
    return {"check": name, "passed": bool(passed), **detail}


# Dynamics checks that are known not to match their reference; the reason is reported as ``expected_fail``.
_EXPECTED_DYNAMICS_FAILURES = {
    "workout_day_share": "LifeSnaps reference counts Fitbit auto-recognised activity as workouts",
}


# Structure
def _patient_codes(table: pa.Table, vocabulary: dict[str, int]) -> np.ndarray:
    column = table["patient_id"]
    out = np.empty(len(column), dtype=np.int64)
    offset = 0
    for chunk in column.chunks:
        if pa.types.is_dictionary(chunk.type):
            remap = np.asarray(
                [vocabulary.setdefault(v, len(vocabulary)) for v in chunk.dictionary.to_pylist()] + [-1], dtype=np.int64
            )
            codes = chunk.indices.fill_null(-1).to_numpy(zero_copy_only=False)
            out[offset : offset + len(chunk)] = remap[codes]
        else:
            out[offset : offset + len(chunk)] = [vocabulary.setdefault(v, len(vocabulary)) for v in chunk.to_pylist()]
        offset += len(chunk)
    return out


def _keys(table: pa.Table, seq: np.ndarray, vocabulary: dict[str, int]) -> np.ndarray:
    return _patient_codes(table, vocabulary) * (1 << 32) + seq.astype(np.int64)


def _unique_ids(column: pa.ChunkedArray) -> bool:
    """Uniqueness of fixed-width ids via a 64-bit polynomial hash (exact check on collisions)."""
    hashes = []
    for chunk in column.chunks:
        offsets = np.frombuffer(chunk.buffers()[1], dtype=np.int32)[chunk.offset : chunk.offset + len(chunk) + 1]
        data = np.frombuffer(chunk.buffers()[2], dtype=np.uint8)
        width = int(offsets[1] - offsets[0]) if len(chunk) else 0
        if not len(chunk) or np.any(np.diff(offsets) != width):
            hashes.append(np.asarray([hash(v) for v in chunk.to_pylist()], dtype=np.int64).view(np.uint64))
            continue
        matrix = data[offsets[0] : offsets[-1]].reshape(len(chunk), width).astype(np.uint64)
        h = np.zeros(len(chunk), dtype=np.uint64)
        for col in range(width):
            h = h * np.uint64(1099511628211) + matrix[:, col]
        hashes.append(h)
    if not hashes:
        return True
    values = np.sort(np.concatenate(hashes))
    if not np.any(values[1:] == values[:-1]):
        return True
    return len(set(column.to_pylist())) == len(column)


def structure_report(ds: Dataset) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for shard in ds.shards():
        for check in _structure_shard(ds, shard):
            name = check["check"]
            if name not in totals:
                totals[name] = dict(check)
                continue
            merged = totals[name]
            merged["passed"] = merged["passed"] and check["passed"]
            for key, value in check.items():
                if key in ("check", "passed"):
                    continue
                if isinstance(value, int) and not isinstance(value, bool):
                    merged[key] = merged.get(key, 0) + value
                elif isinstance(value, float):
                    merged[key] = max(merged.get(key, 0.0), value)
    return list(totals.values())


def _structure_shard(ds: Dataset, shard: int) -> list[dict[str, Any]]:
    columns = [
        "record_id",
        "patient_id",
        "device_id",
        "source_name",
        "platform",
        "metric",
        "truth_kind",
        "truth_seq",
        "start",
        "end",
        "created_at",
    ]
    obs = ds.table("observations", columns=columns, shard=shard)
    out: list[dict[str, Any]] = []
    kind = _col(obs, "truth_kind")
    seq = _col(obs, "truth_seq")
    start, end, created = _col(obs, "start"), _col(obs, "end"), _col(obs, "created_at")
    out.append(_check("end_not_before_start", bool((end >= start).all())))
    out.append(_check("created_not_before_end", bool((created >= end).all())))
    out.append(_check("ids_unique", _unique_ids(obs["record_id"]), rows=obs.num_rows))
    obs = obs.drop_columns(["record_id"])
    vocabulary: dict[str, int] = {}
    obs_keys = _keys(obs, seq, vocabulary)
    truth_tables = {
        "interval": "truth_intervals",
        "night": "truth_nights",
        "day": "truth_days",
        "workout": "truth_workouts",
        "hrv_window": "truth_hrv",
    }
    missing = 0
    for k, table in truth_tables.items():
        t = ds.table(table, columns=["patient_id", "seq"], shard=shard)
        known = np.sort(_keys(t, _col(t, "seq"), vocabulary))
        sel = obs_keys[kind == k]
        if not sel.size:
            continue
        pos = np.clip(np.searchsorted(known, sel), 0, max(0, known.size - 1))
        missing += int((known[pos] != sel).sum()) if known.size else int(sel.size)
    unknown_kind = int((~np.isin(kind, list(truth_tables))).sum())
    out.append(
        _check("truth_references_exist", missing == 0 and unknown_kind == 0, missing=missing, unknown_kind=unknown_kind)
    )
    intervals = ds.table("truth_intervals", columns=["patient_id", "seq", "start", "end"], shard=shard)
    keys = _keys(intervals, _col(intervals, "seq"), vocabulary)
    order = np.argsort(keys)
    keys, a, b = keys[order], _col(intervals, "start")[order], _col(intervals, "end")[order]
    metric = _col(obs, "metric")
    sel = np.flatnonzero((kind == "interval") & np.isin(metric, POINT_METRICS))
    if sel.size and keys.size:
        pos = np.clip(np.searchsorted(keys, obs_keys[sel]), 0, keys.size - 1)
        inside = (keys[pos] == obs_keys[sel]) & (a[pos] - 1 <= start[sel]) & (start[sel] <= b[pos] + 1)
    else:
        inside = np.ones(sel.size, dtype=bool)
    out.append(
        _check("samples_inside_truth_interval", bool(inside.all()), checked=int(sel.size), outside=int((~inside).sum()))
    )
    wear = ds.table("truth_wear", shard=shard)
    device = _col(obs, "device_id")
    w_dev, w_a, w_b = _col(wear, "device_id"), _col(wear, "start"), _col(wear, "end")
    point = np.isin(metric, POINT_METRICS)
    violations = 0
    for d in np.unique(w_dev):
        m = w_dev == d
        o = np.argsort(w_a[m])
        lo, hi = w_a[m][o], w_b[m][o]
        t = start[point & (device == d)]
        k = np.searchsorted(lo, t, side="right") - 1
        violations += int(((k >= 0) & (t > lo[np.clip(k, 0, None)] + 1) & (t < hi[np.clip(k, 0, None)] - 1)).sum())
    out.append(_check("no_samples_while_off_wrist", violations == 0, violations=violations))
    platform = _col(obs, "platform")
    source = _col(obs, "source_name")
    rmssd_apple = int(((metric == "hrv_rmssd") & (source == "Apple Watch")).sum())
    out.append(_check("no_apple_watch_rmssd", rmssd_apple == 0, rows=rmssd_apple))
    sdnn_hc = int(((metric == "hrv_sdnn") & (platform == "health_connect")).sum())
    out.append(_check("no_sdnn_on_health_connect", sdnn_hc == 0, rows=sdnn_hc))
    hr = (metric == "heart_rate") & np.isin(source, GRID_FREE_SOURCES)
    if hr.sum() > 500:
        share = float((np.mod(start[hr], 60) == 0).mean())
        out.append(_check("no_minute_grid_native_hr", share < 0.05, share_on_minute=round(share, 4)))
    return out


def behaviour_report(ds: Dataset, params: Params) -> list[dict[str, Any]]:
    """Checks on the truth timeline: minimum state durations, flicker and plausible heart-rate targets."""
    t = ds.table("truth_intervals", columns=["patient_id", "state", "start", "end", "hr_target", "activity"])
    state = _col(t, "state")
    duration = _col(t, "end") - _col(t, "start")
    names = params["behavior"]["states"]["names"]
    mins = dict(zip(names, params["behavior"]["states"]["min_minutes"], strict=True))
    out = []
    pid = _col(t, "patient_id")
    # Interior intervals only: the first/last interval of a gap may be cut by a fixed block.
    for name, minimum in mins.items():
        sel = state == name
        if not sel.any():
            continue
        short = float((duration[sel] < minimum * 60 * 0.5).mean())
        out.append(
            _check(
                f"duration_{name}",
                short < 0.05,
                median_minutes=round(float(np.median(duration[sel]) / 60), 2),
                share_below_half_minimum=round(short, 4),
            )
        )
    flicker = 0
    for p in np.unique(pid):
        sel = (pid == p) & np.isin(state, ["workout"])
        flicker += int((duration[sel] < 10).sum())
    out.append(_check("no_workout_flicker", flicker == 0, intervals_under_10s=flicker))
    out.append(
        _check("hr_targets_plausible", bool((_col(t, "hr_target") < 215).all() and (_col(t, "hr_target") > 30).all()))
    )
    transitions = len(state) / max(1, len(np.unique(pid))) / max(1, ds.manifest["recipe"]["days"])
    out.append(_check("transitions_per_day", 20 <= transitions <= 400, mean=round(transitions, 1)))
    return out


# Statistics
def _daily_observed(
    ds: Dataset, metric: str, how: str = "sum", *, wearable_only: bool = False
) -> dict[tuple[str, int], float]:
    """Per person-day totals (or means) of one metric, preferring the wearable over the phone,
    like a HealthKit statistics query merging overlapping sources. Streams shard by shard."""
    result: dict[tuple[str, int], float] = {}
    for shard in ds.shards():
        obs = ds.table(
            "observations",
            columns=["patient_id", "start", "start_offset_min", "value", "device_id", "duplicate_of"],
            filter=(pc.field("metric") == metric) & pc.field("duplicate_of").is_null(),
            shard=shard,
        )
        if not obs.num_rows:
            continue
        pid, value = _col(obs, "patient_id"), _col(obs, "value")
        devices = ds.table("devices", columns=["device_id", "role"], shard=shard)
        ids, roles = _col(devices, "device_id"), _col(devices, "role")
        device = _col(obs, "device_id")
        local_day = np.floor((_col(obs, "start") + _col(obs, "start_offset_min") * 60.0) / 86400).astype(np.int64)
        # Wearable totals overwrite phone totals for a day where both contributed.
        for role in ("wearable",) if wearable_only else ("phone", "wearable"):
            sel = np.isin(device, ids[roles == role])
            if not sel.any():
                continue
            keys = np.char.add(pid[sel].astype(str), np.char.add("|", local_day[sel].astype(str)))
            uniq, inverse = np.unique(keys, return_inverse=True)
            sums = np.bincount(inverse, weights=value[sel])
            counts = np.bincount(inverse)
            values = sums if how == "sum" else sums / counts
            for key, v in zip(uniq, values, strict=True):
                p, d = str(key).rsplit("|", 1)
                result[(p, int(d))] = float(v)
    return result


def statistical_report(ds: Dataset, params: Params) -> list[dict[str, Any]]:
    """Compare population statistics (steps, resting HR, SDNN, sleep and others) with the ranges in
    ``references.toml``.
    """
    refs = params["references"]
    personas = ds.table("personas", columns=["patient_id", "age", "sex"])
    age = dict(zip(_col(personas, "patient_id"), _col(personas, "age"), strict=True))
    sex = dict(zip(_col(personas, "patient_id"), _col(personas, "sex"), strict=True))
    out = []

    def per_person(daily: Mapping[tuple[str, int], float], minimum: float = 0.0) -> dict[str, float]:
        grouped: dict[str, list[float]] = defaultdict(list)
        for (p, _), v in daily.items():
            if v > minimum:
                grouped[p].append(v)
        return {p: float(np.median(v)) for p, v in grouped.items() if len(v) >= 3}

    steps = per_person(_daily_observed(ds, "steps"), 500)
    if steps:
        young = [v for p, v in steps.items() if age[p] < 65]
        older = [v for p, v in steps.items() if age[p] >= 65]
        lo, hi = refs["steps"]["median_range"]
        m = float(np.median(young)) if young else float("nan")
        out.append(_check("steps_median_under_65", lo <= m <= hi, median=round(m), people=len(young), range=[lo, hi]))
        if older:
            lo, hi = refs["steps"]["older_median_range"]
            m = float(np.median(older))
            out.append(
                _check("steps_median_65_plus", lo <= m <= hi, median=round(m), people=len(older), range=[lo, hi])
            )
        p10, p90 = np.percentile(list(steps.values()), [10, 90])
        lo, hi = refs["spread"]["steps_p10_p90"]
        out.append(
            _check(
                "steps_between_person_spread",
                p10 < lo * 1.4 and p90 > hi * 0.7,
                p10=round(float(p10)),
                p90=round(float(p90)),
                lifesnaps=[lo, hi],
            )
        )
    rhr = per_person(_daily_observed(ds, "resting_heart_rate", "mean"))
    if rhr:
        lo, hi = refs["resting_heart_rate"]["median_range"]
        m = float(np.median(list(rhr.values())))
        out.append(_check("resting_hr_median", lo <= m <= hi, median=round(m, 1), people=len(rhr), range=[lo, hi]))
        # Compare sexes within one device method: Garmin-style (lowest 30 min incl. sleep)
        # and Apple-style (awake rest) resting HR differ by several bpm, so a device mix that
        # differs between the sexes would otherwise dominate.
        devices = ds.table("devices", columns=["patient_id", "role", "model"])
        model = {
            p: m
            for p, r, m in zip(_col(devices, "patient_id"), _col(devices, "role"), _col(devices, "model"), strict=True)
            if r == "wearable"
        }
        diffs, weights = [], []
        for m in set(model.values()):
            f = [v for p, v in rhr.items() if sex[p] == "F" and model.get(p) == m]
            mm = [v for p, v in rhr.items() if sex[p] == "M" and model.get(p) == m]
            if len(f) >= 3 and len(mm) >= 3:
                diffs.append(float(np.median(f) - np.median(mm)))
                weights.append(min(len(f), len(mm)))
        if sum(weights) >= 10:
            diff = float(np.average(diffs, weights=weights))
            lo, hi = refs["resting_heart_rate"]["female_minus_male"]
            out.append(
                _check(
                    "resting_hr_female_minus_male",
                    lo - 3 <= diff <= hi + 3,
                    difference=round(diff, 1),
                    devices=len(diffs),
                )
            )
    sdnn = per_person(_daily_observed(ds, "hrv_sdnn", "mean"))
    if sdnn:
        young = [v for p, v in sdnn.items() if age[p] < 40]
        older = [v for p, v in sdnn.items() if age[p] >= 60]
        if len(young) >= 5:
            lo, hi = refs["hrv_sdnn"]["young_median_range"]
            m = float(np.median(young))
            out.append(_check("sdnn_median_under_40", lo <= m <= hi, median=round(m, 1), people=len(young)))
        if len(older) >= 5:
            lo, hi = refs["hrv_sdnn"]["older_median_range"]
            m = float(np.median(older))
            out.append(_check("sdnn_median_60_plus", lo <= m <= hi, median=round(m, 1), people=len(older)))
    nights = ds.table("truth_nights", columns=["patient_id", "asleep_seconds", "nap"])
    asleep = _col(nights, "asleep_seconds")[~_col(nights, "nap").astype(bool)] / 60
    if asleep.size:
        lo, hi = refs["sleep"]["median_minutes_range"]
        m = float(np.median(asleep))
        out.append(_check("sleep_minutes_median", lo <= m <= hi, median=round(m), range=[lo, hi]))
    return out


def effect_report(ds: Dataset) -> list[dict[str, Any]]:
    events = ds.table("events")
    kind, code, pid, start = (
        _col(events, "kind"),
        _col(events, "code"),
        _col(events, "patient_id"),
        _col(events, "start"),
    )
    rhr = _daily_observed(ds, "resting_heart_rate", "mean")
    out = []
    drops = []
    starts = (kind == "medication_start") & (code == "beta_blocker")
    first: dict[str, float] = {}
    for p, t in zip(pid[starts], start[starts], strict=True):
        first.setdefault(p, t)  # first start per person; later restarts overlap the first course
    for p, t in first.items():
        d0 = int(t // 86400)
        before = [rhr[(p, d)] for d in range(d0 - 10, d0) if (p, d) in rhr]
        after = [rhr[(p, d)] for d in range(d0 + 8, d0 + 22) if (p, d) in rhr]
        if len(before) >= 3 and len(after) >= 3:
            drops.append(float(np.mean(after) - np.mean(before)))
    out.append(
        _check(
            "beta_blocker_lowers_resting_hr",
            not drops or float(np.median(drops)) < -2,
            starts=len(drops),
            median_change_bpm=round(float(np.median(drops)), 2) if drops else None,
        )
    )
    doses_all = events.filter(pc.field("kind") == "medication_dose")
    diffs: list[float] = []
    for shard in ds.shards() if doses_all.num_rows else []:
        doses = ds.table("events", filter=pc.field("kind") == "medication_dose", shard=shard)
        if not doses.num_rows:
            continue
        dosed = list(set(_col(doses, "patient_id")))
        obs = ds.table(
            "observations",
            columns=["patient_id", "metric", "start", "start_offset_min", "value", "truth_seq"],
            filter=(pc.field("metric") == "heart_rate") & pc.field("patient_id").isin(dosed),
            shard=shard,
        )
        intervals = ds.table(
            "truth_intervals",
            columns=["patient_id", "seq", "state"],
            filter=pc.field("patient_id").isin(dosed),
            shard=shard,
        )
        state = {
            (p, int(s)): st
            for p, s, st in zip(
                _col(intervals, "patient_id"), _col(intervals, "seq"), _col(intervals, "state"), strict=True
            )
        }
        dose_days = defaultdict(set)
        for p, t in zip(_col(doses, "patient_id"), _col(doses, "start"), strict=True):
            dose_days[p].add(int(t // 86400))
        o_pid, o_t, o_v, o_seq = _col(obs, "patient_id"), _col(obs, "start"), _col(obs, "value"), _col(obs, "truth_seq")
        local_hour = ((o_t + _col(obs, "start_offset_min") * 60.0) % 86400) / 3600
        for p, days in dose_days.items():
            sel = (o_pid == p) & (local_hour > 10) & (local_hour < 17)
            if not sel.any():
                continue
            still = np.asarray([state.get((p, int(s))) == "sedentary" for s in o_seq[sel]], dtype=bool)
            day = (o_t[sel] // 86400).astype(int)
            values = o_v[sel]
            on = np.isin(day, list(days)) & still
            off = ~np.isin(day, list(days)) & still
            if on.sum() >= 20 and off.sum() >= 20:
                diffs.append(float(values[on].mean() - values[off].mean()))
    if doses_all.num_rows:
        out.append(
            _check(
                "stimulant_dose_days_raise_daytime_hr",
                not diffs or float(np.median(diffs)) > 1.0,
                personas=len(diffs),
                median_difference_bpm=round(float(np.median(diffs)), 2) if diffs else None,
            )
        )
    labelled = {k for k in kind}
    out.append(_check("effects_labelled", True, kinds=sorted(labelled)))
    return out


def shape_report(
    profile: Mapping[str, Any], ds: Dataset, patient_id: str, family: str, source_name: str
) -> list[dict[str, Any]]:
    from ..calibration.apple_health import HK, HKC

    obs = ds.table("observations", columns=["patient_id", "source_name", "metric", "start", "end", "created_at"])
    sel = (_col(obs, "patient_id") == patient_id) & (_col(obs, "source_name") == source_name)
    metric = _col(obs, "metric")[sel]
    s, e, c = _col(obs, "start")[sel], _col(obs, "end")[sel], _col(obs, "created_at")[sel]
    days = ds.manifest["recipe"]["days"]
    names = {
        "heart_rate": HK + "HeartRate",
        "steps": HK + "StepCount",
        "active_energy": HK + "ActiveEnergyBurned",
        "basal_energy": HK + "BasalEnergyBurned",
        "distance_walking_running": HK + "DistanceWalkingRunning",
        "hrv_sdnn": HK + "HeartRateVariabilitySDNN",
        "respiratory_rate": HK + "RespiratoryRate",
        "oxygen_saturation": HK + "OxygenSaturation",
        "sleep": HKC + "SleepAnalysis",
        "physical_effort": HK + "PhysicalEffort",
        "resting_heart_rate": HK + "RestingHeartRate",
    }
    real = profile["sources"].get(family, {})
    out = []
    window_start = ds.manifest["recipe"]["start"]
    for ours, theirs in names.items():
        if theirs not in real or real[theirs]["last"] < window_start:
            continue  # the real source stopped writing this type before the window
        m = metric == ours
        if not m.any():
            out.append(_check(f"shape_{ours}", False, reason="no synthetic records"))
            continue
        ss = np.sort(s[m])
        gaps = np.diff(ss)
        gaps = gaps[gaps > 0]
        q = [0.05, 0.25, 0.5, 0.75, 0.95]
        synth = {
            "per_day": round(m.sum() / days, 1),
            "gap": [round(float(x), 1) for x in np.quantile(gaps, q)] if gaps.size > 5 else None,
            "duration": [round(float(x), 1) for x in np.quantile(e[m] - s[m], q)],
            "lag": [round(float(x), 1) for x in np.quantile(c[m] - e[m], q)],
        }
        r = real[theirs]
        ratio = synth["per_day"] / max(r["per_day"], 1e-9)
        med_gap_ratio = (
            (synth["gap"][2] + 1) / (r["gap_quantiles"][2] + 1) if synth["gap"] and r.get("gap_quantiles") else None
        )
        passed = 0.5 <= ratio <= 2.0 and (med_gap_ratio is None or 0.33 <= med_gap_ratio <= 3.0)
        out.append(
            _check(
                f"shape_{ours}",
                passed,
                synthetic=synth,
                real={
                    "per_day": r["per_day"],
                    "gap": r.get("gap_quantiles"),
                    "duration": r.get("duration_quantiles"),
                    "lag": r.get("lag_quantiles"),
                },
                per_day_ratio=round(ratio, 2),
            )
        )
    return out


# TODO(realism): Add sequence-level and clinical-event validation (see also validation/storage.py).
def validate(ds: Dataset, params: Params) -> dict[str, list[dict[str, Any]]]:
    return {
        "structure": structure_report(ds),
        "behaviour": behaviour_report(ds, params),
        "statistics": statistical_report(ds, params),
        "effects": effect_report(ds),
        "dynamics": dynamics_report(ds, params),
    }


def dynamics_report(ds: Dataset, params: Params) -> list[dict[str, Any]]:
    """Within-person dynamics of wearable users against LifeSnaps (needs a references overlay
    with a ``dynamics`` table from ``calibration.lifesnaps_overlay``; otherwise returns [])."""
    refs = params["references"].get("dynamics")
    if not refs:
        return []
    devices = ds.table("devices", columns=["patient_id", "role"])
    wearers = set(_col(devices, "patient_id")[_col(devices, "role") == "wearable"])
    days_in_window = ds.manifest["recipe"]["days"]
    first_day = int(np.datetime64(ds.manifest["recipe"]["start"], "D").astype(np.int64))
    steps = {
        k: v
        for k, v in _daily_observed(ds, "steps", wearable_only=True).items()
        if first_day <= k[1] < first_day + days_in_window
    }
    per: dict[str, dict[int, float]] = defaultdict(dict)
    for (p, d), v in steps.items():
        if p in wearers:
            per[p][d] = v
    stats: dict[str, list[float]] = defaultdict(list)
    for series in per.values():
        worn = {d: v for d, v in series.items() if v >= 200}
        stats["wear_fraction"].append(len(worn) / days_in_window)
        if len(worn) < 14:
            continue
        values = np.asarray(list(worn.values()))
        stats["steps_cv"].append(float(values.std() / values.mean()))
        ordered = sorted(worn)
        pairs = [(worn[a], worn[b]) for a, b in itertools.pairwise(ordered) if b == a + 1]
        if len(pairs) > 10:
            x, y = np.asarray(pairs).T
            stats["steps_lag1"].append(float(np.corrcoef(x, y)[0, 1]))
        weekday = [v for d, v in worn.items() if (d + 3) % 7 < 5]  # epoch day 0 was a Thursday
        weekend = [v for d, v in worn.items() if (d + 3) % 7 >= 5]
        if len(weekend) >= 4 and len(weekday) >= 8:
            stats["weekend_weekday_steps"].append(float(np.median(weekend) / np.median(weekday)))
    workouts = ds.table("workouts", columns=["patient_id", "start", "start_offset_min"])
    w_days: dict[str, set[int]] = defaultdict(set)
    for p, t, o in zip(
        _col(workouts, "patient_id"), _col(workouts, "start"), _col(workouts, "start_offset_min"), strict=True
    ):
        w_days[p].add(int((float(t) + float(o) * 60) // 86400))
    for p, series in per.items():
        worn = [d for d, v in series.items() if v >= 200]
        if len(worn) >= 14:
            stats["workout_day_share"].append(len(w_days[p] & set(worn)) / len(worn))
    nights = ds.table("truth_nights", columns=["patient_id", "asleep_seconds", "nap"])
    asleep: dict[str, list[float]] = defaultdict(list)
    for p, a, nap in zip(_col(nights, "patient_id"), _col(nights, "asleep_seconds"), _col(nights, "nap"), strict=True):
        if not nap and p in wearers:
            asleep[p].append(a / 60)
    stats["sleep_sd_minutes"] = [float(np.std(v)) for v in asleep.values() if len(v) >= 10]
    out = []
    for key, value in stats.items():
        if key not in refs or len(value) < 5:
            continue
        p10, med, p90 = refs[key]
        ours = [round(float(x), 3) for x in np.percentile(value, [10, 50, 90])]
        tolerance = max(abs(p90 - p10) * 0.5, 0.05)
        detail: dict[str, Any] = {"synthetic": ours, "lifesnaps": [p10, med, p90], "people": len(value)}
        if key in _EXPECTED_DYNAMICS_FAILURES:
            detail["expected_fail"] = _EXPECTED_DYNAMICS_FAILURES[key]
        out.append(_check(f"dynamics_{key}", abs(ours[1] - med) <= tolerance, **detail))
    return out
