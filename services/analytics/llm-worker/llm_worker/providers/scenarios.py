"""Mock data sources: one YAML file per scenario stands in for the gold serving tables and patient_context.

A scenario describes one patient around one flagged night: the personal baseline, the nights that differ from it,
the descriptive context (medications, diary notes, ...) and the candidate the upstream pipeline would raise.
No physiology is simulated; the numbers are written by hand so that each scenario tests one behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ..dto import AlertCandidate, ContextItem, ContextKind, DescriptiveContext, Fact, NightRow, NumericContext

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


class _Expect(BaseModel):
    verdict: str


class Scenario(BaseModel):
    name: str
    summary: str
    patient: _Patient
    baseline: dict[str, float]
    nights: dict[date, dict[str, float | None]] = Field(default_factory=dict)
    coverage: dict[str, float] = Field(default_factory=dict)
    context: list[_ContextEntry] = Field(default_factory=list)
    candidate_: _Candidate = Field(alias="candidate")
    expect: _Expect

    @property
    def patient_id(self) -> str:
        return self.patient.id

    @property
    def night_date(self) -> date:
        return self.candidate_.night

    @property
    def expect_verdict(self) -> str:
        return self.expect.verdict

    def candidate(self, candidate_id: int) -> AlertCandidate:
        c = self.candidate_
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

    def __post_init__(self) -> None:
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
        if night_date != scenario.night_date:
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
        visible = [item for item in scenario.context_items() if item.ts is None or item.ts < as_of]
        visible.sort(key=lambda item: (item.ts is not None, item.ts or datetime.min))

        undated = [item for item in visible if item.ts is None]
        dated = [item for item in visible if item.ts is not None]
        keep = max(max_items - len(undated), 0)
        kept = undated + dated[len(dated) - keep :] if keep else undated
        items = [
            item.model_copy(update={"days_before": None if item.ts is None else (night_date - item.ts.date()).days})
            for item in kept
        ]
        return DescriptiveContext(
            age_band=age_band(night_date.year - scenario.patient.birth_year),
            sex=scenario.patient.sex,
            items=items,
            truncated=len(visible) - len(items),
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
