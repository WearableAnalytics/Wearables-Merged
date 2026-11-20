"""Structured workouts: daily plan, templates (steady, intervals, sets) and recording intent."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..util import lognormal

MINUTE = 60.0
HARD = frozenset({"run", "intervals", "hiit", "swim"})


@dataclass(slots=True)
class Segment:
    start: float
    end: float
    intensity: float
    met: float
    cadence: float
    speed: float
    arm: float


@dataclass(slots=True)
class Workout:
    id: int
    kind: str  # template type name (run, intervals, strength, ...)
    activity: str  # platform activity (run, cycle, strength, ...)
    start: float
    end: float
    outdoors: bool
    intends_record: bool
    record_start: float
    record_end: float
    auto_detectable: bool
    pauses: int
    segments: list[Segment]


# TODO(realism): Fit workout frequency, type and duration from training exercise logs.
# TODO(realism): use osmnx fir realistic routes.(device/extras)
def sessions_for_day(
    plan: Sequence[Sequence[Any]],
    *,
    weekend: bool,
    weekend_only: bool,
    multiplier: float,
    fatigued: bool,
    injured: bool,
    blocked: Sequence[str],
    double_probability: float,
    rng: np.random.Generator,
    fatigue_multiplier: float,
) -> list[tuple[str, float, float, float]]:
    """Choose today's sessions: list of (type, minutes median, log sigma, record propensity)."""
    chosen: list[tuple[str, float, float, float]] = []
    for kind, per_week, minutes, sigma, record in plan:
        p = (per_week / 2 if weekend else 0.02) if weekend_only else per_week / 7 * (1.25 if weekend else 0.9)
        p *= multiplier
        if fatigued and kind in HARD:
            p *= fatigue_multiplier
        if injured and kind in blocked:
            continue
        if rng.random() < min(p, 0.95):
            chosen.append((str(kind), float(minutes), float(sigma), float(record)))
    rng.shuffle(chosen)  # type: ignore[arg-type]
    limit = 2 if rng.random() < double_probability else 1
    return chosen[:limit]


def build(
    kind: str,
    start: float,
    minutes: float,
    spec: Mapping[str, Any],
    *,
    rng: np.random.Generator,
    effort: float = 1.0,
) -> tuple[str, list[Segment], bool]:
    template = spec["template"]
    activity = str(spec.get("activity", kind))
    jitter = float(np.exp(rng.normal(0, 0.05)))
    intensity = float(np.clip(rng.normal(*spec["intensity"]) * effort, 0.1, 1.0))
    met = spec["met"] * jitter
    cadence = spec["cadence_spm"] * float(np.exp(rng.normal(0, 0.03)))
    speed = spec["speed"] * jitter
    arm = spec["arm_motion"]
    outdoors = bool(rng.random() < spec["outdoor_probability"])
    segments: list[Segment] = []
    cursor = start
    total = max(spec["min_minutes"], minutes) * MINUTE

    def add(length: float, i: float, m: float, c: float, v: float) -> None:
        nonlocal cursor
        segments.append(Segment(cursor, cursor + length, i, m, c, v, arm))
        cursor += length

    if template == "steady":
        warm = spec.get("warmup_minutes", 0.0) * MINUTE
        cool = spec.get("cooldown_minutes", 0.0) * MINUTE
        if warm and total > warm + cool + 5 * MINUTE:
            add(warm, intensity * 0.7, met * 0.6, cadence * 0.95, speed * 0.75)
            add(total - warm - cool, intensity, met, cadence, speed)
            add(cool, intensity * 0.6, met * 0.5, cadence * 0.9, speed * 0.6)
        else:
            add(total, intensity, met, cadence, speed)
    else:
        warm = spec.get("warmup_minutes", 0.0) * MINUTE
        cool = spec.get("cooldown_minutes", 0.0) * MINUTE
        if warm:
            add(warm, spec["rest_intensity"], spec["rest_met"], spec["rest_cadence_spm"], spec["rest_speed"])
        reps = int(rng.integers(spec["repetitions"][0], spec["repetitions"][1] + 1))
        work = rng.uniform(*spec["work_minutes"]) * MINUTE
        rest = rng.uniform(*spec["rest_minutes"]) * MINUTE
        for rep in range(reps):
            add(work * float(np.exp(rng.normal(0, 0.05))), intensity, met, cadence, speed)
            if rep < reps - 1 or not cool:
                add(
                    rest * float(np.exp(rng.normal(0, 0.1))),
                    spec["rest_intensity"],
                    spec["rest_met"],
                    spec["rest_cadence_spm"],
                    spec["rest_speed"],
                )
        if cool:
            add(cool, spec["rest_intensity"] * 0.9, spec["rest_met"], spec["rest_cadence_spm"], spec["rest_speed"])
    return activity, segments, outdoors


def recording(
    workout_start: float,
    workout_end: float,
    propensity: float,
    recording: Mapping[str, Any],
    rng: np.random.Generator,
) -> tuple[bool, float, float, int]:
    """Whether the person starts the watch, and the recorded window it would capture."""
    intends = bool(rng.random() < propensity)
    start = workout_start + float(lognormal(rng, recording["start_delay_seconds"]))
    end = workout_end
    if rng.random() < recording["end_overrun_probability"]:
        end += float(lognormal(rng, recording["end_overrun_minutes"])) * MINUTE
    elif rng.random() < recording["early_stop_probability"]:
        end -= (workout_end - workout_start) * rng.uniform(0.02, 0.15)
    pauses = int(rng.poisson(1.5)) if rng.random() < recording["pause_probability"] else 0
    return intends, start, max(start + 30, end), pauses
