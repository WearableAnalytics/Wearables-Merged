"""Data transfer objects between the data sources, the semantic operators and the write-back (plan §6.2).

The rest of the worker only sees these types, never the storage behind them (PostgreSQL, Delta, ClickHouse, fixtures).
Every number and every text item carries an `id`, so the model can cite evidence and we can check the citations.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["notify", "suppress", "red_flag_bypass", "unparseable_notify"]
ContextKind = Literal["condition", "medication", "encounter", "note"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class AlertCandidate(_Frozen):
    """One flagged patient-night (`alerting.alert_candidates`). Flagged by rules / ML, not yet judged."""

    candidate_id: int
    patient_id: str
    night_date: date
    trigger_reasons: list[str] = Field(default_factory=list)
    red_flag: bool = False
    l2_score: float | None = None
    sync_batch_id: str | None = None


class Fact(_Frozen):
    """One signal tonight, compared with the patient's own baseline. z keeps its sign."""

    id: str
    name: str
    unit: str
    value: float | None
    baseline: float | None
    z: float | None
    previous: list[float | None] = Field(default_factory=list)  # D-1, D-2, D-3


class NightRow(_Frozen):
    night_date: date
    values: dict[str, float | None]


class NumericContext(_Frozen):
    night_date: date
    tonight: list[Fact]
    window: list[NightRow]  # the 14 nights before, oldest first
    coverage: dict[str, float] = Field(default_factory=dict)
    source: str = "unknown"

    def fact(self, name: str) -> Fact:
        for fact in self.tonight:
            if fact.name == name:
                return fact
        raise KeyError(name)


class ContextItem(_Frozen):
    id: str
    kind: ContextKind
    ts: datetime | None
    days_before: int | None  # relative to the night: 0 = the same day, 1 = the day before
    text: str


class DescriptiveContext(_Frozen):
    age_band: str
    sex: str
    items: list[ContextItem]
    truncated: int = 0
    source: str = "unknown"


class EvidenceBundle(_Frozen):
    candidate: AlertCandidate
    numeric: NumericContext
    descriptive: DescriptiveContext
    provenance: dict

    def evidence_ids(self) -> set[str]:
        return {f.id for f in self.numeric.tonight} | {item.id for item in self.descriptive.items}


class TriageDecision(_Frozen):
    """L3: does a documented benign cause explain the night? Only `suppress` holds a notification back."""

    candidate_id: int
    verdict: Verdict
    rationale: str | None = None
    operator: str  # spec name@version
    model: str | None = None


class Explanation(_Frozen):
    """L4: why the clinician is (or is not) notified, citing evidence ids."""

    candidate_id: int
    text: str
    cited_ids: list[str] = Field(default_factory=list)
    invalid_cited_ids: list[str] = Field(default_factory=list)
    fallback: bool = False  # True when the model answer could not be used and a template was written instead
    operator: str
    model: str | None = None
