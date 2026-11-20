"""Measurement policies: turn continuous truth into irregular device records.

Every emitter returns ``Batch`` objects for one metric. Sampling is a context-dependent
renewal process (lognormal mixtures fitted to the exports) or an exact clock grid where
the device genuinely produces one. Cumulative quantities are integrated exactly from the
truth rates over each record's interval. Derived metrics use the device's own samples.
"""

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from ..behavior.timeline import ACTIVITY_INDEX
from ..model import ASLEEP_STATES, COMMUTE, CONTEXTS, CTX_MOVING, CTX_SLEEP, CTX_STILL, CTX_WORKOUT, WALK
from ..physiology import hrv as hrv_model
from ..timeutil import DAY, HOUR, MINUTE
from ..util import mixture, mixture_mean
from .context import Batch, DeviceContext
from .wear import accept_probability, quality

CTX_ID = {name: i for i, name in enumerate(CONTEXTS)}
RUNNING = np.asarray([ACTIVITY_INDEX["run"]])
WALKING_ACTIVITIES = np.asarray([ACTIVITY_INDEX[a] for a in ("walk", "hike", "commute_walk")])


# Time helpers
def _runs(
    dc: DeviceContext, mask: np.ndarray, *, bridge: float = 0.0, any_context: bool = False
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Merge consecutive selected segments into runs (same context unless ``any_context``).

    ``bridge`` joins runs separated by short pauses, as devices accumulate across them.
    """
    if not mask.any():
        z = np.zeros(0)
        return z, z, np.zeros(0, dtype=np.int8)
    a, b, ctx = dc.seg_start[mask], dc.seg_end[mask], dc.seg_ctx[mask]
    breaks = np.ones(len(a), dtype=bool)
    gap_break = (a[1:] - b[:-1]) > bridge
    breaks[1:] = gap_break | (False if any_context else (ctx[1:] != ctx[:-1]))
    group = np.cumsum(breaks) - 1
    starts = a[breaks]
    ends = np.zeros(len(starts))
    np.maximum.at(ends, group, b)
    return starts, ends, ctx[breaks]


def _renewal(
    rng: np.random.Generator, starts: np.ndarray, ends: np.ndarray, components: Sequence[Sequence[float]]
) -> np.ndarray:
    lengths = ends - starts
    total = float(lengths.sum())
    if total <= 0:
        return np.zeros(0)
    mean = mixture_mean(components)
    positions: list[np.ndarray] = []
    offset = rng.uniform(0, mean)
    covered = offset
    first = np.asarray([offset])
    positions.append(first)
    while covered < total:
        n = int((total - covered) / mean * 1.2) + 32
        gaps = mixture(rng, components, n)
        pts = covered + np.cumsum(gaps)
        positions.append(pts)
        covered = float(pts[-1])
    u = np.concatenate(positions)
    u = u[u < total]
    edges = np.concatenate([[0.0], np.cumsum(lengths)])
    k = np.searchsorted(edges, u, side="right") - 1
    return starts[k] + (u - edges[k])


def _chunks(
    rng: np.random.Generator, starts: np.ndarray, ends: np.ndarray, spec: Sequence[float]
) -> tuple[np.ndarray, np.ndarray]:
    if not len(starts):
        z = np.zeros(0)
        return z, z
    median, sigma, cap = float(spec[0]), float(spec[1]), float(spec[2])
    lengths = ends - starts
    total = float(lengths.sum())
    mean = min(cap, median * np.exp(sigma**2 / 2))
    n = int(total / mean * 1.3) + len(starts) + 16
    draws = np.minimum(cap, np.exp(np.log(median) + sigma * rng.standard_normal(n)))
    cuts = np.cumsum(draws)
    while cuts[-1] < total:
        more = np.minimum(cap, np.exp(np.log(median) + sigma * rng.standard_normal(n)))
        cuts = np.concatenate([cuts, cuts[-1] + np.cumsum(more)])
    edges = np.concatenate([[0.0], np.cumsum(lengths)])
    marks = np.unique(np.concatenate([edges, cuts[cuts < total]]))
    a, b = marks[:-1], marks[1:]
    k = np.searchsorted(edges, a, side="right") - 1
    return starts[k] + (a - edges[k]), starts[k] + (b - edges[k])


def _grid(starts: np.ndarray, ends: np.ndarray, step: float, phase: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Clock-aligned buckets [k*step, (k+1)*step) overlapping the runs (clipped)."""
    if not len(starts):
        z = np.zeros(0)
        return z, z
    first = np.floor((starts - phase) / step).astype(np.int64)
    last = np.ceil((ends - phase) / step).astype(np.int64)
    counts = last - first
    base = np.repeat(first, counts) + (np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts))
    a = base * step + phase
    run = np.repeat(np.arange(len(starts)), counts)
    return np.maximum(a, starts[run]), np.minimum(a + step, ends[run])


