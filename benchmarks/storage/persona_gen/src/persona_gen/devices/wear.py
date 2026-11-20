"""Wear timeline and signal quality for one wearable period.

Missingness depends on the person and their state: an adherence trait, nights on or off,
charging habits, short removals, illness/mood (via the daily wear multiplier), low
activity and hospital stays. Signal quality is a hidden per-moment variable built from a
habitual fit tendency, day-to-day variation, motion (arm-heavy effort), cold and tattoos.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..behavior.events import EventPlan
from ..behavior.timeline import Timeline
from ..persona.sampler import Persona
from ..physiology.daily import DailyState
from ..timeutil import DAY, HOUR, MINUTE, ZoneTimeline
from ..util import lognormal
from .ownership import DevicePeriod


@dataclass(slots=True)
class Wear:
    off_start: np.ndarray
    off_end: np.ndarray
    off_reason: list[str]

    def worn(self, times: np.ndarray) -> np.ndarray:
        if not len(self.off_start):
            return np.ones(times.shape, dtype=bool)
        idx = np.searchsorted(self.off_start, times, side="right") - 1
        inside = (idx >= 0) & (times < self.off_end[np.clip(idx, 0, None)])
        return ~inside

    def worn_fraction(self, start: float, end: float) -> float:
        if end <= start:
            return 0.0
        overlap = np.clip(np.minimum(self.off_end, end) - np.maximum(self.off_start, start), 0, None).sum()
        return 1.0 - float(overlap) / (end - start)


def _merge(intervals: list[tuple[float, float, str]]) -> Wear:
    intervals.sort()
    merged: list[list[Any]] = []
    for a, b, why in intervals:
        if b <= a:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b, why])
    return Wear(
        np.asarray([m[0] for m in merged], dtype=float),
        np.asarray([m[1] for m in merged], dtype=float),
        [m[2] for m in merged],
    )


def wear_timeline(
    persona: Persona,
    period: DevicePeriod,
    timeline: Timeline,
    daily: DailyState,
    plan: EventPlan,
    tz: ZoneTimeline,
    traits: Mapping[str, float],
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> Wear:
    spec = params["devices"]["wear"]
    model = period.spec
    off: list[tuple[float, float, str]] = []
    if period.start > timeline.start[0]:
        off.append((timeline.start[0] - DAY, period.start, "not_owned"))
    if period.end < timeline.end[-1]:
        off.append((period.end, timeline.end[-1] + DAY, "not_owned"))
    adherence = float(traits["adherence"])
    night_wear = float(traits["night_wear"])
    if model["kind"] == "ring":
        night_wear = max(night_wear, 0.95)
    # Off-wrist hazard scales the person's own non-wear share: higher when ill, low mood or
    # inactive. Anchors carry adherence measured from their exports, which already includes
    # their activity level, so the inactivity penalty is not applied twice.
    measured = "adherence" in persona.traits
    inactivity = 1.0 if measured else 1.0 + spec["low_activity_penalty"] / 0.15 * (1 - persona.activity_level)
    days = plan.days
    episode_median = float(spec["offwrist_episode_days"][0])
    off_until = -1
    charge_every = float(model.get("charging_every_days", 3.0))
    next_charge = rng.uniform(0, charge_every)
    for i, day in enumerate(days):
        zone = tz.zone_for_day(day)
        start = tz.local_to_utc(day, 0.0, zone)
        end = start + DAY
        if plan.hospital[i]:
            off.append((start, end, "hospital"))
            continue
        if i < off_until:
            continue
        off_share = float(np.clip((1 - adherence) * inactivity / max(daily.wear[i], 0.05), 0.002, 0.98))
        if rng.random() < off_share / episode_median:
            # Highly adherent people have short gaps; low adherence means longer abandonment-like gaps.
            scale = float(np.clip((1 - adherence) / 0.15, 0.3, 2.0))
            median_days, sigma = spec["offwrist_episode_days"]
            length = max(1, round(float(lognormal(rng, (median_days * scale, sigma)))))
            off.append((start, start + length * DAY, "nonwear"))
            off_until = i + length
            continue
        wake, bed = timeline.wake[i], timeline.bed[i]
        if rng.random() > night_wear:
            off.append(
                (
                    bed - rng.uniform(0, 30) * MINUTE,
                    timeline.wake[i + 1] if i + 1 < len(days) else bed + 8 * HOUR,
                    "night_off",
                )
            )
            charge_now = True
        else:
            charge_now = False
        next_charge -= 1
        if next_charge <= 0 or (charge_now and charge_every <= 1.5):
            hour = rng.normal(*model["charge_hour"])
            t0 = tz.local_to_utc(day, float(np.clip(hour, 0, 23.5)), zone)
            t0 = min(max(t0, wake), bed - HOUR) if bed - HOUR > wake else wake
            minutes = float(lognormal(rng, model["charge_minutes"]))
            if not charge_now:
                off.append((t0, t0 + minutes * MINUTE, "charging"))
            next_charge += charge_every * float(np.exp(rng.normal(0, 0.25)))
        for _ in range(rng.poisson(spec["short_removal_per_day"])):
            t0 = rng.uniform(wake, max(wake + 1, bed))
            off.append((t0, t0 + float(lognormal(rng, spec["short_removal_minutes"])) * MINUTE, "removed"))
    return _merge(off)


def signal_traits(persona: Persona, params: Mapping[str, Any], rng: np.random.Generator) -> dict[str, float]:
    """Per-person signal traits (fit, tattoo, adherence, night wear). Anchors use their profiled values."""
    signal = params["devices"]["signal"]
    wear = params["devices"]["wear"]
    traits = {
        "fit": float(np.clip(rng.normal(signal["fit_mean"], signal["fit_sigma"]), 0.4, 1.0)),
        "tattoo": float(rng.random() < signal["tattoo_share"]),
        "adherence": float(rng.beta(*wear["adherence_beta"])),
        "night_wear": float(rng.beta(*wear["night_wear_beta"])),
    }
    for key in ("adherence", "night_wear", "fit"):
        if key in persona.traits:  # anchors: profiled from the owner's exports
            traits[key] = float(persona.traits[key])
    return traits


def quality(
    times_idx: np.ndarray,
    timeline: Timeline,
    traits: Mapping[str, float],
    day_noise: np.ndarray,
    signal: Mapping[str, Any],
    winter: np.ndarray,
) -> np.ndarray:
    cols = timeline.columns
    arm = cols["arm"][times_idx]
    day = cols["day"][times_idx]
    q = traits["fit"] + day_noise[day] - signal["motion_penalty"] * arm
    q -= signal["cold_penalty"] * (cols["outdoors"][times_idx] & winter[day])
    q -= signal["tattoo_penalty"] * traits["tattoo"]
    return np.clip(q, 0.0, 1.0)


def accept_probability(q: np.ndarray, signal: Mapping[str, Any]) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(q - signal["accept_midpoint"]) / signal["accept_scale"]))
