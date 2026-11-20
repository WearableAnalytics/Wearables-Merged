"""Joint persona sampler.

Attributes are drawn along a fixed causal order so correlated traits stay correlated:
cohort -> age -> sex -> BMI -> archetype -> fitness -> resting HR / HRV -> routine ->
clinical backbone (Synthea or sampled) -> habits. Anchors are exact twins or variants
around the owner's two exports; their personal values arrive through a calibration
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from ..config import Params
from ..rng import Streams
from ..util import interp_table, logistic, uniform
from .clinical import ClinicalTimeline, classify, clinical_from_synthea, sample_clinical
from .synthea import SyntheaPatient

ARCHETYPES = ("sedentary", "weekend_warrior", "regular_exerciser", "athlete", "older_daily_walker")
TRAJECTORIES = ("stable", "improving", "declining", "episodic", "event_shaped")


@dataclass(slots=True)
class Persona:
    patient_id: str
    synthea_reused: bool
    index: int
    cohort: str
    anchor: str | None
    anchor_kind: str | None
    age: int
    sex: str
    height_cm: float
    weight_kg: float
    bmi: float
    timezone: str
    latitude: float
    longitude: float
    archetype: str
    occupation: str
    activity_level: float
    light_multiplier: float
    vo2max: float
    rhr: float
    ln_rmssd: float
    hrmax: float
    respiratory_rate: float
    spo2: float
    wrist_temperature: float
    hr_on_tau: float
    hr_off_tau: float
    recovery_slow_fraction: float
    recovery_slow_tau: float
    effort_gain: float
    sleep_debt_rhr: float
    medication_response: float
    lf_hf_ratio: float
    midsleep_hour: float
    weekend_shift_hours: float
    sleep_need_hours: float
    regularity_minutes: float
    nap_probability: float
    trajectory: str
    workout_plan: tuple[tuple[str, float, float, float, float], ...]
    preferred_slots: Mapping[str, float]
    weekend_only: bool
    double_session_probability: float
    abandonment_multiplier: float
    micro_workouts: bool
    nutrition_logger: bool
    weight_logger: str | None  # None | "manual" | "scale"
    bp_cuff: bool
    headphone_listener: bool
    alcohol_drinks_per_day: float  # 0 = does not log alcohol
    height_logger: bool
    ecg_per_week: float  # 0 = never takes on-demand ECGs
    afib_history: bool  # Apple AFib History enabled
    stride_m: float
    double_support_pct: float
    asymmetry_pct: float
    clinical: ClinicalTimeline = field(repr=False)
    traits: Mapping[str, float] = field(default_factory=dict)
    dose_log: Mapping[date, float | None] | None = field(
        default=None, repr=False
    )  # date -> local hour (None = time unknown)

    def row(self) -> dict[str, Any]:
        data = {f.name: getattr(self, f.name) for f in fields(self) if f.name not in ("clinical", "traits", "dose_log")}
        clinical = self.clinical
        data["workout_plan"] = [
            {"type": w[0], "per_week": w[1], "minutes": w[2], "minutes_sigma": w[3], "record_propensity": w[4]}
            for w in self.workout_plan
        ]
        data["preferred_slots"] = dict(self.preferred_slots)
        data["conditions"] = [c.name for c in clinical.conditions]
        data["medications"] = [m.cls for m in clinical.medications]
        data["synthea_id"] = clinical.synthea_id
        return data


def _band(bands: Sequence[int], age: float) -> int:
    return max(i for i, low in enumerate(bands) if age >= low) if age >= bands[0] else 0


def _pick(rng: np.random.Generator, names: Sequence[str], weights: Sequence[float] | np.ndarray) -> str:
    p = np.asarray(weights, dtype=float)
    return names[int(rng.choice(len(names), p=p / p.sum()))]


@dataclass(frozen=True, slots=True)
class PersonaContext:
    params: Params
    seed: int
    window: tuple[date, date]
    twins: bool
    roster: Sequence[SyntheaPatient] | None = None
    assignment: Mapping[int, tuple[int, bool, str]] | None = None  # persona -> (roster index, reused, cohort)
    wearable_only: bool = False


def _cohort(
    ctx: PersonaContext, index: int, rng: np.random.Generator
) -> tuple[Mapping[str, Any] | None, str | None, str | None]:
    cohorts = ctx.params["cohorts"]
    anchors = cohorts["anchors"]
    profiles = list(anchors["profiles"])
    if ctx.twins and index < len(profiles):
        return None, profiles[index], "twin"
    u = rng.random()
    if u < anchors["share"] and profiles:
        return None, profiles[int(rng.integers(len(profiles)))], "variant"
    if ctx.wearable_only:
        return None, None, None
    shares = np.asarray([c["share"] for c in cohorts["cohorts"]], dtype=float)
    chosen = cohorts["cohorts"][int(rng.choice(len(shares), p=shares / shares.sum()))]
    return chosen, None, None


def _vary(rng: np.random.Generator, value: float, sigma: float, kind: str | None) -> float:
    return value if kind == "twin" else float(value * np.exp(rng.normal(0, sigma)))


def cohort_of(index: int, params: Params, seed: int, twins: bool) -> tuple[str, str | None]:
    """Cohort name (or ``anchor``) for one persona, from its own stream only."""
    ctx = PersonaContext(params, seed, (date.min, date.min), twins)
    cohort, anchor, _ = _cohort(ctx, index, Streams(seed, index)("cohort"))
    if anchor or cohort is None:
        return "anchor", anchor
    return str(cohort["name"]), None


def _eligible(patient: SyntheaPatient, cohort: Mapping[str, Any], params: Params, window: tuple[date, date]) -> bool:
    age = patient.age_on(window[0])
    if not cohort["age"][0] <= age <= cohort["age"][1] or (patient.death is not None and patient.death <= window[1]):
        return False
    required = set(cohort.get("require_any", ()))
    if not required:
        return True
    names = {
        classify(params["clinical"]["conditions"], e.description, e.code)
        for e in patient.conditions
        if e.start < window[1] and (e.stop is None or e.stop > window[0])
    }
    return bool(names & required)


def assign_roster(
    params: Params,
    seed: int,
    twins: bool,
    window: tuple[date, date],
    roster: Sequence[SyntheaPatient],
    order: np.ndarray,
    indices: range,
) -> dict[int, tuple[int, bool, str]]:
    """Map personas to roster patients per cohort.

    The k-th persona of a cohort (counting from persona 0, so the result never depends on
    sharding) takes the k-th eligible patient in a seeded roster permutation. Patients are
    reused only once a cohort's pool is exhausted, and such personas are flagged.
    """
    cohorts = {c["name"]: c for c in params["cohorts"]["cohorts"]}
    pools = {
        name: [int(j) for j in order if _eligible(roster[int(j)], spec, params, window)]
        for name, spec in cohorts.items()
    }
    general = next(name for name, c in cohorts.items() if not c.get("require_any"))
    seen: dict[str, int] = {}
    result: dict[int, tuple[int, bool, str]] = {}
    for i in range(indices.stop):
        name, _ = cohort_of(i, params, seed, twins)
        if name == "anchor":
            continue
        target = name if pools[name] else general
        pool = pools[target]
        if not pool:
            raise ValueError("Synthea roster has no eligible adults for the general cohort in this window")
        k = seen.get(target, 0)
        seen[target] = k + 1
        if i >= indices.start:
            result[i] = (pool[k % len(pool)], k >= len(pool), target)
    return result


def sample_persona(index: int, ctx: PersonaContext) -> Persona:
    """Sample persona ``index`` deterministically from the run seed."""
    params = ctx.params
    streams = Streams(ctx.seed, index)
    rng = streams("persona")
    pop = params["population"]
    # TODO(realism): Fit joint population trait spreads from training people, shrink
    # correlations, and check nearest-participant distances before retiring LifeSnaps anchors.
    demo = pop["demographics"]
    cohort, anchor, anchor_kind = _cohort(ctx, index, streams("cohort"))
    anchor_spec: Mapping[str, Any] = params["cohorts"]["anchors"]["profiles"][anchor] if anchor else {}
    traits: dict[str, float] = dict(anchor_spec.get("traits", {}))
    anchors = params["cohorts"]["anchors"]
    scale = float(anchors["variant_scale_sigma"])

    def trait(name: str, default: float) -> float:
        if name in traits:
            return _vary(rng, float(traits[name]), scale, anchor_kind)
        return default

    # Synthea roster patient (if any) fixes age, sex and the clinical backbone. Cohorts keep
    # their target shares; ``assign_roster`` picks a matching patient for each persona.
    patient: SyntheaPatient | None = None
    reused = False
    if ctx.roster is not None and ctx.assignment is not None and index in ctx.assignment:
        position, reused, matched_cohort = ctx.assignment[index]
        patient = ctx.roster[position]
        cohort = next(c for c in params["cohorts"]["cohorts"] if c["name"] == matched_cohort)

    if anchor:
        age = (
            int(anchor_spec["age"])
            if anchor_kind == "twin"
            else round(rng.normal(anchor_spec["age"], anchors["variant_age_sigma"]))
        )
        sex = str(anchor_spec["sex"])
    elif patient is not None:
        age, sex = patient.age_on(ctx.window[0]), patient.sex
    else:
        low, high = cohort["age"] if cohort else (18, 90)
        # Mild skew towards younger adults among app users (assumption).
        age = int(low + (high - low) * rng.beta(1.3, 1.7))
        sex = "F" if rng.random() < demo["female_share"] else "M"
    if patient is None:
        age = int(np.clip(age, 18, 95))

    zones = demo["timezones"]
    zone_index = int(rng.choice(len(zones["names"]), p=np.asarray(zones["weights"]) / sum(zones["weights"])))
    timezone = str(anchor_spec.get("timezone", zones["names"][zone_index]))
    latitude = float(anchor_spec.get("latitude", zones["latitudes"][zone_index])) + float(rng.normal(0, 0.15))
    longitude = float(anchor_spec.get("longitude", zones["longitudes"][zone_index])) + float(rng.normal(0, 0.15))

    bands = pop["archetype_bands"]
    if anchor:
        archetype = str(anchor_spec["archetype"])
    else:
        archetype = _pick(rng, bands["names"], bands["weights"][_band(bands["bands"], age)])
    arch = pop["archetype"][archetype]

    # BMI is conditioned on age and archetype (active people are leaner on average).
    height = trait(
        "height_cm",
        float(rng.normal(demo["height_mean_cm"]["female" if sex == "F" else "male"], demo["height_sigma_cm"])),
    )
    ln_bmi = interp_table(demo["bmi_log_mean_by_age"], age) + float(arch.get("ln_bmi_shift", 0.0))
    bmi = trait("bmi", float(np.clip(np.exp(rng.normal(ln_bmi, demo["bmi_log_sigma"])), *demo["bmi_range"])))
    weight = trait("weight_kg", bmi * (height / 100) ** 2)
    bmi = weight / (height / 100) ** 2

    fit = pop["fitness"]
    norm = interp_table(fit["vo2max_mean_female" if sex == "F" else "vo2max_mean_male"], age)
    vo2 = (
        norm
        + fit["vo2max_sigma"] * (arch["vo2max_z"] + 0.6 * rng.standard_normal())
        + fit["bmi_slope"] * max(0.0, bmi - 25)
    )
    vo2 = trait("vo2max", float(np.clip(vo2, *fit["range"])))

    base = pop["baselines"]
    rhr = (
        base["rhr_intercept"] + base["rhr_vo2_slope"] * (vo2 - norm) + (base["rhr_female_delta"] if sex == "F" else 0.0)
    )
    rhr += base["rhr_bmi_slope"] * (bmi - 25) + base["rhr_sigma"] * rng.standard_normal()
    rhr = trait("rhr", float(np.clip(rhr, *base["rhr_range"])))
    ln_rmssd = base["ln_rmssd_intercept"] + base["ln_rmssd_age_slope"] * (age - 20)
    ln_rmssd += base["ln_rmssd_fitness_slope"] * (vo2 - norm) + base["ln_rmssd_sigma"] * rng.standard_normal()
    ln_rmssd = trait("ln_rmssd", float(ln_rmssd))
    hrmax = trait(
        "hrmax",
        float(base["hrmax_intercept"] + base["hrmax_age_slope"] * age + base["hrmax_sigma"] * rng.standard_normal()),
    )

    resp = pop["responsiveness"]
    routine = pop["routine"]
    if anchor:
        occupation = str(anchor_spec.get("occupation", "office" if age < 65 else "retired"))
    else:
        occ = pop["occupations"]
        occupation = _pick(rng, occ["names"], occ["weights"][_band(occ["bands"], age)])

    # Trajectory: cohort weights override the population default; conditions nudge it.
    trajectories = params["physiology"]["trajectories"]
    weights = np.asarray(
        cohort.get("trajectory_weights", trajectories["weights"]) if cohort else trajectories["weights"], dtype=float
    )

    window = ctx.window
    response = trait("medication_response", uniform(rng, resp["medication_response"]))
    clinical_rng = streams("clinical")
    clinical_params = params["clinical"]
    if patient is not None:
        clinical = clinical_from_synthea(
            patient, window=window, params=clinical_params, response=response, rng=clinical_rng
        )
    elif anchor:
        clinical = sample_clinical(
            age=age,
            sex=sex,
            bmi=bmi,
            window=window,
            params=clinical_params,
            response=response,
            rng=clinical_rng,
            require_any=tuple(cohort["require_any"]) if cohort else (),
            forced_conditions=tuple(anchor_spec.get("conditions", ())),
            forced_medications=tuple(anchor_spec.get("medications", ())),
            overrides=traits,
        )
        clinical.conditions = [c for c in clinical.conditions if c.name in anchor_spec.get("conditions", ())]
        clinical.medications = [m for m in clinical.medications if m.cls in anchor_spec.get("medications", ())]
    else:
        clinical = ClinicalTimeline([], [], [])
    effects = clinical_params["conditions"]
    episodic = any(effects[c.name]["effects"].get("episodic", 0) for c in clinical.conditions)
    if episodic:
        weights = weights * np.asarray([0.6, 1.0, 1.0, 3.0, 1.0])
    if not clinical.procedures:
        weights[4] = 0.0
    if not clinical.conditions and not anchor:
        weights[3] = 0.0
    trajectory = str(
        anchor_spec.get("trajectory", "stable")
        if anchor
        else _pick(rng, TRAJECTORIES, weights if weights.sum() > 0 else [1, 0, 0, 0, 0])
    )

    regularity_factor = float(
        np.prod([effects[c.name]["effects"].get("regularity", 1.0) for c in clinical.conditions] or [1.0])
    )
    low, high = resp["regularity_minutes"]
    regularity = trait("regularity_minutes", float(np.exp(rng.uniform(np.log(low), np.log(high)))) * regularity_factor)

    habits = pop["habits"]
    hypertensive = any(c.name == "hypertension" for c in clinical.conditions)
    has_af = any(c.name == "atrial_fibrillation" for c in clinical.conditions)
    weight_logger: str | None = None
    u = rng.random()
    if u < habits["smart_scale_share"]:
        weight_logger = "scale"
    elif u < habits["smart_scale_share"] + habits["manual_weight_logger_share"]:
        weight_logger = "manual"
    gait = params["physiology"]["gait"]
    plan = tuple(tuple(w) for w in arch["workouts"])
    micro = (
        bool(traits.get("micro_workouts", 0) >= 0.5) if anchor else bool(rng.random() < habits["micro_workout_share"])
    )
    nutrition = (
        bool(traits.get("nutrition_logger", 0) >= 0.5)
        if anchor
        else bool(rng.random() < habits["nutrition_logger_share"])
    )

    persona = Persona(
        patient_id=f"synthetic-{ctx.seed}-{index:07d}",
        synthea_reused=reused,
        index=index,
        cohort=cohort["name"] if cohort else "anchor" if anchor else "wearable_only",
        anchor=anchor,
        anchor_kind=anchor_kind,
        age=age,
        sex=sex,
        height_cm=round(height, 1),
        weight_kg=round(weight, 1),
        bmi=round(bmi, 2),
        timezone=timezone,
        latitude=round(latitude, 4),
        longitude=round(longitude, 4),
        archetype=archetype,
        occupation=occupation,
        activity_level=trait(
            "activity_level", float(np.clip(arch["activity_level"] + 0.12 * rng.standard_normal(), 0.02, 1.0))
        ),
        light_multiplier=float(arch["light_multiplier"]),
        vo2max=round(vo2, 2),
        rhr=round(rhr, 2),
        ln_rmssd=round(ln_rmssd, 4),
        hrmax=round(hrmax, 1),
        respiratory_rate=trait(
            "respiratory_rate", float(rng.normal(base["respiratory_rate_mean"], base["respiratory_rate_sigma"]))
        ),
        spo2=trait("spo2", float(np.clip(rng.normal(base["spo2_mean"], base["spo2_sigma"]), 92, 99.5))),
        wrist_temperature=float(rng.normal(base["wrist_temperature_mean"], base["wrist_temperature_sigma"])),
        hr_on_tau=trait("hr_on_tau", uniform(rng, resp["hr_on_tau_seconds"])),
        hr_off_tau=trait("hr_off_tau", uniform(rng, resp["hr_off_tau_seconds"])),
        recovery_slow_fraction=uniform(rng, resp["recovery_slow_fraction"]),
        recovery_slow_tau=uniform(rng, resp["recovery_slow_tau_seconds"]),
        effort_gain=trait("effort_gain", uniform(rng, resp["effort_gain"])),
        sleep_debt_rhr=uniform(rng, resp["sleep_debt_rhr_per_hour"]),
        medication_response=response,
        lf_hf_ratio=uniform(rng, params["physiology"]["hrv"]["lf_to_hf_ratio"]),
        midsleep_hour=trait(
            "midsleep_hour", float(rng.normal(interp_table(routine["midsleep_by_age"], age), routine["midsleep_sigma"]))
        ),
        weekend_shift_hours=trait(
            "weekend_shift_hours", float(max(0.0, rng.normal(interp_table(routine["weekend_shift_by_age"], age), 0.4)))
        ),
        sleep_need_hours=trait(
            "sleep_need_hours",
            float(rng.normal(interp_table(routine["sleep_need_hours_by_age"], age), routine["sleep_need_sigma"])),
        ),
        regularity_minutes=regularity,
        nap_probability=interp_table(routine["nap_probability_by_age"], age),
        trajectory=trajectory,
        workout_plan=plan,  # type: ignore[arg-type]
        preferred_slots=arch["preferred_slots"],
        weekend_only=bool(arch.get("weekend_only", False)),
        double_session_probability=float(arch.get("double_session_probability", 0.0)),
        abandonment_multiplier=float(arch["abandonment_multiplier"]),
        micro_workouts=micro,
        nutrition_logger=nutrition,
        weight_logger=weight_logger,
        bp_cuff=hypertensive and rng.random() < habits["bp_cuff_share_hypertensive"],
        headphone_listener=bool(rng.random() < habits["headphone_listener_share"] * logistic((50 - age) / 15) * 1.4),
        alcohol_drinks_per_day=float(rng.uniform(*habits["alcohol_drinks_per_day"]))
        if rng.random() < habits["alcohol_logger_share"]
        else 0.0,
        height_logger=bool(rng.random() < habits["height_logger_share"]),
        ecg_per_week=(
            float(traits["ecg_per_week"])
            if "ecg_per_week" in traits
            else float(rng.uniform(*habits["ecg_per_week"]))
            if rng.random() < habits["ecg_user_share"] * (4 if has_af else 1)
            else 0.0
        ),
        afib_history=False
        if ctx.wearable_only and not anchor
        else bool(traits.get("afib_history", 0) >= 0.5)
        if "afib_history" in traits
        else bool(rng.random() < habits["afib_history_share"]["atrial_fibrillation" if has_af else "other"]),
        stride_m=round(height / 100 * gait["step_length_per_height"] * float(np.exp(rng.normal(0, 0.05))), 3),
        double_support_pct=float(
            rng.normal(interp_table(gait["double_support_by_age"], age), gait["double_support_sigma"])
        ),
        asymmetry_pct=float(rng.lognormal(np.log(gait["asymmetry_median"]), 0.6)),
        clinical=clinical,
        traits=traits,
        dose_log=load_dose_log(Path(anchor_spec["dose_log"]))
        if anchor_kind == "twin" and anchor_spec.get("dose_log")
        else None,
    )
    return persona


def load_dose_log(path: Path) -> dict[date, float | None]:
    """Read a stimulant dose log CSV with columns ``date`` and optional ``time`` (HH:MM, local).

    Every date in the log's range that has no row is a skip day.
    """
    from csv import DictReader

    log: dict[date, float | None] = {}
    with path.open(encoding="utf-8", newline="") as stream:
        for row in DictReader(stream):
            day = date.fromisoformat(row["date"].strip())
            text = (row.get("time") or "").strip()
            hour = None
            if text:
                h, m = text.split(":")[:2]
                hour = int(h) + int(m) / 60
            log[day] = hour
    return log