def _grid_points(starts: np.ndarray, ends: np.ndarray, step: float, phase: float) -> np.ndarray:
    if not len(starts):
        return np.zeros(0)
    first = np.ceil((starts - phase) / step).astype(np.int64)
    last = np.ceil((ends - phase) / step).astype(np.int64)
    counts = np.maximum(last - first, 0)
    base = np.repeat(first, counts) + (np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts))
    return base * step + phase


def _idx(dc: DeviceContext, times: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(dc.timeline.start, times, side="right") - 1, 0, len(dc.timeline.start) - 1)


def _seg(dc: DeviceContext, times: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(dc.seg_start, times, side="right") - 1, 0, max(0, len(dc.seg_start) - 1))


def _energy_error(dc: DeviceContext, total: np.ndarray) -> np.ndarray:
    """Active energy as reported: a per-device multiplicative bias and per-record log-normal error."""
    return total * dc.energy_bias * np.exp(dc.rng.normal(0, dc.signal["energy_noise_sigma"], len(total)))


def _round(values: np.ndarray, precision: float) -> np.ndarray:
    return np.round(values / precision) * precision if precision else values


def sample_times(dc: DeviceContext, spec: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Candidate sample times and their segment indices for a ``samples``/``hrv`` policy."""
    if not len(dc.seg_start):
        z = np.zeros(0)
        return z, z.astype(np.int64)
    rng = dc.rng
    if "grid_seconds" in spec:
        step = float(spec["grid_seconds"])
        starts, ends, _ = _runs(dc, dc.seg_on)
        times = _grid_points(starts, ends, step, float(dc.grid_phase % step))
        if burst := spec.get("grid_burst"):
            block = burst["block_seconds"]
            spacing = burst["sample_seconds"]
            phase = float(dc.grid_phase % step)
            first = int(np.floor((dc.seg_start[0] - phase) / block))
            last = int(np.ceil((dc.seg_end[-1] - phase) / block))
            blocks = np.arange(first, last)
            days, group = np.unique(np.floor(blocks * block / DAY), return_inverse=True)
            burst_days = (rng.random(len(days)) < burst["day_probability"])[group]
            active = blocks[burst_days & (rng.random(len(blocks)) < burst["block_probability"])]
            dense = active[:, None] * block + phase + np.arange(0, block, spacing)
            dense = dense.ravel()
            dense = dense[(dense >= dc.seg_start[0]) & (dense < dc.seg_end[-1])]
            times = np.union1d(times, dense)
        if (probability := spec.get("grid_active_hour_probability", 1.0)) < 1.0:
            hours, group = np.unique(np.floor(times / HOUR), return_inverse=True)
            times = times[(rng.random(len(hours)) < probability)[group]]
    else:
        parts = []
        for name, components in spec["cadence"].items():
            c = CTX_ID[name]
            starts, ends, _ = _runs(dc, dc.seg_on & (dc.seg_ctx == c))
            parts.append(_renewal(rng, starts, ends, components))
        times = np.sort(np.concatenate(parts)) if parts else np.zeros(0)
    seg = _seg(dc, times)
    keep = dc.seg_on[seg] if len(times) else np.zeros(0, dtype=bool)
    return times[keep], seg[keep]


def plan_heart_rate(dc: DeviceContext, spec: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sample heart-rate timestamps and drop those rejected by signal quality. Returns times, segment indices and
    quality.
    """
    times, seg = sample_times(dc, spec)
    idx = dc.seg_idx[seg]
    q = quality(idx, dc.timeline, dc.traits, dc.day_noise, dc.signal, dc.winter)
    if spec.get("quality", False) and len(times):
        keep = dc.rng.random(len(times)) < accept_probability(q, dc.signal)
        times, seg, q = times[keep], seg[keep], q[keep]
    return times, seg, q


# TODO(realism): Not modelled yet: per-wearer heart-rate bias, timestamp lag errors and sustained dropouts, SpO2
# error that grows at low saturation, and device-level differences in energy error.
def finish_heart_rate(dc: DeviceContext, times: np.ndarray, seg: np.ndarray, q: np.ndarray, truth: np.ndarray) -> Batch:
    """Add measurement error to the true heart rate (quality-scaled noise, motion error, outliers, cadence lock),
    round it and build the batch.
    """
    signal = dc.signal
    rng = dc.rng
    idx = dc.seg_idx[seg]
    cols = dc.timeline.columns
    noise = rng.normal(0, 1.0, len(times)) * (1 + signal["noise_multiplier"] * (1 - q))
    # Optical error grows with arm motion and with the HR itself, and sporadic large misreads
    # (motion artefact, crosstalk) give the error distribution heavier tails than a Gaussian.
    noise += rng.normal(0, 1.0, len(times)) * signal["hr_motion_error_fraction"] * truth * cols["arm"][idx]
    outlier = rng.random(len(times)) < signal["hr_outlier_probability"] * (1 + 4 * (1 - q))
    noise += outlier * rng.normal(0, signal["hr_outlier_sigma"], len(times))
    value = truth + noise
    running = np.isin(cols["activity"][idx], RUNNING) & (dc.seg_ctx[seg] != CTX_SLEEP)
    lock = (
        running & (q < signal["cadence_lock_quality"]) & (rng.random(len(times)) < signal["cadence_lock_probability"])
    )
    value = np.where(lock, cols["cadence"][idx] * (1 + rng.normal(0, 0.01, len(times))), value)
    value = np.round(np.clip(value, 30, 230))
    end = times.copy()
    spec = dc.spec["metrics"]["heart_rate"]
    if duration := spec.get("grid_interval_seconds"):
        step = spec["grid_seconds"]
        phase = float(dc.grid_phase % step)
        point = np.rint((times - phase) / step) * step + phase
        end = np.minimum(end + np.where(np.abs(times - point) < 1e-5, duration, 0), dc.period.end)
    return Batch("heart_rate", times, end, value, None, "interval", idx)


def respiratory_or_spo2(dc: DeviceContext, metric: str, spec: Mapping[str, Any]) -> list[Batch]:
    times, seg = sample_times(dc, spec)
    if not len(times):
        return []
    idx = dc.seg_idx[seg]
    q = quality(idx, dc.timeline, dc.traits, dc.day_noise, dc.signal, dc.winter)
    keep = dc.rng.random(len(times)) < accept_probability(q, dc.signal)
    times, idx = times[keep], idx[keep]
    cols = dc.timeline.columns
    day = cols["day"][idx]
    asleep = np.isin(cols["state"][idx], list(ASLEEP_STATES))
    phys = dc.params["physiology"]
    rng = dc.rng
    if metric == "respiratory_rate":
        value = (
            dc.persona.respiratory_rate
            + dc.daily.respiratory_delta[day]
            + np.where(asleep, phys["respiration"]["sleep_delta"], 0)
        )
        value += rng.normal(0, phys["respiration"]["noise_sigma"], len(times))
        value = np.clip(value, 6, 40)
        lag = "after_wake"
    else:
        value = (
            dc.persona.spo2
            + dc.daily.spo2_delta[day]
            + np.where(asleep, phys["spo2"]["sleep_delta"] + dc.daily.spo2_sleep_delta[day], 0)
        )
        value = value + dc.signal["spo2_bias"] + rng.normal(0, dc.signal["spo2_error_sigma"], len(times))
        value = np.clip(value + rng.normal(0, phys["spo2"]["noise_sigma"], len(times)), 80, 100)
        lag = "default"
    value = _round(value, float(spec.get("precision", 0.1)))
    return [Batch(metric, times, times.copy(), value, None, "interval", idx, lag_class=lag)]


# Cumulative records
def _active_mask(dc: DeviceContext, rate: np.ndarray, spec: Mapping[str, Any]) -> np.ndarray:
    mask = dc.seg_on.copy()
    if spec.get("active_only", False):
        mask &= rate[dc.seg_idx] > 0
    if "workout_types" in spec:
        allowed = np.asarray([ACTIVITY_INDEX[t] for t in spec["workout_types"]])
        mask &= (dc.seg_ctx == CTX_WORKOUT) & np.isin(dc.timeline.columns["activity"][dc.seg_idx], allowed)
    return mask


def chunks(
    dc: DeviceContext, metric: str, quantity: str, spec: Mapping[str, Any], *, mean: bool = False
) -> list[Batch]:
    """Records of a cumulative quantity (steps, distance, energy): the true rate integrated over chunks or grid cells
    defined by the device spec.
    """
    if not len(dc.seg_start):
        return []
    rate = dc.rate(quantity)
    mask = _active_mask(dc, rate, spec)
    if spec.get("without_watch") and dc.has_native_watch is not None:
        mask &= ~dc.has_native_watch.worn((dc.seg_start + dc.seg_end) / 2)
    pieces_a, pieces_b = [], []
    if "grid_seconds" in spec:
        starts, ends, _ = _runs(dc, mask)
        a, b = _grid(starts, ends, float(spec["grid_seconds"]))
        pieces_a.append(a)
        pieces_b.append(b)
    elif "chunk_all" in spec:
        starts, ends, _ = _runs(dc, mask, bridge=float(spec.get("bridge_seconds", 0.0)), any_context=True)
        a, b = _chunks(dc.rng, starts, ends, spec["chunk_all"])
        pieces_a.append(a)
        pieces_b.append(b)
    else:
        for name, chunk_spec in spec["chunk"].items():
            starts, ends, _ = _runs(
                dc, mask & (dc.seg_ctx == CTX_ID[name]), bridge=float(spec.get("bridge_seconds", 0.0))
            )
            a, b = _chunks(dc.rng, starts, ends, chunk_spec)
            pieces_a.append(a)
            pieces_b.append(b)
    a = np.concatenate(pieces_a) if pieces_a else np.zeros(0)
    b = np.concatenate(pieces_b) if pieces_b else np.zeros(0)
    if not len(a):
        return []
    order = np.argsort(a)
    a, b = a[order], b[order]
    if "grid_seconds" in spec:
        # Grid buckets from neighbouring runs may repeat; merge identical buckets.
        step = float(spec["grid_seconds"])
        key = np.floor(a / step)
        first = np.ones(len(a), dtype=bool)
        first[1:] = key[1:] != key[:-1]
        group = np.cumsum(first) - 1
        a = np.floor(a[first] / step) * step
        b = a + step
        del group
    total = dc.integral(rate, a, b)
    if mean:
        on = dc.integral(np.ones_like(rate), a, b)
        value = np.where(on > 0, total / np.maximum(on, 1e-9), np.nan)
        value = _round(value, 0.1) if quantity == "met" else _round(value, 0.01)
    else:
        if quantity == "steps":
            day = dc.timeline.columns["day"][_idx(dc, a)]
            total = np.floor(total * dc.step_bias * dc.step_day[day] + dc.rng.random(len(total)))
        elif quantity == "active_energy":
            total = np.round(_energy_error(dc, total), 3)
        elif quantity == "flights_climbed":
            total = np.floor(total + dc.rng.random(len(total)))
        elif quantity == "daylight":
            total = np.round(total)
        else:
            total = np.round(total, 3)
        value = total
    keep = np.isfinite(value) & (value > 0)
    end_offset = float(spec.get("end_offset_seconds", 0.0))
    a, b, value = a[keep], b[keep] + end_offset, value[keep]
    return [Batch(metric, a, b, value, None, "interval", _idx(dc, a), lag_class="default")]


def sync_chunks(dc: DeviceContext, metric: str, quantity: str, spec: Mapping[str, Any]) -> list[Batch]:
    """Companion apps write deltas covering the time since the previous sync (split at midnight)."""
    if not len(dc.seg_start):
        return []
    rate = dc.rate(quantity)
    lo, hi = dc.seg_start[0], dc.seg_end[-1]
    days = dc.plan.days
    midnights = np.asarray([dc.tz.local_to_utc(d, 0.0, dc.tz.zone_for_day(d)) for d in days])
    syncs = dc.sync_times if not spec.get("daily") else np.zeros(0)
    marks = np.unique(np.clip(np.concatenate([midnights, syncs, [lo, hi]]), lo, hi))
    a, b = marks[:-1], marks[1:]
    on_only = quantity != "basal_energy"
    total = dc.integral(rate, a, b, on_only=on_only)
    if quantity == "steps":
        total = np.floor(total)
    elif quantity == "flights_climbed":
        total = np.floor(total + dc.rng.random(len(total)))
    elif quantity == "active_energy":
        total = np.round(_energy_error(dc, total), 3)
    else:
        total = np.round(total, 3)
    worn = dc.integral(np.ones_like(rate), a, b) > 0
    keep = worn & (total > 0)
    at_midnight = np.isin(b, midnights)
    b = np.where(at_midnight, b - 1, b)
    return [Batch(metric, a[keep], b[keep], total[keep], None, "interval", _idx(dc, a[keep]))]


def minute_grid(dc: DeviceContext, spec: Mapping[str, Any]) -> list[Batch]:
    cols = dc.timeline.columns
    mask = dc.seg_on & (cols["met"][dc.seg_idx] >= spec["min_met"])
    starts, ends, _ = _runs(dc, mask)
    a, b = _grid(starts, ends, MINUTE)
    full = (b - a) >= MINUTE - 1e-6
    a = a[full]
    if not len(a):
        return []
    return [Batch("exercise_time", a, a + MINUTE, np.ones(len(a)), None, "interval", _idx(dc, a))]


def stand(dc: DeviceContext, spec: Mapping[str, Any]) -> list[Batch]:
    """Stand-hour records: one per waking hour, "stood" if upright long enough, else "idle"."""
    if not len(dc.seg_start):
        return []
    upright = dc.rate("upright")
    out: list[Batch] = []
    hours_a: list[np.ndarray] = []
    for i, day in enumerate(dc.plan.days):
        zone = dc.tz.zone_for_day(day)
        wake, bed = dc.timeline.wake[i], dc.timeline.bed[i]
        h0 = dc.tz.local_to_utc(day, 0.0, zone)
        hours = h0 + np.arange(24) * HOUR
        hours = hours[(hours + HOUR > wake) & (hours < bed)]
        hours_a.append(hours)
    a = np.concatenate(hours_a) if hours_a else np.zeros(0)
    if not len(a):
        return []
    b = a + HOUR
    on = dc.integral(np.ones_like(upright), a, b)
    a, b = a[on > 0.5 * HOUR], b[on > 0.5 * HOUR]
    stood = dc.integral(upright, a, b) >= spec["min_upright_minutes"] * MINUTE
    categories: list[str | None] = ["stood" if s else "idle" for s in stood]
    out.append(
        Batch("stand_hour", a, b, np.full(len(a), np.nan), categories, "interval", _idx(dc, a), lag_class="hour")
    )
    # Five-minute stand time.
    starts, ends, _ = _runs(dc, dc.seg_on & (upright[dc.seg_idx] > 0))
    ga, _gb = _grid(starts, ends, 300.0)
    ga = np.unique(np.floor(ga / 300.0) * 300.0)
    minutes = np.floor(dc.integral(upright, ga, ga + 300.0) / MINUTE)
    keep = minutes >= 1
    out.append(
        Batch(
            "stand_time", ga[keep], ga[keep] + 300.0, np.minimum(minutes[keep], 5), None, "interval", _idx(dc, ga[keep])
        )
    )
    return out


def hrv(dc: DeviceContext, spec: Mapping[str, Any], hrv_truth: list[dict[str, Any]]) -> list[Batch]:
    phys = dc.params["physiology"]
    window = float(phys["hrv"]["window_seconds"])
    times, seg = sample_times(dc, spec)
    if spec.get("nightly_only"):
        keep = dc.seg_ctx[seg] == CTX_SLEEP
        times, seg = times[keep], seg[keep]
    if not len(times):
        return []
    idx = dc.seg_idx[seg]
    cols = dc.timeline.columns
    # Measurements need stillness, enough wear time left and adequate signal quality.
    q = quality(idx, dc.timeline, dc.traits, dc.day_noise, dc.signal, dc.winter)
    ok = (q >= dc.signal["hrv_min_quality"]) & np.isin(dc.seg_ctx[seg], (CTX_SLEEP, CTX_STILL))
    ok &= dc.seg_end[seg] - times >= window
    times, idx, q = times[ok], idx[ok], q[ok]
    if not len(times):
        return []
    day = cols["day"][idx]
    asleep = np.isin(cols["state"][idx], list(ASLEEP_STATES))
    rng = dc.rng
    ln = dc.daily.ln_rmssd[day] + np.where(
        asleep, phys["hrv"]["sleep_ln_rmssd_delta"], phys["hrv"]["awake_ln_rmssd_delta"]
    )
    ln += rng.normal(0, 0.12, len(times))
    mean_hr = dc.heart.deterministic(times + window / 2)
    resp = dc.persona.respiratory_rate + np.where(asleep, phys["respiration"]["sleep_delta"], 0.0)
    windows = hrv_model.simulate(mean_hr, np.exp(ln), resp, dc.persona.lf_hf_ratio, dc.params, rng)
    base = len(hrv_truth)
    for k in range(len(times)):
        hrv_truth.append(
            {
                "seq": base + k,
                "start": float(times[k]),
                "end": float(times[k] + window),
                "device_id": dc.period.device_id,
                "mean_hr": float(mean_hr[k]),
                "rmssd": float(windows.rmssd[k]),
                "sdnn": float(windows.sdnn[k]),
                "beats": int(windows.count[k]),
            }
        )
    seqs = base + np.arange(len(times))
    # Device error: a per-model bias and spread (log scale), plus missed beats that inflate both
    # metrics at low quality.
    signal = dc.signal
    artefact = np.exp(signal["hrv_bias"] + rng.normal(0, signal["hrv_error_sigma"], len(times))) * (
        1 + np.clip((0.9 - q).clip(0) * 0.2, 0, 0.5)
    )
    out = []
    ends = times + window - rng.uniform(0, 12, len(times)) * (rng.random(len(times)) < 0.2)
    sdnn_gate = dc.gate("hrv_sdnn", times)
    if sdnn_gate.any():
        out.append(
            Batch(
                "hrv_sdnn",
                times[sdnn_gate],
                ends[sdnn_gate],
                np.round(windows.sdnn * artefact, 3)[sdnn_gate],
                None,
                "hrv_window",
                seqs[sdnn_gate],
            )
        )
    if dc.spec.get("writes_rmssd", False):
        gate = dc.gate("hrv_rmssd", times)
        if gate.any():
            out.append(
                Batch(
                    "hrv_rmssd",
                    times[gate],
                    ends[gate],
                    np.round(windows.rmssd * artefact, 3)[gate],
                    None,
                    "hrv_window",
                    seqs[gate],
                )
            )
    return out


def daily(dc: DeviceContext, metric: str, spec: Mapping[str, Any], hr: Batch | None) -> list[Batch]:
    """Daily metrics derived from the device's own heart-rate samples, computed by the spec's method (for example
    resting heart rate).
    """
    if hr is None or not len(hr):
        return []
    cols = dc.timeline.columns
    idx = hr.truth_seq
    assert idx is not None
    # Attribute samples to the local calendar day they were taken on.
    local = np.floor((hr.start + dc.tz.offsets(hr.start).astype(np.float64) * 60) / DAY).astype(np.int64)
    epoch_day = dc.plan.days[0].toordinal() - 719163
    day = local - epoch_day
    valid = (day >= 0) & (day < len(dc.plan.days))
    day = np.where(valid, day, -1)
    state = cols["state"][idx]
    seg = _seg(dc, hr.start)
    ctx = dc.seg_ctx[seg]
    starts, ends, values, days = [], [], [], []
    method = spec["method"]
    for d in np.unique(day[day >= 0]):
        sel = day == d
        local_day = dc.plan.days[int(d)]
        midnight = dc.tz.local_to_utc(local_day, 0.0, dc.tz.zone_for_day(local_day))
        if method == "awake_still_low_quantile":
            v = hr.value[sel & (ctx == CTX_STILL)]
            if len(v) < 10:
                continue
            low = v[v <= np.quantile(v, 0.1)]
            value = float(np.round(low.mean()))
            starts.append(midnight)
            ends.append(float(hr.start[sel].max()))
        elif method == "lowest_30min_mean":
            t, v = hr.start[sel], hr.value[sel]
            if len(v) < 20:
                continue
            bins = np.floor((t - midnight) / 1800).astype(int)
            inside = (bins >= 0) & (bins < 50)
            if not inside.any():
                continue
            sums = np.bincount(bins[inside], weights=v[inside])
            counts = np.bincount(bins[inside])
            # A bin needs at least two samples (10-minute background cadence gives three);
            # requiring more would leave only dense workout bins and bias RHR upwards.
            enough = counts >= 2
            means = sums[enough] / counts[enough]
            if not len(means):
                continue
            value = float(np.round(means.min()))
            starts.append(midnight)
            ends.append(midnight)
        elif method == "walking_mean":
            walking = (state == WALK) | ((state == COMMUTE) & np.isin(cols["activity"][idx], WALKING_ACTIVITIES))
            v = hr.value[sel & walking & (ctx == CTX_MOVING)]
            if len(v) < 5:
                continue
            value = float(np.round(v.mean(), 1))
            starts.append(float(hr.start[sel].min()))
            ends.append(float(hr.start[sel].max()))
        else:
            raise ValueError(method)
        values.append(value)
        days.append(int(d))
    if not values:
        return []
    return [
        Batch(
            metric,
            np.asarray(starts),
            np.asarray(ends),
            np.asarray(values),
            None,
            "day",
            np.asarray(days),
            lag_class="daily",
        )
    ]


def nightly(dc: DeviceContext, metric: str, spec: Mapping[str, Any]) -> list[Batch]:
    """One record per main sleep with enough sleep and wear (wrist temperature, breathing disturbances)."""
    rows = []
    for night in dc.timeline.nights:
        if night.nap or not (dc.period.start <= night.onset and night.wake <= dc.period.end):
            continue
        if night.asleep_seconds < 4 * HOUR or dc.wear.worn_fraction(night.onset, night.wake) < 0.85:
            continue
        if not dc.gate(metric, np.asarray([night.wake]), spec.get("feature"))[0]:
            continue
        d = min(night.day, len(dc.plan.days) - 1)
        if metric == "wrist_temperature":
            value = (
                dc.persona.wrist_temperature
                + dc.daily.temperature_delta[d]
                + dc.rng.normal(0, dc.params["physiology"]["temperature"]["night_sigma"])
            )
            value = round(float(value), 2)
        else:
            value = round(float(dc.rng.lognormal(np.log(2.5 + dc.daily.breathing_disturbances[d]), 0.35)), 2)
        rows.append((night.onset, night.wake, value, night.id))
    if not rows:
        return []
    a = np.asarray([r[0] for r in rows], dtype=float)
    b = np.asarray([r[1] for r in rows], dtype=float)
    v = np.asarray([r[2] for r in rows], dtype=float)
    s = np.asarray([r[3] for r in rows], dtype=np.int64)
    return [Batch(metric, a, b, v, None, "night", s, lag_class="after_wake")]


LABELS = ("awake", "asleep_core", "asleep_deep", "asleep_rem")


def sleep(dc: DeviceContext, spec: Mapping[str, Any]) -> list[Batch]:
    """Sleep records: true stages passed through the model's confusion matrix, short awake spells merged, naps only
    where the device detects them.
    """
    cols = dc.timeline.columns
    confusion = np.asarray(dc.spec["sleep_confusion"]["matrix"], dtype=float)
    epoch = float(spec.get("epoch_seconds", 30.0))
    merge_awake = float(spec["merge_awake_under_minutes"]) * MINUTE
    rng = dc.rng
    starts, ends, cats, seqs = [], [], [], []
    for night in dc.timeline.nights:
        if not (dc.period.start <= night.in_bed and night.out_of_bed <= dc.period.end):
            continue
        if night.nap and (
            not spec.get("naps") or night.asleep_seconds < float(spec.get("min_nap_minutes", 15.0)) * MINUTE
        ):
            continue  # Apple Watch only tracks scheduled sleep; others detect naps
        if dc.wear.worn_fraction(night.onset, night.wake) < 0.7:
            continue
        rows = np.flatnonzero(cols["night"] == night.id)
        if not len(rows):
            continue
        true_state = cols["state"][rows] - 5  # 0 awake, 1 light, 2 deep, 3 rem
        a, b = cols["start"][rows], cols["end"][rows]
        if spec.get("in_bed"):
            starts.append(night.in_bed)
            ends.append(night.out_of_bed)
            cats.append("in_bed")
            seqs.append(night.id)
        # Devices detect sleep from onset (minus a little) to final wake; drop out-of-bed tail.
        inside = (b > night.onset - 5 * MINUTE) & (a < night.wake)
        a, b, true_state = a[inside], b[inside], true_state[inside]
        if not len(a):
            continue
        a[0] = max(a[0], night.onset - rng.uniform(0, 8) * MINUTE)
        b[-1] = min(b[-1], night.wake + rng.uniform(-3, 6) * MINUTE)
        if rng.random() < spec["unspecified_probability"]:
            starts.append(a[0])
            ends.append(b[-1])
            cats.append("asleep_unspecified")
            seqs.append(night.id)
            continue
        # Classify sub-epochs of each true stage so misclassification fragments the night.
        relabel = float(spec.get("relabel_minutes", 0.0)) * MINUTE
        if relabel > 0:
            pieces = []
            for x, y, st in zip(a, b, true_state, strict=True):
                n = max(1, int(np.ceil((y - x) / (relabel * float(np.exp(rng.normal(0, 0.6)))))))
                edges = np.linspace(x, y, n + 1)
                pieces.extend((edges[j], edges[j + 1], st) for j in range(n))
            a = np.asarray([p_[0] for p_ in pieces])
            b = np.asarray([p_[1] for p_ in pieces])
            true_state = np.asarray([p_[2] for p_ in pieces])
        cdf = np.cumsum(confusion / confusion.sum(axis=1, keepdims=True), axis=1)
        labels = (rng.random(len(true_state))[:, None] > cdf[true_state]).sum(axis=1)
        # Quantize boundaries to the device epoch and merge equal neighbours.
        origin = a[0]
        qa = origin + np.round((a - origin) / epoch) * epoch
        qb = origin + np.round((b - origin) / epoch) * epoch
        keep = qb > qa
        qa, qb, labels = qa[keep], qb[keep], labels[keep]
        merged: list[list[Any]] = []
        for x, y, lab in zip(qa, qb, labels, strict=True):
            if merged and (merged[-1][2] == lab or (lab == 0 and y - x < merge_awake)):
                merged[-1][1] = y
            else:
                merged.append([x, y, lab])
        for x, y, lab in merged:
            starts.append(float(x))
            ends.append(float(y))
            cats.append(LABELS[int(lab)])
            seqs.append(night.id)
    if not starts:
        return []
    return [
        Batch(
            "sleep",
            np.asarray(starts),
            np.asarray(ends),
            np.full(len(starts), np.nan),
            cats,
            "night",
            np.asarray(seqs, dtype=np.int64),
            lag_class="after_wake",
        )
    ]


# Gait (phone)
def bout(dc: DeviceContext, metric: str, spec: Mapping[str, Any]) -> list[Batch]:
    cols = dc.timeline.columns
    walking = (cols["state"][dc.seg_idx] == WALK) | np.isin(cols["activity"][dc.seg_idx], WALKING_ACTIVITIES)
    starts, ends, _ = _runs(dc, dc.seg_on & walking)
    long = (ends - starts) >= spec["min_bout_seconds"]
    starts, ends = starts[long], ends[long]
    a, b = _chunks(dc.rng, starts, ends, spec["chunk"])
    if not len(a):
        return []
    rng = dc.rng
    keep = (rng.random(len(a)) < 0.55) & ((b - a) >= 2)
    a, b = a[keep], b[keep]
    idx = _idx(dc, a)
    p = dc.persona
    speed = cols["speed"][idx].astype(float)
    injured = dc.plan.injury[cols["day"][idx]]
    if metric == "walking_speed":
        value = np.round(speed * np.exp(rng.normal(0, 0.05, len(a))), 3)
    elif metric == "walking_step_length":
        value = np.round(p.stride_m * np.exp(rng.normal(0, 0.04, len(a))), 3)
    elif metric == "walking_double_support":
        value = np.round(np.clip(p.double_support_pct + rng.normal(0, 1.2, len(a)), 15, 45), 1)
    else:
        delta = dc.params["behavior"]["events"]["injury"]["gait_asymmetry_delta"]
        value = np.round(np.clip(p.asymmetry_pct + injured * delta + rng.exponential(1.0, len(a)) - 1, 0, 60), 1)
    return [Batch(metric, a, b, value, None, "interval", idx, lag_class="gait")]
