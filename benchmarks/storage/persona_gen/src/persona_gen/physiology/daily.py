"""Per-day latent state and long-run trajectories (vectorized over days).

The base state is built before the behaviour timeline. Sleep debt and the day after a
hard workout feed back into resting HR once the timeline is known (``finalize``).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from ..behavior.events import EventPlan
from ..model import Medication
from ..persona.sampler import Persona


@dataclass(slots=True)
class DailyState:
    days: list[date]
    vo2max: np.ndarray
    rhr: np.ndarray
    ln_rmssd: np.ndarray
    activity: np.ndarray  # multiplier on light/walk time
    workout: np.ndarray  # multiplier on workout probability
    sleep_extra_hours: np.ndarray
    wear: np.ndarray  # multiplier on daily wear probability
    temperature_delta: np.ndarray
    respiratory_delta: np.ndarray
    spo2_delta: np.ndarray
    spo2_sleep_delta: np.ndarray
    hrmax_multiplier: np.ndarray
    exercise_gain: np.ndarray
    hr_noise: np.ndarray
    medication_rhr: np.ndarray
    condition_rhr: np.ndarray
    stimulant: list[Medication | None]
    afib_burden: np.ndarray
    awakenings_multiplier: np.ndarray
    breathing_disturbances: np.ndarray
    systolic_delta: np.ndarray
    sleep_debt: np.ndarray
    sleep_hours: np.ndarray

    def row(self, i: int) -> dict[str, Any]:
        return {
            "date": self.days[i],
            "vo2max": float(self.vo2max[i]),
            "rhr": float(self.rhr[i]),
            "ln_rmssd": float(self.ln_rmssd[i]),
            "activity_multiplier": float(self.activity[i]),
            "workout_multiplier": float(self.workout[i]),
            "sleep_debt_hours": float(self.sleep_debt[i]),
            "sleep_hours": float(self.sleep_hours[i]),
            "medication_rhr_delta": float(self.medication_rhr[i]),
            "condition_rhr_delta": float(self.condition_rhr[i]),
            "temperature_delta": float(self.temperature_delta[i]),
            "stimulant_active": self.stimulant[i] is not None,
            "hrmax_multiplier": float(self.hrmax_multiplier[i]),
        }


def _ar1(rng: np.random.Generator, n: int, phi: float, sigma: float) -> np.ndarray:
    noise = rng.normal(0.0, sigma * np.sqrt(1 - phi**2), n)
    out = np.empty(n)
    out[0] = rng.normal(0.0, sigma)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + noise[i]
    return out


def _active_ramp(day_numbers: np.ndarray, start: date, stop: date | None, onset: float) -> np.ndarray:
    s = start.toordinal()
    ramp_up = np.clip((day_numbers - s + 1) / max(onset, 1.0), 0.0, 1.0)
    if stop is None:
        return ramp_up
    e = stop.toordinal()
    washout = np.clip(1.0 - (day_numbers - e) / max(onset, 1.0), 0.0, 1.0)
    return np.where(day_numbers < e, ramp_up, np.minimum(ramp_up, washout))


def base_state(persona: Persona, plan: EventPlan, params: Mapping[str, Any], rng: np.random.Generator) -> DailyState:
    # TODO(realism): Fit day-level autocorrelation, weekend effects and sleep spread
    # on training participants and verify the fit against the participant holdout.
    days = plan.days
    n = len(days)
    phys = params["physiology"]
    daily = phys["daily"]
    traj = phys["trajectories"]
    clinical = params["clinical"]
    behavior = params["behavior"]["events"]
    ordinals = np.asarray([d.toordinal() for d in days], dtype=float)
    t_days = ordinals - ordinals[0]
    # Season peaks mid-summer in the persona's hemisphere.
    doy = np.asarray([d.timetuple().tm_yday for d in days], dtype=float)
    summer = np.cos(2 * np.pi * (doy - (196 if persona.latitude >= 0 else 15)) / 365.25)

    vo2_factor = np.ones(n)
    activity_trend = np.ones(n)
    if persona.trajectory == "improving":
        gain = rng.uniform(*traj["improving_vo2_gain"])
        ramp = rng.uniform(*traj["improving_ramp_days"])
        vo2_factor = 1 + gain * np.clip(t_days / ramp, 0, 1)
        activity_trend = 1 + 0.5 * gain * np.clip(t_days / ramp, 0, 1) * 4
    elif persona.trajectory == "declining":
        vo2_factor = 1 + rng.uniform(*traj["declining_vo2_per_year"]) * t_days / 365.25
        activity_trend = np.exp(rng.uniform(*traj["declining_activity_per_year"]) * t_days / 365.25)

    cond_rhr = np.zeros(n)
    cond_lnr = np.zeros(n)
    cond_activity = np.ones(n)
    cond_wear = np.ones(n)
    spo2 = np.zeros(n)
    spo2_sleep = np.zeros(n)
    resp = np.zeros(n)
    hr_noise = np.ones(n)
    afib = np.zeros(n)
    awakenings = np.ones(n)
    breathing = np.zeros(n)
    systolic = np.zeros(n)
    for condition in persona.clinical.conditions:
        effects = clinical["conditions"][condition.name]["effects"]
        active = (ordinals >= condition.onset.toordinal()) & (
            np.inf > ordinals if condition.stop is None else ordinals < condition.stop.toordinal()
        )
        a = active.astype(float)
        cond_rhr += a * effects.get("rhr", 0.0)
        cond_lnr += a * effects.get("ln_rmssd", 0.0)
        cond_activity *= np.where(active, effects.get("activity", 1.0), 1.0)
        cond_wear *= np.where(active, effects.get("wear", 1.0), 1.0)
        vo2_factor = vo2_factor * np.where(active, 1 + effects.get("vo2max_fraction", 0.0), 1.0)
        spo2 += a * effects.get("spo2", 0.0)
        spo2_sleep += a * effects.get("spo2_sleep", 0.0)
        resp += a * effects.get("respiratory_rate", 0.0)
        hr_noise *= np.where(active, effects.get("hr_noise", 1.0), 1.0)
        afib = np.maximum(afib, a * effects.get("afib_burden", 0.0))
        awakenings *= np.where(active, effects.get("awakenings", 1.0), 1.0)
        breathing += a * effects.get("breathing_disturbances", 0.0)
        systolic += a * effects.get("systolic", 0.0)

    med_rhr = np.zeros(n)
    med_lnr = np.zeros(n)
    hrmax_mult = np.ones(n)
    gain = np.ones(n)
    stimulant: list[Medication | None] = [None] * n
    for med in persona.clinical.medications:
        spec = clinical["medications"][med.cls]
        ramp = _active_ramp(ordinals, med.start, med.stop, float(spec.get("onset_days", 0.0)))
        med_rhr += ramp * med.rhr_delta
        med_lnr += ramp * spec.get("ln_rmssd_delta", 0.0)
        hrmax_mult *= 1 - ramp * (1 - spec.get("hrmax_multiplier", 1.0))
        gain *= 1 - ramp * (1 - spec.get("exercise_gain_multiplier", 1.0))
        systolic += ramp * spec.get("systolic_delta", 0.0)
        if spec.get("dosing") == "daily":
            for i in np.flatnonzero(ramp > 0):
                stimulant[int(i)] = med

    recovery = plan.recovery
    recovery_rhr = behavior["hospitalization"]["rhr_delta"] * np.clip((1 - recovery) / 0.8, 0, 1)
    vo2_factor = vo2_factor * (0.85 + 0.15 * recovery)
    vo2 = persona.vo2max * vo2_factor

    illness = params["behavior"]["events"]["illness"]
    rhr_noise = _ar1(rng, n, daily["rhr_ar"], daily["rhr_sigma"])
    rhr = (
        persona.rhr
        - 0.75 * (vo2 - persona.vo2max)
        + rhr_noise
        + daily["seasonal_rhr_amplitude"] * -summer
        + plan.illness_rhr
        + cond_rhr
        + med_rhr
        + recovery_rhr
    )
    ln_rmssd = (
        persona.ln_rmssd
        + _ar1(rng, n, daily["ln_rmssd_ar"], daily["ln_rmssd_sigma"])
        + daily["ln_rmssd_per_rhr"] * (rhr_noise + plan.illness_rhr)
        + illness["ln_rmssd_delta"] * plan.illness
        + cond_lnr
        + med_lnr
    )
    mood = params["behavior"]["events"]["mood_episode"]
    injury = params["behavior"]["events"]["injury"]
    travel = params["behavior"]["events"]["travel"]
    activity = (
        np.exp(
            _ar1(rng, n, daily["activity_ar"], daily["activity_sigma"]) + daily["seasonal_activity_amplitude"] * summer
        )
        * (1 - (1 - illness["activity_multiplier"]) * plan.illness)
        * np.where(plan.injury, injury["activity_multiplier"], 1.0)
        * (1 - (1 - mood["activity_multiplier"]) * plan.mood)
        * np.where(plan.vacation & ~plan.hospital, travel["vacation_activity_multiplier"], 1.0)
        * recovery
        * activity_trend
        * cond_activity
    )
    workout = (
        (1 - (1 - params["behavior"]["workouts"]["illness_multiplier"]) * plan.illness)
        * (1 - (1 - mood["workout_multiplier"]) * plan.mood)
        * np.where(recovery < 0.7, 0.0, 1.0)
        * np.where(plan.hospital, 0.0, 1.0)
        * np.clip(activity_trend, 0.3, 2.0)
        * np.sqrt(cond_activity)
    )
    wear = (
        (1 - (1 - illness["wear_multiplier"]) * plan.illness)
        * (1 - (1 - mood["wear_multiplier"]) * plan.mood)
        * cond_wear
    )
    return DailyState(
        days=days,
        vo2max=vo2,
        rhr=rhr,
        ln_rmssd=ln_rmssd,
        activity=activity,
        workout=workout,
        sleep_extra_hours=illness["sleep_extra_hours"] * plan.illness + plan.mood_sleep_delta,
        wear=wear,
        temperature_delta=plan.fever,
        respiratory_delta=resp + phys["respiration"]["illness_delta"] * plan.illness,
        spo2_delta=spo2,
        spo2_sleep_delta=spo2_sleep,
        hrmax_multiplier=hrmax_mult,
        exercise_gain=gain,
        hr_noise=hr_noise,
        medication_rhr=med_rhr,
        condition_rhr=cond_rhr,
        stimulant=stimulant,
        afib_burden=afib,
        awakenings_multiplier=awakenings,
        breathing_disturbances=breathing,
        systolic_delta=systolic,
        sleep_debt=np.zeros(n),
        sleep_hours=np.zeros(n),
    )


def finalize(state: DailyState, persona: Persona, params: Mapping[str, Any], hard_days: np.ndarray) -> None:
    """Apply sleep-debt and post-hard-workout effects once the timeline is known."""
    daily = params["physiology"]["daily"]
    state.rhr = state.rhr + persona.sleep_debt_rhr * np.clip(state.sleep_debt, 0, 8)
    shifted = np.zeros_like(state.rhr)
    shifted[1:] = hard_days[:-1]
    state.rhr = state.rhr + daily["hard_workout_rhr_next_day"] * shifted
    state.ln_rmssd = state.ln_rmssd - 0.03 * np.clip(state.sleep_debt, 0, 8) - 0.05 * shifted
