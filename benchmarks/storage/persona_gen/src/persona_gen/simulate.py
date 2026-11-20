"""Simulate one persona end to end: persona -> events -> daily state -> behaviour ->
physiology -> devices -> platforms -> delivery. Returns storage-neutral columnar tables."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np

from .behavior.events import plan_events, zone_timeline
from .behavior.timeline import ACTIVITIES, build_timeline
from .config import Params
from .delivery import app_usage, companion_syncs, created_at, readable
from .devices.context import Batch, DeviceContext
from .devices.emit import (
    bout,
    chunks,
    finish_heart_rate,
    hrv,
    minute_grid,
    nightly,
    plan_heart_rate,
    respiratory_or_spo2,
    sleep,
    stand,
    sync_chunks,
)
from .devices.emit import (
    daily as daily_metric,
)
from .devices.extras import afib_weekly, audio_events, ecg_recordings, stairs, weekly_gait
from .devices.manual import manual_batches
from .devices.ownership import DevicePeriod, plan_devices
from .devices.wear import Wear, signal_traits, wear_timeline
from .devices.workout_records import workout_rows, workout_totals
from .model import STATE_NAMES, Coded, Event
from .persona.sampler import Persona, PersonaContext, sample_persona
from .physiology.daily import base_state, finalize
from .physiology.heart import HeartModel
from .rng import Streams
from .timeutil import DAY, utc_seconds
from .util import lognormal

CHUNK_QUANTITY = {
    "steps": "steps",
    "distance_walking_running": "distance_walking_running",
    "distance_cycling": "distance_cycling",
    "active_energy": "active_energy",
    "basal_energy": "basal_energy",
    "flights_climbed": "flights_climbed",
}
MEAN_SIGNAL = {"physical_effort": "met", "environmental_audio": "audio", "headphone_audio": "headphones"}
METRIC_NAME = {"daylight": "time_in_daylight"}


@dataclass(frozen=True, slots=True)
class SimulationContext:
    """Run-level settings for ``simulate_persona``: parameters, seed, window, twin mode, persona context, metric
    whitelist and everyday-events switch.
    """

    params: Params
    seed: int
    start: date
    days: int
    twins: bool
    persona_context: PersonaContext
    # TODO: store_rr is passed through but nothing reads it yet; RR windows are not written to the output.
    store_rr: bool = False
    # Whitelist of metric names to emit; None emits all. No CLI option sets it yet.
    metrics: frozenset[str] | None = None
    everyday_events: bool = True  # False: no illness, injury, mood episodes or travel


class _Coverage:
    def __init__(self, parts: list[tuple[DevicePeriod, Wear]]) -> None:
        self.parts = parts

    def worn(self, times: np.ndarray) -> np.ndarray:
        out = np.zeros(times.shape, dtype=bool)
        for period, wear in self.parts:
            out |= (times >= period.start) & (times < period.end) & wear.worn(times)
        return out


def _uuids(rng: np.random.Generator, n: int) -> np.ndarray:
    if n == 0:
        return np.zeros(0, dtype="S36")
    raw = rng.integers(0, 256, size=(n, 16), dtype=np.uint8)
    raw[:, 6] = (raw[:, 6] & 0x0F) | 0x40
    raw[:, 8] = (raw[:, 8] & 0x3F) | 0x80
    hexdigits = np.frombuffer(b"0123456789ABCDEF", dtype=np.uint8)
    chars = np.empty((n, 32), dtype=np.uint8)
    chars[:, 0::2] = hexdigits[raw >> 4]
    chars[:, 1::2] = hexdigits[raw & 0x0F]
    dash = np.full((n, 1), ord("-"), dtype=np.uint8)
    out = np.concatenate(
        [chars[:, :8], dash, chars[:, 8:12], dash, chars[:, 12:16], dash, chars[:, 16:20], dash, chars[:, 20:]], axis=1
    )
    return out.view("S36").ravel()


def _os_adoption(params: Params, platform: str, rng: np.random.Generator) -> dict[str, float]:
    spec = params["platforms"]["ios" if platform == "healthkit" else "android"]
    lag = float(lognormal(rng, spec["adoption_lag_days"])) * DAY
    adoption = {"lag": lag}
    for version, released in spec["releases"]:
        adoption[str(version)] = utc_seconds(date.fromisoformat(released)) + lag
    return adoption


def simulate_persona(index: int, ctx: SimulationContext) -> dict[str, dict[str, Any]]:
    params = ctx.params
    streams = Streams(ctx.seed, index)
    persona = sample_persona(index, ctx.persona_context)
    if persona.anchor_kind == "twin":
        _calibrate_twin(persona, ctx, streams)
    w0 = utc_seconds(ctx.start)
    w1 = w0 + ctx.days * DAY
    days = [ctx.start + timedelta(days=k) for k in range(-1, ctx.days + 1)]
    plan = plan_events(persona, days, params, streams("events"), everyday=ctx.everyday_events)
    tz = zone_timeline(persona, plan)
    daily = base_state(persona, plan, params, streams("daily"))
    timeline = build_timeline(persona, daily, plan, tz, params, streams("behavior"))
    finalize(daily, persona, params, timeline.hard_workout)
    offsets = tz.offsets(timeline.start)
    heart = HeartModel(persona, timeline, daily, offsets, params)
    periods, device_events = plan_devices(persona, (w0, w1), params, streams("devices"))
    traits = signal_traits(persona, params, streams("signal"))
    traits["vo2_bias"] = float(np.exp(streams("signal", "vo2").normal(0, 0.04)))
    traits["headphone_level"] = float(streams("signal", "audio").normal())
    phone_platform = next(p.platform for p in periods if p.role == "phone")
    os_adoption = _os_adoption(params, phone_platform, streams("os"))
    usage = app_usage(timeline, plan, (w0, w1), phone_platform, params, streams("app"))
    allowed = ctx.metrics

    contexts: list[DeviceContext] = []
    recorded_kinds = ("watch", "tracker")
    native: list[tuple[DevicePeriod, Wear]] = []
    for k, period in enumerate(sorted(periods, key=lambda p: (p.role != "wearable", p.start))):
        rng = streams("device", k)
        if period.role == "wearable":
            wear = wear_timeline(persona, period, timeline, daily, plan, tz, traits, params, rng)
        else:
            wear = Wear(np.zeros(0), np.zeros(0), [])
        dc = DeviceContext(
            persona, period, timeline, daily, plan, tz, heart, wear, traits, params, rng, os_adoption, (w0, w1)
        )
        recorder = period.role == "wearable" and period.spec["kind"] in recorded_kinds and period.reason != "second"
        dc.prepare(recorder)
        if period.archetype == "companion" and "delivery" not in period.spec:
            companion = params["delivery"]["companion"]
            rate = float(lognormal(rng, companion["device_to_app_syncs_per_day"]))
            dc.sync_times = companion_syncs(timeline, plan, companion, rng, rate)
            rate = float(lognormal(rng, companion["app_to_store_writes_per_day"]))
            dc.write_times = companion_syncs(timeline, plan, companion, rng, rate)
        if period.archetype == "native":
            native.append((period, wear))
        contexts.append(dc)
    coverage = _Coverage(native)
    for dc in contexts:
        if dc.is_phone:
            dc.has_native_watch = coverage  # type: ignore[assignment]

    # Heart rate: one truth evaluation over the union of all devices' sample times, so
    # simultaneous devices see the same physiological fluctuation.
    planned: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for k, dc in enumerate(contexts):
        spec = dc.spec.get("metrics", {}).get("heart_rate")
        if spec and (allowed is None or "heart_rate" in allowed):
            planned[k] = plan_heart_rate(dc, spec)
    union = np.unique(np.concatenate([v[0] for v in planned.values()])) if planned else np.zeros(0)
    truth_hr = heart.evaluate(union, streams("heart", "noise"))

    hrv_truth: list[dict[str, Any]] = []
    batches: list[tuple[DeviceContext, Batch, str | None]] = []
    workout_records: list[tuple[DeviceContext, list[dict[str, Any]]]] = []
    route_parts: list[dict[str, Any]] = []
    ecg_rows: list[dict[str, Any]] = []
    for k, dc in enumerate(contexts):
        hr_batch: Batch | None = None
        if k in planned:
            times, seg, q = planned[k]
            hr_batch = finish_heart_rate(dc, times, seg, q, truth_hr[np.searchsorted(union, times)])
            batches.append((dc, hr_batch, None))
        for name, spec in dc.spec.get("metrics", {}).items():
            if name in ("source", "heart_rate") or not isinstance(spec, Mapping):
                continue
            mode = spec["mode"]
            metric = METRIC_NAME.get(name, name)
            if allowed is not None and metric not in allowed and mode not in ("hrv", "stand", "workout"):
                continue
            produced: list[Batch] = []
            if (
                spec.get("feature")
                and name != "daylight"
                and not dc.gate(
                    metric if metric in params["platforms"]["metrics"] else "heart_rate",
                    np.asarray([w1]),
                    spec["feature"],
                )[0]
            ):
                continue  # hardware feature not available on this model
            if mode == "chunks" and name in CHUNK_QUANTITY:
                produced = chunks(dc, metric, CHUNK_QUANTITY[name], spec)
            elif (mode == "chunks" and name == "daylight") or (mode == "mean_chunks" and name == "daylight"):
                if dc.gate("time_in_daylight", np.asarray([w1]), spec.get("feature"))[0]:
                    produced = chunks(dc, metric, "daylight", {**spec, "chunk": spec.get("chunk", {})})
            elif mode == "mean_chunks":
                if spec.get("feature") and not dc.gate(metric, np.asarray([w1]), spec["feature"])[0]:
                    continue
                produced = chunks(dc, metric, MEAN_SIGNAL[name], spec, mean=True)
            elif mode == "sync_chunks":
                produced = sync_chunks(dc, metric, CHUNK_QUANTITY[name], spec)
            elif mode == "minute_grid":
                produced = minute_grid(dc, spec)
            elif mode == "stand":
                produced = stand(dc, spec)
            elif mode == "hrv":
                produced = hrv(dc, spec, hrv_truth)
            elif mode == "samples":
                produced = respiratory_or_spo2(dc, metric, spec)
            elif mode == "daily":
                produced = daily_metric(dc, metric, spec, hr_batch)
            elif mode == "nightly":
                produced = nightly(dc, metric, spec)
            elif mode == "sleep":
                produced = sleep(dc, spec)
            elif mode == "bout":
                produced = bout(dc, metric, spec)
            elif mode == "workout_total":
                produced = workout_totals(dc, metric, spec)
            elif mode == "workout":
                rows, produced, tracks = workout_rows(dc, spec)
                workout_records.append((dc, rows))
                for track in tracks:
                    keep = (track["time"] >= w0) & (track["time"] < w1)
                    if keep.any():
                        route_parts.append(
                            {k: v[keep] for k, v in track.items()}
                            | {"device_id": np.full(int(keep.sum()), dc.period.device_id, dtype=object)}
                        )
            elif mode == "stairs":
                produced = stairs(dc, metric, spec)
            elif mode == "audio_events":
                produced = audio_events(dc, spec)
            elif mode == "afib_weekly":
                produced = afib_weekly(dc, spec)
            elif mode == "weekly_gait":
                produced = weekly_gait(dc, metric, spec)
            elif mode == "ecg":
                if dc.gate("electrocardiogram", np.asarray([w1]))[0]:
                    for row in ecg_recordings(dc, spec):
                        if w0 <= row["start"] < w1:
                            ecg_rows.append(
                                row
                                | {
                                    "device_id": dc.period.device_id,
                                    "source_name": dc.spec["source_name"],
                                    "lag": float(np.floor(dc.rng.uniform(2, 60))),
                                }
                            )
            else:
                raise ValueError(f"Unknown emission mode {mode!r} for {name}")
            batches.extend((dc, b, None) for b in produced if len(b))
    phone_dcs = [dc for dc in contexts if dc.is_phone]
    for source_name, batch in manual_batches(persona, timeline, daily, streams("manual"), (w0, w1)):
        if not len(batch):
            continue
        for dc in phone_dcs:
            mask = (batch.start >= dc.period.start) & (batch.start < dc.period.end)
            if mask.any():
                batches.append((dc, batch.select(mask), source_name))

    tables = {
        "observations": _observations(persona, batches, tz, timeline, usage, params, streams, (w0, w1)),
        "workouts": _workouts(persona, workout_records, tz, timeline, params, streams, (w0, w1)),
    }
    tables["routes"] = _concat_routes(persona, route_parts)
    tables["ecg"] = _ecg(persona, ecg_rows, tz, streams)
    events = plan.events + device_events
    events += [
        Event(
            "medication_dose",
            d.time,
            None,
            "stimulant",
            {
                "tmax_hours": round(d.tmax_hours, 2),
                "half_life_hours": round(d.half_life_hours, 2),
                "awake_hr_delta": round(d.awake_hr_delta, 2),
            },
        )
        for d in timeline.doses
    ]
    events.sort(key=lambda e: (e.start, e.kind))
    tables.update(_truth(persona, timeline, daily, heart, offsets, contexts, hrv_truth, events, plan, ctx, (w0, w1)))
    persona_row = persona.row()
    persona_row.update(
        {
            "platform": phone_platform,
            "enrollment": usage.enrollment,
            "app_sync_style": usage.style,
            "history_permission": usage.history_permission,
            "signal_fit": traits["fit"],
            "adherence": traits["adherence"],
            "night_wear": traits["night_wear"],
            "wearables": sorted({p.model for p in periods if p.role == "wearable"}),
        }
    )
    tables["personas"] = {k: [v] for k, v in persona_row.items()}
    tables["devices"] = _rows([p.row(persona.patient_id) for p in periods])
    tables["app_sync"] = {"patient_id": [persona.patient_id] * len(usage.syncs), "time": usage.syncs}
    return tables


def _concat_routes(persona: Persona, parts: list[dict[str, Any]]) -> dict[str, Any]:
    if not parts:
        return {}
    cols: dict[str, Any] = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    order = np.argsort(cols["time"], kind="stable")
    cols = {k: v[order] for k, v in cols.items()}
    cols["patient_id"] = Coded(np.zeros(order.size, dtype=np.int32), [persona.patient_id])
    return cols


def _ecg(persona: Persona, rows: list[dict[str, Any]], tz: Any, streams: Streams) -> dict[str, Any]:
    if not rows:
        return {}
    rows.sort(key=lambda r: r["start"])
    cols: dict[str, Any] = dict(_rows([{k: v for k, v in r.items() if k not in ("voltage_uv", "lag")} for r in rows]))
    cols["voltage_uv"] = [r["voltage_uv"] for r in rows]
    start = np.asarray(cols["start"], dtype=float)
    cols["created_at"] = start + 30 + np.asarray([r["lag"] for r in rows])
    cols["start_offset_min"] = tz.offsets(start)
    cols["record_id"] = _uuids(streams("ecg-ids"), len(rows))
    cols["patient_id"] = [persona.patient_id] * len(rows)
    return cols


# TODO(realism): Investigate the 30-45% twin steps target miss across both anchor sets.
def _calibrate_twin(persona: Persona, ctx: SimulationContext, streams: Streams) -> None:
    """Match a twin's realized steps and sleep to the owner's profiled medians.

    Behaviour parameters map to outcomes only through the whole simulation, so a short
    pilot (own random streams, discarded) measures the twin's median steps and asleep hours
    and rescales activity and sleep need. Applied once; the pilot never reaches the output.
    """
    traits = dict(persona.traits)
    steps_target = traits.get("daily_steps_target")
    sleep_target = traits.get("asleep_hours_target")
    if steps_target is None and sleep_target is None:
        return
    params = ctx.params
    anchors = params["cohorts"]["anchors"]
    if steps_target is not None:
        spec = params["cohorts"]["anchors"]["profiles"][persona.anchor]
        archetype = params["devices"]["models"][spec.get("wearable", "apple_watch")].get("archetype", "native")
        archetype = archetype if archetype in anchors["twin_steps_device_ratio"] else "native"
        steps_target = steps_target / float(anchors["twin_steps_device_ratio"][archetype])
    if sleep_target is not None:
        sleep_target = sleep_target + float(anchors["twin_sleep_device_bias_hours"])
    days = [ctx.start + timedelta(days=k) for k in range(84)]
    for _ in range(2):
        plan = plan_events(persona, days, params, streams("pilot", "events"), everyday=ctx.everyday_events)
        tz = zone_timeline(persona, plan)
        daily = base_state(persona, plan, params, streams("pilot", "daily"))
        timeline = build_timeline(persona, daily, plan, tz, params, streams("pilot", "behavior"))
        cols = timeline.columns
        steps = np.bincount(
            cols["day"], weights=cols["cadence"] / 60.0 * (cols["end"] - cols["start"]), minlength=len(days)
        )
        if steps_target is not None:
            measured = float(np.median(steps[1:-1]))
            traits["activity_scale"] = float(
                np.clip(traits.get("activity_scale", 1.0) * steps_target / max(measured, 500.0), 0.3, 4.0)
            )
        if sleep_target is not None:
            asleep = np.median([n.asleep_seconds / 3600 for n in timeline.nights if not n.nap])
            persona.sleep_need_hours = float(np.clip(persona.sleep_need_hours + (sleep_target - asleep), 5.0, 11.0))
        persona.traits = traits


def _rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for row in rows:
        for k, v in row.items():
            out.setdefault(k, []).append(v)
    return out


def _observations(
    persona: Persona,
    batches: list[tuple[DeviceContext, Batch, str | None]],
    tz: Any,
    timeline: Any,
    usage: Any,
    params: Params,
    streams: Streams,
    window: tuple[float, float],
) -> dict[str, Any]:
    registry = params["platforms"]["metrics"]
    w0, w1 = window
    numeric: dict[str, list[np.ndarray]] = {
        k: [] for k in ("start", "end", "created_at", "value", "truth_seq", "batch")
    }
    categories: list[Coded] = []
    meta: dict[str, list[Any]] = {
        k: []
        for k in ("metric", "unit", "truth_kind", "device_id", "wearable_id", "source_name", "device_model", "platform")
    }
    lag_rng = streams("delivery")
    for dc, batch, source_override in batches:
        if batch.metric not in registry:
            raise KeyError(f"Metric {batch.metric} missing from platforms.toml")
        mask = (batch.start >= w0) & (batch.start < w1) & dc.gate(batch.metric, batch.start)
        if not mask.any():
            continue
        b = batch.select(mask)
        n = len(b)
        archetype = "manual" if source_override is not None else "phone" if dc.is_phone else dc.period.archetype
        start = np.floor(b.start)
        end = np.maximum(start, np.floor(b.end))
        made = created_at(
            b.lag_class,
            archetype,
            start,
            end,
            timeline=timeline,
            syncs=dc.write_times,
            params=params,
            rng=lag_rng,
            metric=b.metric,
            model_delivery=dc.spec.get("delivery"),
        )
        k = len(meta["metric"])
        numeric["start"].append(start)
        numeric["end"].append(end)
        numeric["created_at"].append(np.maximum(np.floor(made), end))
        numeric["value"].append(b.value.astype(np.float64))
        numeric["truth_seq"].append(b.truth_seq.astype(np.int64) if b.truth_seq is not None else np.full(n, -1))
        numeric["batch"].append(np.full(n, k, dtype=np.int32))
        if b.category is None:
            categories.append(Coded(np.full(n, -1, dtype=np.int32), []))
        else:
            labels = sorted({c for c in b.category if c is not None})
            index = {c: i for i, c in enumerate(labels)}
            categories.append(Coded(np.asarray([index.get(c, -1) for c in b.category], dtype=np.int32), labels))
        for key, value in (
            ("metric", b.metric),
            ("unit", registry[b.metric]["unit"]),
            ("truth_kind", b.truth_kind),
            ("device_id", dc.period.device_id),
            ("wearable_id", None if dc.is_phone else dc.period.wearable_id),
            ("source_name", source_override or dc.spec["source_name"]),
            ("device_model", dc.spec["hardware"]),
            ("platform", dc.period.platform),
        ):
            meta[key].append(value)
    if not numeric["start"]:
        return {}
    cols: dict[str, Any] = {k: np.concatenate(v) for k, v in numeric.items()}
    category = Coded.concat(categories)
    metric_order = np.asarray([sorted(set(meta["metric"])).index(m) for m in meta["metric"]], dtype=np.int32)
    order = np.lexsort((metric_order[cols["batch"]], cols["start"]))
    cols = {k: v[order] for k, v in cols.items()}
    category = category.take(order)
    rng = streams("ids")
    n = cols["start"].size
    cols["record_id"] = _uuids(rng, n)
    duplicate_of = np.zeros(n, dtype="S36")
    # Rare re-sends: the same sample written again with a new id and a later creation date.
    resend = np.flatnonzero(rng.random(n) < params["delivery"]["app"]["resend_probability"])
    if resend.size:
        extra = {k: v[resend].copy() for k, v in cols.items()}
        extra["record_id"] = _uuids(rng, resend.size)
        extra["created_at"] = extra["created_at"] + np.round(rng.uniform(60, 3 * DAY, resend.size))
        duplicate_of = np.concatenate([duplicate_of, cols["record_id"][resend]])
        cols = {k: np.concatenate([cols[k], extra[k]]) for k in cols}
        category = Coded.concat([category, category.take(resend)])
        order = np.argsort(cols["start"], kind="stable")
        cols = {k: v[order] for k, v in cols.items()}
        category = category.take(order)
        duplicate_of = duplicate_of[order]
    batch = cols.pop("batch")
    for key, values in meta.items():
        uniq = sorted({v for v in values if v is not None})
        index = {v: i for i, v in enumerate(uniq)}
        codes = np.asarray([index[v] if v is not None else -1 for v in values], dtype=np.int32)
        cols[key] = Coded(codes[batch], uniq)
    cols["category"] = category
    cols["duplicate_of"] = duplicate_of
    cols["duplicate_mask"] = duplicate_of != b""
    cols["start_offset_min"] = tz.offsets(cols["start"])
    cols["end_offset_min"] = tz.offsets(cols["end"])
    platform_values = np.asarray([*cols["platform"].values, ""], dtype=object)[cols["platform"].codes]
    cols["readable"] = readable(cols["end"], platform_values, usage, params)
    cols["patient_id"] = Coded(np.zeros(n + int(resend.size), dtype=np.int32), [persona.patient_id])
    return cols


def _workouts(
    persona: Persona,
    records: list[tuple[DeviceContext, list[dict[str, Any]]]],
    tz: Any,
    timeline: Any,
    params: Params,
    streams: Streams,
    window: tuple[float, float],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    rng = streams("workout-ids")
    lag_rng = streams("workout-delivery")
    for dc, items in records:
        for item in items:
            if not window[0] <= item["start"] < window[1]:
                continue
            start, end = float(np.floor(item["start"])), float(np.floor(item["end"]))
            made = created_at(
                "default",
                dc.period.archetype,
                np.asarray([start]),
                np.asarray([end]),
                timeline=timeline,
                syncs=dc.write_times,
                params=params,
                rng=lag_rng,
                metric="workout",
                model_delivery=dc.spec.get("delivery"),
            )[0]
            rows.append(
                {
                    **item,
                    "start": start,
                    "end": end,
                    "created_at": float(max(np.floor(made), end)),
                    "patient_id": persona.patient_id,
                    "device_id": dc.period.device_id,
                    "wearable_id": dc.period.wearable_id,
                    "source_name": dc.spec["source_name"],
                    "platform": dc.period.platform,
                    "start_offset_min": int(tz.offsets(np.asarray([start]))[0]),
                }
            )
    if not rows:
        return {}
    cols: dict[str, Any] = dict(_rows(rows))
    cols["record_id"] = _uuids(rng, len(rows))
    return cols


def _truth(
    persona: Persona,
    timeline: Any,
    daily: Any,
    heart: HeartModel,
    offsets: np.ndarray,
    contexts: list[DeviceContext],
    hrv_truth: list[dict[str, Any]],
    events: list[Event],
    plan: Any,
    ctx: SimulationContext,
    window: tuple[float, float],
) -> dict[str, dict[str, Any]]:
    pid = persona.patient_id
    cols = timeline.columns
    w0, w1 = window
    keep = (cols["end"] > w0) & (cols["start"] < w1)
    intervals = {
        "patient_id": np.full(int(keep.sum()), pid, dtype=object),
        "seq": np.flatnonzero(keep),
        "start": cols["start"][keep],
        "end": cols["end"][keep],
        "offset_min": offsets[keep],
        "state": np.asarray(STATE_NAMES, dtype=object)[cols["state"][keep]],
        "activity": np.asarray(ACTIVITIES, dtype=object)[cols["activity"][keep]],
        "met": cols["met"][keep],
        "cadence_spm": cols["cadence"][keep],
        "speed_mps": cols["speed"][keep],
        "hr_intensity": cols["intensity"][keep],
        "hr_target": heart.target[keep],
        "hr_start": heart.v0[keep],
        "outdoors": cols["outdoors"][keep],
        "upright": cols["upright"][keep],
        "workout_seq": cols["workout"][keep],
        "night_seq": cols["night"][keep],
        "day_seq": cols["day"][keep],
        "headphones": cols["headphones"][keep],
        "flights": cols["flights"][keep],
    }
    steps = np.bincount(
        cols["day"], weights=cols["cadence"] / 60.0 * (cols["end"] - cols["start"]), minlength=len(plan.days)
    )
    day_rows = []
    for i, day in enumerate(plan.days):
        row = daily.row(i)
        row.update(
            {
                "patient_id": pid,
                "seq": i,
                "workday": bool(timeline.workday[i]),
                "wake": float(timeline.wake[i]),
                "bed": float(timeline.bed[i]),
                "steps_true": float(steps[i]),
                "illness": float(plan.illness[i]),
                "injury": bool(plan.injury[i]),
                "mood": float(plan.mood[i]),
                "vacation": bool(plan.vacation[i]),
                "hospital": bool(plan.hospital[i]),
                "hard_workout": bool(timeline.hard_workout[i]),
                "in_window": ctx.start <= day < ctx.start + timedelta(days=ctx.days),
            }
        )
        day_rows.append(row)
    nights = [
        {
            "patient_id": pid,
            "seq": nt.id,
            "day_seq": nt.day,
            "in_bed": nt.in_bed,
            "onset": nt.onset,
            "wake": nt.wake,
            "out_of_bed": nt.out_of_bed,
            "asleep_seconds": nt.asleep_seconds,
            "nap": nt.nap,
        }
        for nt in timeline.nights
        if nt.out_of_bed > w0 and nt.in_bed < w1
    ]
    workouts = [
        {
            "patient_id": pid,
            "seq": w.id,
            "kind": w.kind,
            "activity": w.activity,
            "start": w.start,
            "end": w.end,
            "outdoors": w.outdoors,
            "intends_record": w.intends_record,
            "record_start": w.record_start,
            "record_end": w.record_end,
            "auto_detectable": w.auto_detectable,
            "pauses": w.pauses,
            "segments": len(w.segments),
        }
        for w in timeline.workouts
        if w.end > w0 and w.start < w1
    ]
    wear_rows = []
    for dc in contexts:
        if dc.is_phone:
            continue
        for a, b, why in zip(dc.wear.off_start, dc.wear.off_end, dc.wear.off_reason, strict=True):
            if b > w0 and a < w1 and why != "not_owned":
                wear_rows.append(
                    {
                        "patient_id": pid,
                        "device_id": dc.period.device_id,
                        "start": float(a),
                        "end": float(b),
                        "reason": why,
                    }
                )
    hrv_rows = [{"patient_id": pid, **row} for row in hrv_truth if w0 <= row["start"] < w1]
    event_rows = [
        {
            "patient_id": pid,
            "seq": k,
            "kind": e.kind,
            "code": e.code,
            "start": e.start,
            "end": e.end,
            "detail": json.dumps(e.detail, sort_keys=True, default=str),
        }
        for k, e in enumerate(events)
    ]
    return {
        "truth_intervals": intervals,
        "truth_days": _rows(day_rows),
        "truth_nights": _rows(nights),
        "truth_workouts": _rows(workouts),
        "truth_wear": _rows(wear_rows),
        "truth_hrv": _rows(hrv_rows),
        "events": _rows(event_rows),
    }
