"""Less frequent types: stair speed, audio exposure events, weekly AFib burden and gait
summaries, on-demand ECGs and GPS workout routes."""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import numpy as np

from ..physiology import ecg as ecg_model
from ..timeutil import DAY, MINUTE
from .context import Batch, DeviceContext
from .wear import quality

ROUTE_ACTIVITIES = frozenset({"walk", "run", "cycle", "hike"})


def _idx(dc: DeviceContext, times: np.ndarray) -> np.ndarray:
    return np.clip(np.searchsorted(dc.timeline.start, times, side="right") - 1, 0, len(dc.timeline.start) - 1)


def stairs(dc: DeviceContext, metric: str, spec: Mapping[str, Any]) -> list[Batch]:
    cols = dc.timeline.columns
    flights = cols["flights"]
    rows = np.flatnonzero(flights > 0)
    if not rows.size:
        return []
    rng = dc.rng
    counts = flights[rows].astype(int)
    k = np.repeat(rows, counts)
    t = cols["start"][k] + rng.random(k.size) * (cols["end"][k] - cols["start"][k])
    up = rng.random(k.size) < 0.5
    keep = (
        (up if metric == "stair_ascent_speed" else ~up) & dc.wear.worn(t) & (t >= dc.period.start) & (t < dc.period.end)
    )
    t, k = t[keep], k[keep]
    if not t.size:
        return []
    age = dc.persona.age
    base = 0.38 - 0.003 * max(0, age - 30) + (0.12 if metric == "stair_descent_speed" else 0.0)
    value = np.round(np.clip(base * np.exp(rng.normal(0, 0.15, t.size)), 0.1, 1.2), 3)
    duration = rng.uniform(4, 12, t.size)
    return [Batch(metric, t, t + duration, value, None, "interval", k)]


def audio_events(dc: DeviceContext, spec: Mapping[str, Any]) -> list[Batch]:
    cols = dc.timeline.columns
    loud = (cols["audio_db"] >= spec["threshold_db"]) & ((cols["end"] - cols["start"]) >= 3 * MINUTE)
    rows = np.flatnonzero(loud)
    if not rows.size:
        return []
    a = cols["start"][rows] + 3 * MINUTE
    keep = dc.wear.worn(a) & (a >= dc.period.start) & (a < dc.period.end)
    a, rows = a[keep], rows[keep]
    b = a + dc.rng.uniform(160, 180, a.size)
    return [
        Batch(
            "audio_exposure_event", a, b, np.full(a.size, np.nan), ["momentary_limit"] * int(a.size), "interval", rows
        )
    ]


def _weeks(dc: DeviceContext) -> list[tuple[float, float, int]]:
    out = []
    for i, day in enumerate(dc.plan.days):
        if day.weekday() == 0:
            zone = dc.tz.zone_for_day(day)
            start = dc.tz.local_to_utc(day, 0.0, zone)
            out.append((start, dc.tz.local_to_utc(day + timedelta(days=7), 0.0, zone), i))
    return out


def afib_weekly(dc: DeviceContext, spec: Mapping[str, Any]) -> list[Batch]:
    """AFib History: weekly burden written by the phone from a paired watch's readings."""
    if not dc.persona.afib_history or dc.has_native_watch is None:
        return []
    rows = []
    for a, b, i in _weeks(dc):
        samples = np.linspace(a, b, 7 * 24, endpoint=False)
        if dc.has_native_watch.worn(samples).mean() < 0.5:
            continue
        days = slice(i, min(i + 7, len(dc.plan.days)))
        burden = float(np.mean(dc.daily.afib_burden[days])) * 100
        value = round(max(0.0, burden + dc.rng.normal(0, 1.0) if burden else 0.0), 1)
        rows.append((a, b - 1, value, i))
    if not rows:
        return []
    a, b, v, d = (np.asarray([r[k] for r in rows]) for k in range(4))
    return [
        Batch(
            "afib_burden",
            a.astype(float),
            b.astype(float),
            v.astype(float),
            None,
            "day",
            d.astype(np.int64),
            lag_class="daily",
        )
    ]


