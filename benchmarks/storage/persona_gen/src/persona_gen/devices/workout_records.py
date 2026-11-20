"""Observed workouts and per-workout metrics (VO2max, HR recovery, running dynamics)."""

from collections.abc import Mapping
from typing import Any

import numpy as np

from .context import Batch, DeviceContext, ObservedWorkout
from .extras import ROUTE_ACTIVITIES, route

OUTDOOR_VO2 = frozenset({"walk", "run", "hike"})


def workout_rows(
    dc: DeviceContext, spec: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[Batch], list[dict[str, Any]]]:
    """Observed workout rows for one device, their metric batches (energy, effort, VO2max, heart-rate recovery, running
    dynamics) and GPS route rows.
    """
    rows: list[dict[str, Any]] = []
    batches: list[Batch] = []
    routes: list[dict[str, Any]] = []
    if not dc.workouts or not dc.gate("workout", np.asarray([dc.workouts[0].start]))[0]:
        return rows, batches, routes
    rng = dc.rng
    active = dc.rate("active_energy")
    distance = dc.rate("distance_walking_running")
    cycling = dc.rate("distance_cycling")
    vo2_t, vo2_v, vo2_s = [], [], []
    hrr_t, hrr_v, hrr_s = [], [], []
    eff_a, eff_b, eff_v, eff_s = [], [], [], []
    est_a, est_b, est_v, est_s = [], [], [], []
    dyn: dict[str, list[tuple[np.ndarray, np.ndarray, np.ndarray]]] = {}
    for k, ow in enumerate(dc.workouts):
        w = ow.truth
        a, b = np.asarray([ow.start]), np.asarray([ow.end])
        energy = float(dc.integral(active, a, b)[0])
        dist = float(dc.integral(cycling if w.activity == "cycle" else distance, a, b)[0])
        intensity = float(np.mean([s.intensity for s in w.segments]))
        effort = int(np.clip(round(1 + 9 * intensity * rng.uniform(0.85, 1.15)), 1, 10))
        rows.append(
            {
                "workout_seq": k,
                "truth_workout": w.id,
                "activity": w.activity,
                "start": ow.start,
                "end": ow.end,
                "duration_s": ow.end - ow.start,
                "energy_kcal": round(energy, 2),
                "distance_m": round(dist, 1),
                "auto_detected": ow.auto_detected,
                "pauses": w.pauses,
                "outdoors": w.outdoors,
                "effort": effort if "effort_score" in dc.spec.get("features", ()) else None,
            }
        )
        if spec.get("route_seconds") and w.outdoors and w.activity in ROUTE_ACTIVITIES:
            track = route(dc, ow.start, ow.end, w.activity, float(spec["route_seconds"]))
            if track:
                track["truth_workout"] = np.full(track["time"].size, w.id, dtype=np.int64)
                routes.append(track)
        if "effort_score" in dc.spec.get("features", ()):
            est_a.append(ow.start)
            est_b.append(ow.end)
            est_s.append(w.id)
            est_v.append(int(np.clip(round(1 + 9 * intensity), 1, 10)))
            eff_a.append(ow.start)
            eff_b.append(ow.end)
            eff_v.append(effort)
            eff_s.append(w.id)
        if spec.get("vo2max") and w.activity in OUTDOOR_VO2 and w.outdoors and ow.end - ow.start >= 600:
            d = dc.timeline.columns["day"][np.searchsorted(dc.timeline.start, ow.start) - 1]
            bias = dc.traits.get("vo2_bias", 1.0)
            value = dc.daily.vo2max[d] * bias + rng.normal(0, 1.0)
            vo2_t.append(ow.end)
            vo2_v.append(round(float(np.clip(value, 14, 85)), 2))
            vo2_s.append(w.id)
        if spec.get("heart_rate_recovery") and intensity >= 0.45 and ow.end - ow.start >= 600:
            times = np.asarray([w.end, w.end + 60])
            hr = dc.heart.deterministic(times)
            hrr_t.append(w.end + 60)
            hrr_v.append(round(float(hr[0] - hr[1] + rng.normal(0, 2.5)), 1))
            hrr_s.append(w.id)
        if (
            spec.get("running_dynamics")
            and w.activity == "run"
            and w.outdoors
            and "running_dynamics" in dc.spec.get("features", ())
        ):
            p = dc.persona
            for metric, cadence in (
                ("running_speed", 3.0),
                ("running_power", 3.0),
                ("running_stride_length", 5.0),
                ("running_ground_contact_time", 5.0),
                ("running_vertical_oscillation", 5.0),
            ):
                times = np.arange(ow.start + rng.uniform(1, cadence), ow.end, cadence)
                idx = np.clip(
                    np.searchsorted(dc.timeline.start, times, side="right") - 1, 0, len(dc.timeline.start) - 1
                )
                speed = dc.timeline.columns["speed"][idx].astype(float) * np.exp(rng.normal(0, 0.04, len(times)))
                cad = np.maximum(dc.timeline.columns["cadence"][idx].astype(float), 60)
                if metric == "running_speed":
                    value = np.round(speed, 3)
                elif metric == "running_power":
                    value = np.round(1.04 * p.weight_kg * speed * np.exp(rng.normal(0, 0.03, len(times))))
                elif metric == "running_stride_length":
                    value = np.round(speed / (cad / 60), 3)
                elif metric == "running_ground_contact_time":
                    value = np.round(np.clip(330 - 25 * speed + rng.normal(0, 8, len(times)), 160, 400))
                else:
                    value = np.round(np.clip(9.5 + 0.3 * (speed - 3) + rng.normal(0, 0.4, len(times)), 5, 15), 1)
                dyn.setdefault(metric, []).append((times, value, idx))
    if vo2_t:
        t = np.asarray(vo2_t)
        batches.append(
            Batch("vo2max", t, t.copy(), np.asarray(vo2_v), None, "workout", np.asarray(vo2_s), lag_class="default")
        )
    if hrr_t:
        t = np.asarray(hrr_t)
        batches.append(Batch("heart_rate_recovery", t, t.copy(), np.asarray(hrr_v), None, "workout", np.asarray(hrr_s)))
    if eff_a:
        gate = dc.gate("workout_effort", np.asarray(eff_b))
        if gate.any():
            batches.append(
                Batch(
                    "workout_effort",
                    np.asarray(eff_a)[gate],
                    np.asarray(eff_b)[gate],
                    np.asarray(eff_v, dtype=float)[gate],
                    None,
                    "workout",
                    np.asarray(eff_s)[gate],
                )
            )
    if est_a:
        gate = dc.gate("estimated_workout_effort", np.asarray(est_b))
        if gate.any():
            batches.append(
                Batch(
                    "estimated_workout_effort",
                    np.asarray(est_a)[gate],
                    np.asarray(est_b)[gate],
                    np.asarray(est_v, dtype=float)[gate],
                    None,
                    "workout",
                    np.asarray(est_s)[gate],
                )
            )
    for metric, parts in dyn.items():
        t = np.concatenate([x[0] for x in parts])
        gate = dc.gate(metric, t)
        batches.append(
            Batch(
                metric,
                t[gate],
                t[gate].copy(),
                np.concatenate([x[1] for x in parts])[gate],
                None,
                "interval",
                np.concatenate([x[2] for x in parts])[gate],
            )
        )
    return rows, batches, routes


def workout_totals(dc: DeviceContext, metric: str, spec: Mapping[str, Any]) -> list[Batch]:
    """Companion apps write one distance total per workout (e.g. Garmin cycling)."""
    allowed = set(spec.get("workout_types", ()))
    rate = dc.rate(metric)
    rows = [
        (ow.start, ow.end, ow.truth.id)
        for ow in dc.workouts
        if ow.truth.kind in allowed or ow.truth.activity in allowed
    ]
    if not rows:
        return []
    a = np.asarray([r[0] for r in rows], dtype=float)
    b = np.asarray([r[1] for r in rows], dtype=float)
    s = np.asarray([r[2] for r in rows], dtype=np.int64)
    value = np.round(dc.integral(rate, a, b), 1)
    keep = value > 0
    return [Batch(metric, a[keep], b[keep], value[keep], None, "workout", s[keep])]


__all__ = ["ObservedWorkout", "workout_rows", "workout_totals"]
