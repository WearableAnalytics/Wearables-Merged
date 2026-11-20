"""Delivery layer: when records reach the platform store, and when the app can read them.

``created_at`` mirrors HealthKit's creationDate: native devices write close to real time
(with a heavy tail), companion apps write in delayed batches at their sync sessions, and
manually logged data lands later still. App enrollment, sync sessions and the Health
Connect history limit decide what our app can read and when; upload scheduling stays in
the replay workload.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..behavior.events import EventPlan
from ..behavior.timeline import Timeline
from ..timeutil import DAY, HOUR
from ..util import choice, lognormal, mixture


def companion_syncs(
    timeline: Timeline, plan: EventPlan, spec: Mapping[str, Any], rng: np.random.Generator, rate: float
) -> np.ndarray:
    times: list[np.ndarray] = []
    for i in range(len(plan.days)):
        if plan.offline[i]:
            continue
        wake, bed = timeline.wake[i], timeline.bed[i]
        k = rng.poisson(rate)
        if bed > wake and k:
            times.append(rng.uniform(wake, bed, k))
    return np.sort(np.concatenate(times)) if times else np.zeros(0)


def created_at(
    lag_class: str,
    archetype: str,
    start: np.ndarray,
    end: np.ndarray,
    *,
    timeline: Timeline,
    syncs: np.ndarray,
    params: Mapping[str, Any],
    rng: np.random.Generator,
    metric: str = "",
    model_delivery: Mapping[str, Any] | None = None,
) -> np.ndarray:
    """Platform-store write time. ``syncs`` are the companion app's HealthKit write sessions."""
    delivery = params["delivery"]
    n = end.size
    if n == 0:
        return np.zeros(0)
    if lag_class == "manual":
        return end + mixture(rng, delivery["manual"]["lag"], n)
    if archetype == "phone":
        spec = delivery["phone"]
        return end + mixture(rng, spec["gait_lag" if lag_class == "gait" else "lag"], n)
    # TODO(realism): Measure Fitbit Health Connect writes. The shared Android
    # companion policy currently uses assumed scheduling.
    # TODO: Fit companion-app write lag (backfill share and heavy tail) on Garmin Connect and Zepp data
    # and store it in params/delivery.toml.
    if archetype == "companion":
        if model_delivery and (lag := model_delivery["write_lag"].get(metric)):
            # One wait per measurement-day batch. Round writes to shared store sessions;
            # long deferred writes may land after the requested simulation window.
            day, group = np.unique(np.floor(end / DAY), return_inverse=True)
            ready = end + mixture(rng, lag, len(day))[group]
            bucket = model_delivery["write_bucket_seconds"]
            return np.ceil(ready / bucket) * bucket
        spec = delivery["companion"]
        if not len(syncs):
            return end + DAY * spec["max_backlog_days"]
        extra = spec.get("metric_extra_lag", {}).get(metric)
        ready = end + (mixture(rng, extra, n) if extra else 0.0)
        k = np.searchsorted(syncs, ready, side="left")
        late = k >= len(syncs)
        at = np.where(late, ready + DAY * spec["max_backlog_days"], syncs[np.clip(k, 0, len(syncs) - 1)])
        return np.maximum(at, end) + mixture(rng, spec["write_after_sync_seconds"], n)
    spec = delivery["native"]
    if lag_class == "after_wake":
        wake_times = np.asarray([night.out_of_bed for night in timeline.nights])
        k = np.searchsorted(wake_times, end, side="left")
        base = np.where(k < len(wake_times), wake_times[np.clip(k, 0, len(wake_times) - 1)], end)
        return np.maximum(base, end) + mixture(rng, spec["after_wake_lag"], n)
    if lag_class == "daily":
        return end + mixture(rng, spec["daily_lag"], n)
    lag = mixture(rng, spec.get("metric_lag", {}).get(metric, spec["lag"]), n)
    # Occasional offline batches: the watch was out of range and flushed later.
    batch = rng.random(n) < spec["offline_batch_probability"]
    lag = np.where(batch, lag + rng.uniform(0.5, 12.0, n) * HOUR, lag)
    return end + lag


@dataclass(slots=True)
class AppUsage:
    enrollment: float
    style: str
    history_permission: bool
    syncs: np.ndarray


def app_usage(
    timeline: Timeline,
    plan: EventPlan,
    window: tuple[float, float],
    platform: str,
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> AppUsage:
    """Sample enrollment, sync style, history permission and sync times for the platform's app. Offline days have
    no syncs.
    """
    spec = params["delivery"]["app"]
    lo, hi = window
    if rng.random() < spec["enrolled_before_window_probability"]:
        enrollment = lo - rng.uniform(1, 365) * DAY
    else:
        enrollment = lo + rng.uniform(0, spec["enrollment_window_fraction"]) * (hi - lo)
    style = choice(rng, spec["sync_style"])
    history = params["platforms"]["history"]
    permission = platform == "healthkit" or bool(rng.random() < history["health_connect_history_permission_share"])
    times: list[np.ndarray] = []
    for i in range(len(plan.days)):
        wake, bed = timeline.wake[i], timeline.bed[i]
        if bed <= wake or plan.offline[i]:
            continue
        if style == "background":
            k = rng.poisson(float(lognormal(rng, spec["background_syncs_per_day"])))
        elif style == "daily_open":
            k = 1 + rng.poisson(0.3)
        else:
            k = int(rng.random() < 1 / float(lognormal(rng, spec["occasional_open_every_days"])))
        if k:
            times.append(rng.uniform(wake, bed, k))
    syncs = np.sort(np.concatenate(times)) if times else np.zeros(0)
    syncs = syncs[(syncs >= max(lo, enrollment)) & (syncs < hi)]
    if enrollment >= lo:
        syncs = np.concatenate([[enrollment], syncs])  # initial backfill at enrollment
    return AppUsage(enrollment, style, permission, syncs)


def readable(
    end: np.ndarray, platform: Sequence[str] | np.ndarray, usage: AppUsage, params: Mapping[str, Any]
) -> np.ndarray:
    """Health Connect only exposes data from 30 days before the first grant without history permission."""
    days = params["platforms"]["history"]["health_connect_days"]
    limit = usage.enrollment - days * DAY
    hc = np.asarray(platform) == "health_connect"
    return ~hc | usage.history_permission | (end >= limit)
