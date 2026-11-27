"""Mock data sources: one YAML file per scenario stands in for the gold serving tables and patient_context.

A scenario describes one patient: the personal baseline, the nights that differ from it, the descriptive context
(medications, diary notes, ...) and the candidates the upstream pipeline would raise (none, one or several nights).
No physiology is simulated; the numbers are written by hand so that each scenario tests one behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from ..dto import (
    AlertCandidate,
    ContextItem,
    ContextKind,
    DescriptiveContext,
    Fact,
    NightRow,
    NumericCondition,
    NumericContext,
)
from . import Match, condition_holds, visible_items

WINDOW_NIGHTS = 14
PREVIOUS_NIGHTS = 3

# name -> (unit, spread used for z). In production the baseline and z come from the gold job; here they are fixed.
SIGNALS: dict[str, tuple[str, float]] = {
    "rhr": ("bpm", 3.0),
    "hrv_sdnn": ("ms", 8.0),
    "wrist_temp_delta": ("°C", 0.2),
    "resp_rate": ("/min", 1.0),
    "spo2_mean": ("%", 1.0),
    "steps": ("steps", 2000.0),
}


class _Patient(BaseModel):
    id: str
    birth_year: int
    sex: str


class _ContextEntry(BaseModel):
    id: int
    kind: ContextKind
    ts: datetime | None = None
    text: str


class _Candidate(BaseModel):
    night: date
    trigger_reasons: list[str] = Field(default_factory=list)
    red_flag: bool = False
    l2_score: float | None = None
    expect: str | None = None  # the verdict a good triage gives this night


class Scenario(BaseModel):
    name: str
    summary: str
    patient: _Patient
    baseline: dict[str, float]
    nights: dict[date, dict[str, float | None]] = Field(default_factory=dict)
    coverage: dict[str, float] = Field(default_factory=dict)
    context: list[_ContextEntry] = Field(default_factory=list)
    candidates_: list[_Candidate] = Field(default_factory=list, alias="candidates")

    @model_validator(mode="before")
    @classmethod
    def _single_candidate(cls, data):
        """The first scenarios had one `candidate` and a top-level `expect`; keep reading them."""
        if isinstance(data, dict) and "candidate" in data:
            data = dict(data)
            candidate = dict(data.pop("candidate"))
            expect = data.pop("expect", None)
            if expect and "expect" not in candidate:
                candidate["expect"] = expect["verdict"]
            data["candidates"] = [candidate]
        return data

    @property
    def patient_id(self) -> str:
        return self.patient.id

    @property
    def night_date(self) -> date:
        """The latest flagged night."""
        return self._last().night

    @property
    def expect_verdict(self) -> str | None:
        return self._last().expect

    def candidates(self, candidate_id: int = 0) -> list[AlertCandidate]:
        return [self._to_candidate(c, candidate_id) for c in sorted(self.candidates_, key=lambda c: c.night)]

    def expected(self) -> list[tuple[AlertCandidate, str | None]]:
        ordered = sorted(self.candidates_, key=lambda c: c.night)
        return [(self._to_candidate(c, 0), c.expect) for c in ordered]

    def candidate(self, candidate_id: int) -> AlertCandidate:
        """The latest flagged night as a candidate."""
        return self._to_candidate(self._last(), candidate_id)

    def last_night(self) -> date:
        return max([*self.nights, *(c.night for c in self.candidates_)], default=date.min)

    def _last(self) -> _Candidate:
        if not self.candidates_:
            raise LookupError(f"scenario {self.name} has no flagged night")
        return max(self.candidates_, key=lambda c: c.night)

    def _to_candidate(self, c: _Candidate, candidate_id: int) -> AlertCandidate:
        return AlertCandidate(
            candidate_id=candidate_id,
            patient_id=self.patient_id,
            night_date=c.night,
            trigger_reasons=c.trigger_reasons,
            red_flag=c.red_flag,
            l2_score=c.l2_score,
        )

    def values_on(self, night: date) -> dict[str, float | None]:
        return {**self.baseline, **self.nights.get(night, {})}

    def context_items(self) -> list[ContextItem]:
        return [
            ContextItem(id=f"c:{e.id}", kind=e.kind, ts=e.ts, days_before=None, text=e.text.strip())
            for e in self.context
        ]


@dataclass
class ScenarioStore:
    scenarios: dict[str, Scenario]
    by_patient: dict[str, Scenario] = field(init=False)
    today: date = field(init=False)  # the latest night in the data; questions about 'last week' end here

    def __post_init__(self) -> None:
        self.today = max((s.last_night() for s in self.scenarios.values()), default=date.min)
        self.by_patient = {}
        for scenario in self.scenarios.values():
            if scenario.patient_id in self.by_patient:
                raise ValueError(f"patient {scenario.patient_id} is used by two scenarios")
            self.by_patient[scenario.patient_id] = scenario

    @classmethod
    def from_dir(cls, directory: Path) -> ScenarioStore:
        scenarios = {}
        for path in sorted(Path(directory).glob("*.yaml")):
            scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
            scenarios[scenario.name] = scenario
        return cls(scenarios)

    def names(self) -> list[str]:
        return list(self.scenarios)

    def get(self, name: str) -> Scenario:
        return self.scenarios[name]

    def patient_ids(self) -> list[str]:
        return sorted(self.by_patient)

    def patients(self) -> list[dict]:
        """What the UI may show about a patient: no name, no birth date."""
        out = []
        for pid in self.patient_ids():
            s = self.by_patient[pid]
            out.append(
                {
                    "patient_id": pid,
                    "age_band": age_band(self.today.year - s.patient.birth_year),
                    "sex": s.patient.sex,
                    "flagged_nights": [c.night_date.isoformat() for c in s.candidates()],
                }
            )
        return out

    def has_patient(self, patient_id: str) -> bool:
        return patient_id in self.by_patient

    def nights_matching(
        self, conditions: list[NumericCondition], match: Match, since_days: int, patient_id: str | None = None
    ) -> list[tuple[str, date]]:
        out = []
        for pid in [patient_id] if patient_id else self.patient_ids():
            for d in range(since_days - 1, -1, -1):
                night = self.today - timedelta(days=d)
                zs = {f.name: f.z for f in self.numeric.get(pid, night).tonight}
                if condition_holds(zs, conditions, match):
                    out.append((pid, night))
        return out

    def all_candidates(self) -> list[AlertCandidate]:
        return [c for pid in self.patient_ids() for c in self.by_patient[pid].candidates()]

    def patient(self, patient_id: str) -> Scenario:
        try:
            return self.by_patient[patient_id]
        except KeyError:
            raise LookupError(f"no data for patient {patient_id}") from None

    @property
    def numeric(self) -> ScenarioNumericProvider:
        return ScenarioNumericProvider(self)

    @property
    def descriptive(self) -> ScenarioDescriptiveProvider:
        return ScenarioDescriptiveProvider(self)


def load_bundled_store() -> ScenarioStore:
    return ScenarioStore.from_dir(Path(str(files("llm_worker.scenarios"))))


class ScenarioNumericProvider:
    """Stands in for the `vitals` serving tables (nightly_features + nightly_deviations)."""

    def __init__(self, store: ScenarioStore):
        self.store = store

    def get(self, patient_id: str, night_date: date) -> NumericContext:
        scenario = self.store.patient(patient_id)
        if night_date > self.store.today:
            raise LookupError(f"no data for patient {patient_id} on {night_date}")

        tonight = scenario.values_on(night_date)
        facts = []
        for name, (unit, spread) in SIGNALS.items():
            if name not in scenario.baseline:
                continue
            value, baseline = tonight.get(name), scenario.baseline[name]
            previous = [
                scenario.values_on(night_date - timedelta(days=d)).get(name) for d in range(1, PREVIOUS_NIGHTS + 1)
            ]
            z = None if value is None else round((value - baseline) / spread, 1)
            facts.append(
                Fact(id=f"n:{name}", name=name, unit=unit, value=value, baseline=baseline, z=z, previous=previous)
            )

        window = [
            NightRow(
                night_date=night_date - timedelta(days=d), values=scenario.values_on(night_date - timedelta(days=d))
            )
            for d in range(WINDOW_NIGHTS, 0, -1)
        ]
        coverage = {name: scenario.coverage.get(name, 1.0) for name in scenario.baseline if name in SIGNALS}
        return NumericContext(
            night_date=night_date, tonight=facts, window=window, coverage=coverage, source=f"scenario:{scenario.name}"
        )


class ScenarioDescriptiveProvider:
    """Stands in for the `patient_context` schema (later db_lord / FHIR)."""

    def __init__(self, store: ScenarioStore):
        self.store = store

    def get(self, patient_id: str, night_date: date, as_of: datetime, max_items: int = 20) -> DescriptiveContext:
        scenario = self.store.patient(patient_id)
        items, truncated = visible_items(scenario.context_items(), night_date, as_of, max_items)
        return DescriptiveContext(
            age_band=age_band(night_date.year - scenario.patient.birth_year),
            sex=scenario.patient.sex,
            items=items,
            truncated=truncated,
            source=f"scenario:{scenario.name}",
        )


def age_band(age: int) -> str:
    """Age groups suggested by the clinician (Amin, 2026-11): 18–35, 35–50, 50–70, >70."""
    if age < 18:
        return "<18"
    if age < 35:
        return "18–35"
    if age < 50:
        return "35–50"
    if age < 70:
        return "50–70"
    return ">70"
