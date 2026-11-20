"""Clinical backbone: conditions, medications and procedures with mid-timeline changes.

Synthea rosters are mapped to the condition and medication classes in ``clinical.toml``
by regular expression on their descriptions. Without a roster, conditions are sampled
from age/sex/BMI-dependent prevalence. Either way each medication gets persona-specific
effect sizes, and every start, stop and onset inside the window becomes a labelled event.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import numpy as np

from ..model import Condition, Medication
from ..util import interp_table, lognormal, uniform
from .synthea import SyntheaPatient


@dataclass(slots=True)
class ClinicalTimeline:
    conditions: list[Condition]
    medications: list[Medication]
    procedures: list[tuple[date, date, str]]
    synthea_id: str | None = None


@lru_cache(maxsize=64)
def _pattern(expression: str) -> re.Pattern[str]:
    return re.compile(expression, re.IGNORECASE)


def classify(table: Mapping[str, Any], description: str, code: str = "") -> str | None:
    text = f"{description} {code}"
    for name, spec in table.items():
        if _pattern(spec["pattern"]).search(text):
            return name
    return None


def medication_params(
    cls: str,
    spec: Mapping[str, Any],
    response: float,
    rng: np.random.Generator,
    overrides: Mapping[str, float] | None = None,
) -> tuple[float, dict[str, float]]:
    rhr = uniform(rng, spec.get("rhr_delta", (0.0, 0.0))) * response
    params: dict[str, float] = {}
    if spec.get("dosing") == "daily":
        params = {
            "tmax_hours": uniform(rng, spec["tmax_hours"]),
            "half_life_hours": uniform(rng, spec["half_life_hours"]),
            "awake_hr_delta": uniform(rng, spec["awake_hr_delta"]) * response,
            "dose_after_wake_hours": float(lognormal(rng, spec["dose_after_wake_hours"])),
        }
    if overrides and params:
        for name in ("awake_hr_delta", "tmax_hours", "half_life_hours"):
            if f"{cls}_{name}" in overrides:
                params[name] = float(overrides[f"{cls}_{name}"])
    return rhr, params


def _prevalence(spec: Mapping[str, Any], age: float, sex: str, bmi: float) -> float:
    base = interp_table(spec["prevalence_by_age"], age)
    if base <= 0:
        return 0.0
    odds = base / (1 - base)
    ratios = spec.get("odds_ratio", {})
    if sex == "M" and "male" in ratios:
        odds *= ratios["male"]
    if sex == "F" and "female" in ratios:
        odds *= ratios["female"]
    if "bmi_per_unit" in ratios:
        odds *= ratios["bmi_per_unit"] ** (bmi - 25.0)
    return odds / (1 + odds)


def _add_medications(
    condition: Condition,
    params: Mapping[str, Any],
    response: float,
    window: tuple[date, date],
    rng: np.random.Generator,
    overrides: Mapping[str, float] | None,
) -> list[Medication]:
    meds_table = params["medications"]
    sampler = params["sampler"]
    spec = params["conditions"][condition.name]
    result: list[Medication] = []
    for cls, probability in spec.get("medications", {}).items():
        if rng.random() >= probability:
            continue
        start = condition.onset + timedelta(days=float(lognormal(rng, sampler["medication_start_lag_days"])))
        stop = None
        horizon = (window[1] - start).days
        if horizon > 0:
            stop_after = rng.exponential(365.0 / sampler["medication_stop_rate_per_year"])
            if stop_after < horizon:
                stop = start + timedelta(days=float(stop_after))
        rhr, extra = medication_params(cls, meds_table[cls], response, rng, overrides)
        result.append(Medication(cls, cls, start, stop, rhr, "sampled", extra))
    return result


def sample_clinical(
    *,
    age: float,
    sex: str,
    bmi: float,
    window: tuple[date, date],
    params: Mapping[str, Any],
    response: float,
    rng: np.random.Generator,
    require_any: Sequence[str] = (),
    forced_conditions: Sequence[str] = (),
    forced_medications: Sequence[str] = (),
    overrides: Mapping[str, float] | None = None,
) -> ClinicalTimeline:
    conditions: list[Condition] = []
    start, end = window
    span_years = max((end - start).days, 1) / 365.25
    incidence = params["sampler"]["incidence_fraction_per_year"]
    for name, spec in params["conditions"].items():
        p = _prevalence(spec, age, sex, bmi)
        forced = name in forced_conditions
        if forced or rng.random() < p:
            onset = start - timedelta(days=float(rng.uniform(30, 3650)))
            conditions.append(Condition(name, onset))
        elif rng.random() < p * incidence * span_years:
            onset = start + timedelta(days=float(rng.uniform(0, (end - start).days)))
            conditions.append(Condition(name, onset))
    if require_any and not any(c.name in require_any for c in conditions):
        weights = np.asarray([_prevalence(params["conditions"][n], age, sex, bmi) + 1e-3 for n in require_any])
        name = require_any[int(rng.choice(len(require_any), p=weights / weights.sum()))]
        conditions.append(Condition(name, start - timedelta(days=float(rng.uniform(30, 1500)))))
    medications: list[Medication] = []
    for condition in conditions:
        for med in _add_medications(condition, params, response, window, rng, overrides):
            # One course per class: a second indication does not stack the same drug class.
            if not any(
                m.cls == med.cls and (m.stop is None or m.stop > med.start) and m.start <= (med.stop or med.start)
                for m in medications
            ):
                medications.append(med)
    sampler = params["sampler"]
    if rng.random() < float(sampler.get("scenario_probability", 0.0)):
        cls = str(sampler["scenario_medication"])
        days = max(1, (end - start).days)
        begin = start + timedelta(days=int(days * float(rng.uniform(0.25, 0.6))))
        if not any(m.cls == cls and (m.stop is None or m.stop > begin) for m in medications):
            rhr, extra = medication_params(cls, params["medications"][cls], response, rng, overrides)
            medications.append(Medication(cls, cls, begin, None, rhr, "scenario", extra))
    for cls in forced_medications:
        if not any(m.cls == cls for m in medications):
            rhr, extra = medication_params(cls, params["medications"][cls], response, rng, overrides)
            medications.append(Medication(cls, cls, start - timedelta(days=365), None, rhr, "anchor", extra))
    return ClinicalTimeline(conditions, medications, [])


def clinical_from_synthea(
    patient: SyntheaPatient,
    *,
    window: tuple[date, date],
    params: Mapping[str, Any],
    response: float,
    rng: np.random.Generator,
    overrides: Mapping[str, float] | None = None,
) -> ClinicalTimeline:
    """Map a Synthea patient's conditions, medications (refills merged into courses) and inpatient stays onto generator
    classes within the window.
    """
    start, end = window
    conditions: list[Condition] = []
    seen: set[str] = set()
    for entry in patient.conditions:
        name = classify(params["conditions"], entry.description, entry.code)
        if name is None or entry.start >= end or (entry.stop is not None and entry.stop <= start):
            continue
        if name in seen:
            continue
        seen.add(name)
        conditions.append(Condition(name, entry.start, entry.stop, entry.code, "synthea"))
    # Synthea writes each refill of a chronic prescription as its own row. Merge rows of the
    # same class separated by short gaps, so effects do not re-ramp at every refill.
    courses: dict[str, list[list[Any]]] = {}
    for entry in sorted(patient.medications, key=lambda e: (e.start, e.code)):
        cls = classify(params["medications"], entry.description, entry.code)
        if cls is None:
            continue
        runs = courses.setdefault(cls, [])
        if runs and (runs[-1][2] is None or entry.start <= runs[-1][2] + timedelta(days=14)):
            if runs[-1][2] is not None:
                runs[-1][2] = None if entry.stop is None else max(runs[-1][2], entry.stop)
        else:
            runs.append([entry.description or entry.code, entry.start, entry.stop])
    medications: list[Medication] = []
    for cls, runs in courses.items():
        for name, begin, stop in runs:
            if begin >= end or (stop is not None and stop <= start):
                continue
            rhr, extra = medication_params(cls, params["medications"][cls], response, rng, overrides)
            medications.append(Medication(cls, name, begin, stop, rhr, "synthea", extra))
    medications.sort(key=lambda m: (m.start, m.cls))
    # TODO(realism): Validate clinical events against the roster, including procedure-specific timelines.
    procedures = [
        (e.start, e.stop or e.start + timedelta(days=2), e.description or e.code)
        for e in patient.inpatient
        if e.start < end and (e.stop or e.start + timedelta(days=2)) >= start
    ]
    return ClinicalTimeline(conditions, medications, procedures, patient.id)


def add_procedure(
    timeline: ClinicalTimeline,
    *,
    name: str,
    window: tuple[date, date],
    params: Mapping[str, Any],
    post_medications: Mapping[str, float],
    response: float,
    rng: np.random.Generator,
    hospital_days: Sequence[float],
) -> None:
    """Insert a perioperative event inside the window (cardiac-surgery cohort)."""
    start, end = window
    days = (end - start).days
    offset = rng.uniform(0.15, 0.6) * days if days > 4 else 0
    admit = start + timedelta(days=int(offset))
    discharge = admit + timedelta(days=max(1, round(float(lognormal(rng, hospital_days)))))
    timeline.procedures.append((admit, discharge, name))
    for cls, probability in post_medications.items():
        if rng.random() < probability and not any(m.cls == cls and m.stop is None for m in timeline.medications):
            rhr, extra = medication_params(cls, params["medications"][cls], response, rng)
            timeline.medications.append(Medication(cls, cls, discharge, None, rhr, "procedure", extra))
