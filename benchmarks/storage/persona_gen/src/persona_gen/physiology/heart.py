"""Continuous-time heart rate, evaluated exactly at arbitrary timestamps.

HR(t) = resting HR of the day + circadian term + state elevation with first-order
kinetics (rise tau_on, biphasic recovery) + stimulant dose curve + cardiovascular drift
+ Ornstein-Uhlenbeck noise. Interval start values are chained once per timeline, and
any batch of timestamps is then evaluated. Cost should scales with samples requested.
"""

from collections.abc import Mapping
from math import exp
from typing import Any

import numpy as np

from ..behavior.timeline import Dose, Timeline
from ..model import BED_AWAKE, SEDENTARY, SLEEP_DEEP, SLEEP_LIGHT, SLEEP_REM, WORKOUT
from ..persona.sampler import Persona
from ..timeutil import HOUR
from .daily import DailyState


class HeartModel:
    """True heart rate as a function of time for one persona: kinetics toward each interval's target, circadian term,
    stimulant dose curve and exercise drift. Device error is added elsewhere.
    """

    def __init__(
        self, persona: Persona, timeline: Timeline, daily: DailyState, offsets: np.ndarray, params: Mapping[str, Any]
    ) -> None:
        heart = params["physiology"]["heart"]
        cols = timeline.columns
        self.p = persona
        self.cols = cols
        self.daily = daily
        self.starts = cols["start"]
        self.ends = cols["end"]
        self.offsets = offsets  # minutes, per interval start
        self.heart = heart
        day = cols["day"]
        state = cols["state"]
        rest = daily.rhr[day]
        hrmax = persona.hrmax * daily.hrmax_multiplier[day]
        gain = persona.effort_gain * daily.exercise_gain[day]
        stage = heart["sleep_stage_offsets"]
        offset = np.zeros(len(state), dtype=np.float64)
        offset[state == SEDENTARY] = heart["sedentary_offset"]
        offset[state == BED_AWAKE] = stage["awake"]
        offset[state == SLEEP_LIGHT] = stage["light"]
        offset[state == SLEEP_DEEP] = stage["deep"]
        offset[state == SLEEP_REM] = stage["rem"]
        elevation = cols["intensity"].astype(np.float64) * (hrmax - rest) * gain
        self.target = np.clip(rest + offset + np.where(state == SEDENTARY, 0.0, elevation), 32.0, hrmax)
        self.noise_scale = daily.hr_noise[day] * np.select(
            [state == SLEEP_LIGHT, state == SLEEP_DEEP, state == SLEEP_REM, state == BED_AWAKE],
            [
                heart["stage_noise_multiplier"]["light"],
                heart["stage_noise_multiplier"]["deep"],
                heart["stage_noise_multiplier"]["rem"],
                heart["stage_noise_multiplier"]["awake"],
            ],
            1.0,
        )
        self.workout = cols["workout"]
        self.is_workout = state == WORKOUT
        self._chain()
        self._doses(timeline.doses)
        # Workout start per interval for cardiovascular drift.
        first_start: dict[int, float] = {}
        for w in timeline.workouts:
            first_start[w.id] = w.start
        self.workout_start = (
            np.asarray([first_start.get(int(w), 0.0) for w in self.workout]) if len(self.workout) else np.zeros(0)
        )

    def _chain(self) -> None:
        p = self.p
        n = len(self.starts)
        v0 = np.empty(n)
        up = np.empty(n, dtype=bool)
        value = float(self.target[0]) if n else 0.0
        on, off, slow_f, slow = p.hr_on_tau, p.hr_off_tau, p.recovery_slow_fraction, p.recovery_slow_tau
        targets = self.target.tolist()
        durations = (self.ends - self.starts).tolist()
        for i in range(n):
            v0[i] = value
            target = targets[i]
            dt = durations[i]
            if target >= value:
                up[i] = True
                value = target + (value - target) * exp(-dt / on)
            else:
                up[i] = False
                value = target + (value - target) * ((1 - slow_f) * exp(-dt / off) + slow_f * exp(-dt / slow))
        self.v0 = v0
        self.up = up

    def _doses(self, doses: list[Dose]) -> None:
        self.dose_times = np.asarray([d.time for d in doses])
        tmax = np.asarray([d.tmax_hours for d in doses]) * HOUR
        self.dose_ke = np.log(2) / (np.asarray([d.half_life_hours for d in doses]) * HOUR)
        self.dose_delta = np.asarray([d.awake_hr_delta for d in doses])
        # Absorption rate from tmax = ln(ka/ke) / (ka - ke), solved by bisection on ka > ke.
        lo, hi = self.dose_ke * (1 + 1e-6), self.dose_ke * 1e4
        for _ in range(80):
            mid = np.sqrt(lo * hi)
            f = np.log(mid / self.dose_ke) / (mid - self.dose_ke) - tmax
            lo, hi = np.where(f > 0, mid, lo), np.where(f > 0, hi, mid)
        self.dose_ka = np.sqrt(lo * hi)
        self.dose_peak = np.exp(-self.dose_ke * tmax) - np.exp(-self.dose_ka * tmax)

    def index(self, times: np.ndarray) -> np.ndarray:
        return np.clip(np.searchsorted(self.starts, times, side="right") - 1, 0, max(0, len(self.starts) - 1))

    def stimulant(self, times: np.ndarray, idx: np.ndarray) -> np.ndarray:
        """Bateman-shaped effect normalized to each dose's peak HR delta (attenuated asleep)."""
        out = np.zeros_like(times, dtype=np.float64)
        if not len(self.dose_times):
            return out
        asleep = self.cols["state"][idx] >= SLEEP_LIGHT
        order = np.argsort(self.dose_times)
        for k in order:
            t0 = self.dose_times[k]
            lo, hi = np.searchsorted(times, [t0, t0 + 36 * HOUR]) if np.all(np.diff(times) >= 0) else (0, len(times))
            dt = times[lo:hi] - t0
            active = dt > 0
            ke, ka = self.dose_ke[k], self.dose_ka[k]
            curve = np.where(
                active, (np.exp(-ke * np.maximum(dt, 0)) - np.exp(-ka * np.maximum(dt, 0))) / self.dose_peak[k], 0.0
            )
            out[lo:hi] += self.dose_delta[k] * np.clip(curve, 0, None) * np.where(asleep[lo:hi], 0.4, 1.0)
        return out

    # TODO(realism): Fit and validate workout onset, effort and recovery curves.
    def deterministic(self, times: np.ndarray, idx: np.ndarray | None = None) -> np.ndarray:
        idx = self.index(times) if idx is None else idx
        dt = np.maximum(times - self.starts[idx], 0.0)
        target = self.target[idx]
        v0 = self.v0[idx]
        p = self.p
        rise = target + (v0 - target) * np.exp(-dt / p.hr_on_tau)
        fall = target + (v0 - target) * (
            (1 - p.recovery_slow_fraction) * np.exp(-dt / p.hr_off_tau)
            + p.recovery_slow_fraction * np.exp(-dt / p.recovery_slow_tau)
        )
        value = np.where(self.up[idx], rise, fall)
        local = ((times + self.offsets[idx].astype(np.float64) * 60) % 86400) / HOUR
        heart = self.heart
        value += heart["circadian_amplitude"] * np.cos(2 * np.pi * (local - heart["circadian_peak_hour"]) / 24)
        stim = self.stimulant(times, idx)
        exercise = self.is_workout[idx]
        stim = np.where(exercise, stim * 0.6, stim)  # attenuated in absolute terms during effort
        value += stim
        if len(self.workout_start):
            elapsed = np.where(exercise, times - self.workout_start[idx], 0.0)
            value += heart["drift_bpm_per_hour"] * np.clip(elapsed / HOUR, 0, 3)
        return value

    def evaluate(self, times: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        if times.size == 0:
            return np.zeros(0)
        idx = self.index(times)
        value = self.deterministic(times, idx)
        sigma = self.heart["noise_sigma"] * self.noise_scale[idx]
        return np.clip(value + ou(times, self.heart["noise_tau_seconds"], rng) * sigma, 30.0, 230.0)


def ou(times: np.ndarray, tau: float, rng: np.random.Generator) -> np.ndarray:
    """Unit-variance Ornstein-Uhlenbeck process sampled exactly at sorted times.

    x_k = a_k x_{k-1} + sqrt(1 - a_k^2) z_k with a_k = exp(-dt_k / tau). Solved in blocks
    with cumulative log-decay so it stays vectorized without overflow.
    """
    n = times.size
    if n == 0:
        return np.zeros(0)
    z = rng.standard_normal(n)
    decay = np.minimum(np.diff(times, prepend=times[0]) / tau, 700.0)
    b = np.sqrt(-np.expm1(-2 * decay))
    b[0] = 1.0
    out = np.empty(n)
    state, k = 0.0, 0
    while k < n:
        cumulative = np.cumsum(decay[k : k + 8192])
        cut = max(1, int(np.searchsorted(cumulative, 500.0, side="right")))
        cumulative = cumulative[:cut]
        acc = np.cumsum(np.exp(cumulative) * b[k : k + cut] * z[k : k + cut])
        out[k : k + cut] = np.exp(-cumulative) * (state + acc)
        state = float(out[k + cut - 1])
        k += cut
    return out
