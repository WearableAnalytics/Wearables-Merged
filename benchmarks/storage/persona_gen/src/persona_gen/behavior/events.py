"""Acute events and clinical changes on a per-day grid of the persona's local dates.

Events are planned before the timeline so behaviour, physiology and devices all see the
same ground truth. Every event is also returned as a labelled ``Event`` row.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from ..model import Event
from ..persona.sampler import Persona
from ..timeutil import ZoneSpan, ZoneTimeline, utc_seconds
from ..util import lognormal, uniform


@dataclass(slots=True)
class Travel:
    depart: date
    back: date
    zone: str
    vacation: bool
    offline: tuple[date, date] | None


@dataclass(slots=True)
class EventPlan:
    days: list[date]
    illness: np.ndarray  # severity 0..1 per day
    illness_rhr: np.ndarray  # bpm per day
    fever: np.ndarray  # degC per day
    injury: np.ndarray  # bool per day
    mood: np.ndarray  # 0..1 depressive load per day
    mood_sleep_delta: np.ndarray  # hours per day
    hospital: np.ndarray  # bool per day (in hospital, device off)
    recovery: np.ndarray  # 0..1 post-procedure activity factor
    vacation: np.ndarray  # bool per day
    offline: np.ndarray  # bool per day (phone offline, no sync)
    travels: list[Travel]
    events: list[Event] = field(default_factory=list)


def _spans(rng: np.random.Generator, rate_per_year: float, n_days: int, duration: Any) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    day = 0
    while True:
        day += int(rng.exponential(365.0 / rate_per_year)) + 1 if rate_per_year > 0 else n_days + 1
        if day >= n_days:
            return spans
        length = max(1, round(float(lognormal(rng, duration))))
        spans.append((day, min(n_days, day + length)))
        day += length


def plan_events(
    persona: Persona,
    days: list[date],
    params: Mapping[str, Any],
    rng: np.random.Generator,
    *,
    everyday: bool = True,
) -> EventPlan:
    """Plan the per-day event grid. ``everyday=False`` leaves out illness, injury, mood episodes and travel;
    clinical events from the persona's timeline are always planned (a wearable-only persona has none)."""
    spec = params["behavior"]["events"]
    n = len(days)
    plan = EventPlan(
        days=days,
        illness=np.zeros(n),
        illness_rhr=np.zeros(n),
        fever=np.zeros(n),
        injury=np.zeros(n, dtype=bool),
        mood=np.zeros(n),
        mood_sleep_delta=np.zeros(n),
        hospital=np.zeros(n, dtype=bool),
        recovery=np.ones(n),
        vacation=np.zeros(n, dtype=bool),
        offline=np.zeros(n, dtype=bool),
        travels=[],
    )

    def label(kind: str, d0: int, d1: int, code: str, **detail: Any) -> None:
        plan.events.append(
            Event(kind, utc_seconds(days[d0]), utc_seconds(days[min(d1, n - 1)]) if d1 > d0 else None, code, detail)
        )

    # Everyday events: acute illness, injury, mood episodes and travel. Wearable-only fixtures can skip them.
    if everyday:
        illness = spec["illness"]
        for d0, d1 in _spans(rng, illness["rate_per_year"], n, illness["duration_days"]):
            rhr = uniform(rng, illness["rhr_delta"])
            fever = uniform(rng, illness["temperature_delta"])
            length = d1 - d0
            shape = np.sin(np.linspace(0.3, np.pi - 0.3, length)) if length > 1 else np.ones(1)
            plan.illness[d0:d1] = np.maximum(plan.illness[d0:d1], shape)
            plan.illness_rhr[d0:d1] = np.maximum(plan.illness_rhr[d0:d1], rhr * shape)
            plan.fever[d0:d1] = np.maximum(plan.fever[d0:d1], fever * shape * (np.arange(length) < 3))
            label("illness", d0, d1, "synthetic-acute-illness", rhr_delta_bpm=round(rhr, 2), fever_degc=round(fever, 2))

        injury = spec["injury"]
        for d0, d1 in _spans(rng, injury["rate_per_year"], n, injury["duration_days"]):
            plan.injury[d0:d1] = True
            label("injury", d0, d1, "synthetic-musculoskeletal-injury")

        if persona.trajectory == "episodic" and (
            persona.anchor or any(c.name in {"depression", "bipolar"} for c in persona.clinical.conditions)
        ):
            mood = spec["mood_episode"]
            for d0, d1 in _spans(rng, mood["rate_per_year"], n, mood["duration_days"]):
                ramp = np.minimum(1.0, np.minimum(np.arange(1, d1 - d0 + 1), np.arange(d1 - d0, 0, -1)) / 5.0)
                delta = uniform(rng, mood["sleep_delta_hours"])
                plan.mood[d0:d1] = np.maximum(plan.mood[d0:d1], ramp)
                plan.mood_sleep_delta[d0:d1] = delta * ramp
                label("mood_episode", d0, d1, "synthetic-depressive-episode", sleep_delta_hours=round(delta, 2))

        travel = spec["travel"]
        for d0, d1 in _spans(rng, travel["rate_per_year"], n, travel["duration_days"]):
            if d1 - d0 < 2 or plan.hospital[d0:d1].any():
                continue
            zone = str(rng.choice(travel["zones"]))
            vacation = bool(rng.random() < travel["vacation_probability"])
            offline = None
            if rng.random() < travel["offline_probability"]:
                o0 = d0 + int(rng.integers(0, max(1, d1 - d0 - 1)))
                offline = (days[o0], days[min(n - 1, o0 + int(rng.integers(1, 4)))])
                plan.offline[o0 : o0 + 3] = True
            plan.travels.append(Travel(days[d0], days[min(d1, n - 1)], zone, vacation, offline))
            if vacation:
                plan.vacation[d0:d1] = True
            label("travel", d0, d1, zone, vacation=vacation, zone=zone)

    # Clinical events: condition onsets, medication starts/stops, procedures.
    first, last = days[0], days[-1]
    for condition in persona.clinical.conditions:
        if first <= condition.onset <= last:
            plan.events.append(
                Event(
                    "condition_onset",
                    utc_seconds(condition.onset),
                    None,
                    condition.name,
                    {"source": condition.source, "code": condition.code},
                )
            )
    for medication in persona.clinical.medications:
        for kind, day in (("medication_start", medication.start), ("medication_stop", medication.stop)):
            if day is not None and first <= day <= last:
                plan.events.append(
                    Event(
                        kind,
                        utc_seconds(day),
                        None,
                        medication.cls,
                        {
                            "name": medication.name,
                            "rhr_delta_bpm": round(medication.rhr_delta, 2),
                            **{k: round(v, 3) for k, v in medication.params.items()},
                        },
                    )
                )
    hospital = spec["hospitalization"]
    for admit, discharge, name in persona.clinical.procedures:
        if discharge < first or admit > last:
            continue
        d0 = max(0, (admit - first).days)
        d1 = min(n, (discharge - first).days + 1)
        plan.hospital[d0:d1] = True
        after = np.arange(n) - d1
        curve = hospital["activity_floor"] + (1 - hospital["activity_floor"]) * (
            1 - np.exp(-after / hospital["recovery_tau_days"])
        )
        plan.recovery = np.where(after >= 0, np.minimum(plan.recovery, curve), plan.recovery)
        plan.recovery[d0:d1] = hospital["activity_floor"]
        plan.vacation[d0:d1] = True  # no work while hospitalized
        label("hospitalization", d0, d1, name, discharge=discharge.isoformat())
    plan.events.sort(key=lambda e: (e.start, e.kind))
    return plan


def zone_timeline(persona: Persona, plan: EventPlan) -> ZoneTimeline:
    """Home zone plus one span per trip to another zone (09:00 UTC on departure to 15:00 UTC on return)."""
    spans = [
        ZoneSpan(utc_seconds(t.depart) + 9 * 3600, utc_seconds(t.back) + 15 * 3600, t.zone)
        for t in plan.travels
        if t.zone != persona.timezone
    ]
    return ZoneTimeline(persona.timezone, spans)


def day_index(plan: EventPlan, day: date) -> int:
    return (day - plan.days[0]).days


__all__ = ["EventPlan", "Travel", "day_index", "plan_events", "zone_timeline"]
