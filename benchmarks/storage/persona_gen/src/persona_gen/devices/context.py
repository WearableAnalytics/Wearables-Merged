"""Per-device view of the truth: measurement contexts, observed workouts, rates and gates."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import numpy as np

from ..behavior.events import EventPlan
from ..behavior.timeline import ACTIVITY_INDEX, Timeline
from ..behavior.workouts import Workout
from ..model import (
    COMMUTE,
    CTX_MOVING,
    CTX_SLEEP,
    CTX_STILL,
    CTX_WORKOUT,
    SEDENTARY,
    SLEEP_STATES,
)
from ..persona.sampler import Persona
from ..physiology.daily import DailyState
from ..physiology.heart import HeartModel
from ..timeutil import DAY, ZoneTimeline, utc_seconds
from ..util import lognormal
from .ownership import DevicePeriod
from .wear import Wear

STILL_ACTIVITIES = np.asarray([ACTIVITY_INDEX[a] for a in ("transit", "car", "flight")])
CYCLING_ACTIVITIES = np.asarray([ACTIVITY_INDEX[a] for a in ("cycle", "commute_cycle")])
NO_FOOT_DISTANCE = np.asarray(
    [ACTIVITY_INDEX[a] for a in ("cycle", "swim", "commute_cycle", "car", "transit", "flight")]
)


@dataclass(slots=True)
class Batch:
    metric: str
    start: np.ndarray
    end: np.ndarray
    value: np.ndarray  # float64, NaN for category records
    category: list[str | None] | None = None
    truth_kind: str = "interval"
    truth_seq: np.ndarray | None = None
    workout_ref: np.ndarray | None = None
    lag_class: str = "default"

    def __len__(self) -> int:
        return int(self.start.size)

    def select(self, mask: np.ndarray) -> Batch:
        return Batch(
            self.metric,
            self.start[mask],
            self.end[mask],
            self.value[mask],
            [c for c, m in zip(self.category, mask, strict=True) if m] if self.category is not None else None,
            self.truth_kind,
            self.truth_seq[mask] if self.truth_seq is not None else None,
            self.workout_ref[mask] if self.workout_ref is not None else None,
            self.lag_class,
        )


class Worn(Protocol):
    def worn(self, times: np.ndarray) -> np.ndarray: ...


@dataclass(slots=True)
class ObservedWorkout:
    truth: Workout
    start: float
    end: float
    auto_detected: bool


@dataclass(slots=True)
class DeviceContext:
    persona: Persona
    period: DevicePeriod
    timeline: Timeline
    daily: DailyState
    plan: EventPlan
    tz: ZoneTimeline
    heart: HeartModel
    wear: Wear
    traits: Mapping[str, float]
    params: Mapping[str, Any]
    rng: np.random.Generator
    os_adoption: Mapping[str, float]
    window: tuple[float, float]
    day_noise: np.ndarray = field(default_factory=lambda: np.zeros(0))
    winter: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    carried: np.ndarray | None = None
    workouts: list[ObservedWorkout] = field(default_factory=list)
    has_native_watch: Worn | None = None
    sync_times: np.ndarray = field(default_factory=lambda: np.zeros(0))  # device -> companion app
    write_times: np.ndarray = field(default_factory=lambda: np.zeros(0))  # companion app -> platform store
    step_bias: float = 1.0
    step_day: np.ndarray = field(default_factory=lambda: np.ones(0))
    energy_bias: float = 1.0
    grid_phase: float = 0.0
    # Segments: maximal pieces with constant interval, wear and recording state.
    seg_start: np.ndarray = field(default_factory=lambda: np.zeros(0))
    seg_end: np.ndarray = field(default_factory=lambda: np.zeros(0))
    seg_idx: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))
    seg_on: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    seg_ctx: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int8))
    seg_workout: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))

    @property
    def is_phone(self) -> bool:
        return self.period.role == "phone"

    @property
    def spec(self) -> dict[str, Any]:
        return self.period.spec

    @property
    def signal(self) -> Mapping[str, Any]:
        override = {k: v for k, v in self.spec.get("signal", {}).items() if k != "source"}
        return {**self.params["devices"]["signal"], **override}

    def prepare(self, recorder: bool) -> None:
        """Draw per-device random effects (day noise, step and energy bias, grid phase, phone carry), observe
        workouts if ``recorder`` is set, and build the segment arrays.
        """
        cols = self.timeline.columns
        signal = self.signal
        n_days = len(self.plan.days)
        self.day_noise = self.rng.normal(0, signal["day_sigma"], n_days)
        bias = self.spec.get("step_bias", (1.0, 0.0))
        # TODO: Some ``step_bias`` tables in params/devices.toml are labelled "calibrated" but hold assumptions.
        # Relabel them.
        self.step_bias = float(self.rng.normal(bias[0], bias[1]))
        self.step_day = np.clip(self.rng.normal(1.0, signal["step_day_sigma"], n_days), 0.7, 1.3)
        self.energy_bias = float(
            np.clip(self.rng.normal(signal["energy_bias_mean"], signal["energy_bias_sigma"]), 0.5, 1.6)
        )
        self.grid_phase = float(self.rng.uniform(0, 3600))
        months = np.asarray([d.month for d in self.plan.days])
        self.winter = np.isin(months, (12, 1, 2) if self.persona.latitude >= 0 else (6, 7, 8))
        if self.is_phone:
            carry = self.params["devices"]["phone"]["carry_probability"]
            propensity = self.rng.normal(0, self.params["devices"]["phone"]["carry_propensity_sigma"])
            state = cols["state"]
            p = np.select(
                [state == SEDENTARY, state == 1, state == 2, state == 4, state == COMMUTE],
                [carry["sedentary"], carry["light"], carry["walk"], carry["workout"], carry["commute"]],
                0.0,
            )
            # TODO: compare phone and wearable steps on the same days (synthetic versus Kaggle) and tune the carry
            # model only if the gap exceeds the real-versus-real spread.
            self.carried = (self.rng.random(len(state)) < np.clip(p + propensity, 0, 1)) & self.period.motion
        if recorder:
            self._observe_workouts()
        self._segments()

    def _observe_workouts(self) -> None:
        rec = self.params["behavior"]["recording"]
        auto = bool(self.spec.get("auto_detect_workouts", False)) and self.spec["kind"] in ("watch", "tracker")
        for w in self.timeline.workouts:
            if not (self.period.start <= w.start < self.period.end) or not self.wear.worn(np.asarray([w.start]))[0]:
                continue
            if w.intends_record:
                self.workouts.append(ObservedWorkout(w, w.record_start, w.record_end, False))
            elif auto and w.auto_detectable and self.rng.random() < rec["auto_detect_probability"]:
                delay = float(lognormal(self.rng, rec["auto_detect_delay_minutes"])) * 60
                if w.end - w.start > delay + 300:
                    self.workouts.append(ObservedWorkout(w, w.start + delay * 0.3, w.end, True))

    def _segments(self) -> None:
        cols = self.timeline.columns
        starts, ends = cols["start"], cols["end"]
        lo = max(self.period.start, starts[0])
        hi = min(self.period.end, ends[-1])
        if hi <= lo:
            for name in ("seg_start", "seg_end"):
                setattr(self, name, np.zeros(0))
            self.seg_idx = np.zeros(0, dtype=np.int64)
            self.seg_on = np.zeros(0, dtype=bool)
            self.seg_ctx = np.zeros(0, dtype=np.int8)
            self.seg_workout = np.zeros(0, dtype=np.int64)
            return
        points = [starts, ends[-1:], np.asarray([lo, hi])]
        if not self.is_phone:
            points += [self.wear.off_start, self.wear.off_end]
        rec_s = np.asarray([w.start for w in self.workouts])
        rec_e = np.asarray([w.end for w in self.workouts])
        points += [rec_s, rec_e]
        bps = np.unique(np.clip(np.concatenate(points), lo, hi))
        a, b = bps[:-1], bps[1:]
        mid = (a + b) / 2
        idx = np.clip(np.searchsorted(starts, mid, side="right") - 1, 0, len(starts) - 1)
        on = self.carried[idx] if self.is_phone and self.carried is not None else self.wear.worn(mid)
        order = np.argsort(rec_s) if len(rec_s) else np.zeros(0, dtype=int)
        rs, re = rec_s[order], rec_e[order]
        k = np.searchsorted(rs, mid, side="right") - 1
        inside = (k >= 0) & (mid < re[np.clip(k, 0, None)]) if len(rs) else np.zeros(mid.shape, dtype=bool)
        workout = np.where(inside, order[np.clip(k, 0, None)] if len(rs) else 0, -1)
        state = cols["state"][idx]
        activity = cols["activity"][idx]
        # "moving" matches the calibration's definition: stepping at >= 60 steps/min (or a
        # non-stepping effort such as cycling); light puttering counts as still.
        cadence = cols["cadence"][idx]
        effort = (state == 4) | np.isin(activity, CYCLING_ACTIVITIES)
        still = (state == SEDENTARY) | np.isin(activity, STILL_ACTIVITIES) | ((cadence < 60) & ~effort)
        ctx = np.where(
            inside,
            CTX_WORKOUT,
            np.where(np.isin(state, list(SLEEP_STATES)), CTX_SLEEP, np.where(still, CTX_STILL, CTX_MOVING)),
        ).astype(np.int8)
        self.seg_start, self.seg_end, self.seg_idx = a, b, idx
        self.seg_on, self.seg_ctx, self.seg_workout = on, ctx, workout.astype(np.int64)

    def rate(self, quantity: str) -> np.ndarray:
        cols = self.timeline.columns
        p = self.persona
        if quantity == "steps":
            return cols["cadence"].astype(np.float64) / 60.0
        if quantity == "distance_walking_running":
            return np.where(np.isin(cols["activity"], NO_FOOT_DISTANCE), 0.0, cols["speed"].astype(np.float64))
        if quantity == "distance_cycling":
            return np.where(cols["activity"] == ACTIVITY_INDEX["cycle"], cols["speed"].astype(np.float64), 0.0)
        if quantity == "active_energy":
            return np.clip(cols["met"].astype(np.float64) - 1.0, 0, None) * p.weight_kg / 3600.0
        if quantity == "basal_energy":
            bmr = 10 * p.weight_kg + 6.25 * p.height_cm - 5 * p.age + (5 if p.sex == "M" else -161)
            return np.full(len(cols["start"]), bmr / 86400.0)
        if quantity == "flights_climbed":
            return cols["flights"].astype(np.float64) / np.maximum(cols["end"] - cols["start"], 1.0)
        if quantity == "met":
            return cols["met"].astype(np.float64)
        if quantity == "audio":
            return cols["audio_db"].astype(np.float64)
        if quantity == "headphones":
            level = 70.0 + 4.0 * self.traits.get("headphone_level", 0.0)
            return np.where(cols["headphones"], level, 0.0)
        if quantity == "daylight":
            return np.where(cols["outdoors"] & self._sun_up(), 1 / 60.0, 0.0)
        if quantity == "upright":
            return np.where(cols["upright"], 1.0, 0.0)
        raise KeyError(quantity)

    def _sun_up(self) -> np.ndarray:
        cols = self.timeline.columns
        mid = (cols["start"] + cols["end"]) / 2
        offsets = self.tz.offsets(mid).astype(np.float64)
        local = ((mid + offsets * 60) % DAY) / 3600
        doy = np.asarray([d.timetuple().tm_yday for d in self.plan.days])[cols["day"]]
        decl = 23.44 * np.sin(np.radians(360 / 365 * (doy - 81)))
        x = -np.tan(np.radians(self.persona.latitude)) * np.tan(np.radians(decl))
        half = np.degrees(np.arccos(np.clip(x, -1, 1))) / 15
        return (local > 12 - half) & (local < 12 + half)

    def cumulative(self, rate: np.ndarray, *, on_only: bool = True) -> tuple[np.ndarray, np.ndarray]:
        r = rate[self.seg_idx] * (self.seg_on if on_only else 1.0)
        dur = self.seg_end - self.seg_start
        c = np.concatenate([[0.0], np.cumsum(r * dur)])
        return np.concatenate([self.seg_start, self.seg_end[-1:]]) if len(self.seg_start) else np.zeros(1), c

    def integral(self, rate: np.ndarray, a: np.ndarray, b: np.ndarray, *, on_only: bool = True) -> np.ndarray:
        """Integral of a per-interval rate between ``a`` and ``b``. With ``on_only``, only time the device is on
        counts.
        """
        x, c = self.cumulative(rate, on_only=on_only)
        return np.interp(b, x, c) - np.interp(a, x, c)

    # Gates
    def _version_from(self, required: int) -> float:
        """Instant from which the persona's OS is at least ``required`` (older versions assumed installed)."""
        listed = sorted(int(v) for v in self.os_adoption if v.isdigit())
        if not listed or required <= listed[0]:
            return -np.inf
        later = [v for v in listed if v >= required]
        return self.os_adoption[str(later[0])] if later else np.inf

    def gate(self, metric: str, times: np.ndarray, feature: str | None = None) -> np.ndarray:
        """Platform type availability, OS version and hardware feature release gates."""
        registry = self.params["platforms"]["metrics"][metric]
        platform = self.period.platform
        if platform not in registry:
            return np.zeros(times.shape, dtype=bool)
        ok = np.ones(times.shape, dtype=bool)
        if platform == "healthkit" and "requires_ios" in registry:
            ok &= times >= self._version_from(int(registry["requires_ios"]))
        if feature is not None:
            if feature not in self.spec.get("features", ()):
                return np.zeros(times.shape, dtype=bool)
            since = self.spec.get("features_since", {}).get(feature)
            if since:
                ok &= times >= utc_seconds(date.fromisoformat(since)) + self.os_adoption.get("lag", 0.0)
        return ok