def weekly_gait(dc: DeviceContext, metric: str, spec: Mapping[str, Any]) -> list[Batch]:
    cols = dc.timeline.columns
    walking = (cols["state"][dc.seg_idx] == 2) & dc.seg_on
    rows = []
    p = dc.persona
    for a, b, i in _weeks(dc):
        inside = walking & (dc.seg_start >= a) & (dc.seg_end <= b)
        seconds = float((dc.seg_end[inside] - dc.seg_start[inside]).sum())
        if seconds < spec.get("min_walking_minutes", 90.0) * 60:
            continue
        injured = bool(dc.plan.injury[i : i + 7].any())
        if metric == "walking_steadiness":
            value = 100 * (1 - 0.006 * max(0, p.age - 30)) - (12 if injured else 0) + dc.rng.normal(0, 3)
            value = round(float(np.clip(value, 5, 100)), 1)
        else:
            speed = float(np.median(cols["speed"][dc.seg_idx[inside]]))
            value = round(float(min(500.0, speed * 360 * (1 - 0.002 * max(0, p.age - 40)) + dc.rng.normal(0, 15))), 1)
        rows.append((a, b - 1, value, i))
    if not rows:
        return []
    a, b, v, d = (np.asarray([r[k] for r in rows]) for k in range(4))
    return [
        Batch(
            metric, a.astype(float), b.astype(float), v.astype(float), None, "day", d.astype(np.int64), lag_class="gait"
        )
    ]


def ecg_recordings(dc: DeviceContext, spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    rate = dc.persona.ecg_per_week
    if rate <= 0 or not len(dc.seg_start):
        return []
    rng = dc.rng
    still = dc.seg_on & (dc.seg_ctx == 2) & ((dc.seg_end - dc.seg_start) >= spec["seconds"] + 10)
    if not still.any():
        return []
    a, b = dc.seg_start[still], dc.seg_end[still]
    span = (dc.period.end if dc.period.end < dc.window[1] else dc.window[1]) - max(dc.period.start, dc.window[0])
    count = rng.poisson(rate * max(span, 0) / (7 * DAY))
    if not count:
        return []
    pick = rng.choice(a.size, size=count, p=(b - a) / (b - a).sum())
    starts = np.sort(a[pick] + rng.random(count) * (b[pick] - a[pick] - spec["seconds"]))
    out = []
    for t in starts:
        idx = _idx(dc, np.asarray([t]))
        q = float(quality(idx, dc.timeline, dc.traits, dc.day_noise, dc.signal, dc.winter)[0])
        q = min(1.0, q + 0.1)  # finger on the crown: better contact than optical
        mean_hr = float(dc.heart.deterministic(np.asarray([t + spec["seconds"] / 2]))[0])
        day = int(dc.timeline.columns["day"][idx[0]])
        afib = bool(rng.random() < min(1.0, dc.daily.afib_burden[day] * 4))
        out.append(
            {
                "start": float(np.floor(t)),
                "sampling_hz": float(spec["sampling_hz"]),
                "classification": ecg_model.classify(mean_hr, afib, q),
                "average_hr": round(mean_hr, 1),
                "truth_seq": int(idx[0]),
                "voltage_uv": ecg_model.waveform(
                    mean_hr, seconds=spec["seconds"], hz=spec["sampling_hz"], afib=afib, quality=q, rng=rng
                ),
            }
        )
    return out


def route(dc: DeviceContext, start: float, end: float, activity: str, seconds: float) -> dict[str, np.ndarray]:
    """GPS track from the truth speed profile, as a correlated random walk near home."""
    rng = dc.rng
    times = np.arange(start + rng.uniform(0, seconds), end, seconds)
    if not times.size:
        return {}
    idx = _idx(dc, times)
    speed = dc.timeline.columns["speed"][idx].astype(np.float64) * np.exp(rng.normal(0, 0.05, times.size))
    heading = np.cumsum(rng.normal(0, 0.08 if activity != "cycle" else 0.05, times.size)) + rng.uniform(0, 2 * np.pi)
    if times.size > 20:  # loop back towards the start in the second half
        heading[times.size // 2 :] += np.linspace(0, np.pi, times.size - times.size // 2)
    step = speed * seconds
    lat0 = dc.persona.latitude + rng.normal(0, 0.02)
    lon0 = dc.persona.longitude + rng.normal(0, 0.02)
    north = np.cumsum(step * np.cos(heading))
    east = np.cumsum(step * np.sin(heading))
    lat = lat0 + north / 111_320.0
    lon = lon0 + east / (111_320.0 * np.cos(np.radians(lat0)))
    elevation = 40 + np.cumsum(rng.normal(0, 0.3 if activity != "hike" else 1.2, times.size))
    accuracy = np.clip(rng.lognormal(np.log(4.0), 0.4, times.size), 1, 50)
    return {
        "time": times,
        "latitude": np.round(lat + rng.normal(0, accuracy / 111_320.0 / 3), 7),
        "longitude": np.round(lon, 7),
        "elevation_m": elevation.astype(np.float32),
        "speed_mps": speed.astype(np.float32),
        "course_deg": (np.degrees(heading) % 360).astype(np.float32),
        "horizontal_accuracy_m": accuracy.astype(np.float32),
    }
