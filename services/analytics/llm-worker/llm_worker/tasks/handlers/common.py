"""Shared by the templates: the recent nights of one patient, the evidence returned with an answer, citations.

Evidence is built from the data source's DTOs, never from model output: the numbers a physician sees next to an
answer are the numbers in the serving tables.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...dto import DescriptiveContext, NumericCondition, NumericContext
from ...providers import DataSource, as_of_for
from ...render import RenderedNight, render_night

MAX_DAYS = 14
MAX_FILTERS = 3
_CITED = re.compile(r"\b(?:n\d*:[a-z_0-9]+|c:\d+)\b")
_PATIENT_ID = re.compile(r"\bP-\d{3}\b", re.IGNORECASE)


class WindowParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since_days: int = Field(default=7, ge=1, le=MAX_DAYS)


class FilterParams(WindowParams):
    filters: list[NumericCondition] = Field(default_factory=list, max_length=MAX_FILTERS)
    match: Literal["any", "all"] = "any"


@dataclass(frozen=True)
class Night:
    numeric: NumericContext
    rendered: RenderedNight


def recent_nights(source: DataSource, patient_id: str, days: int, end: date | None = None) -> list[Night]:
    """The last `days` nights up to `end` (default: the latest night in the data), oldest first."""
    end = end or source.today
    nights = []
    for d in range(days - 1, -1, -1):
        numeric = source.numeric.get(patient_id, end - timedelta(days=d))
        nights.append(Night(numeric, render_night(numeric, days_ago=d)))
    return nights


def context_now(source: DataSource, patient_id: str) -> DescriptiveContext:
    """Documented context as of the morning after the latest night; nothing written later is read."""
    return source.descriptive.get(patient_id, source.today, as_of_for(source.today))


def night_evidence(numeric: NumericContext, days_ago: int, ids: str = "night") -> dict:
    """One night as data. `ids="night"` labels like the multi-night prompts (n2:rhr); "tonight" like triage (n:rhr)."""
    prefix = "n:" if ids == "tonight" and days_ago == 0 else f"n{days_ago}:"
    return {
        "night": numeric.night_date.isoformat(),
        "label": f"D-{days_ago}",
        "signals": [
            {
                "id": prefix + f.name,
                "signal": f.name,
                "unit": f.unit,
                "value": f.value,
                "baseline": f.baseline,
                "z": f.z,
                "coverage": numeric.coverage.get(f.name, 1.0),
            }
            for f in numeric.tonight
        ],
    }


def context_evidence(context: DescriptiveContext) -> list[dict]:
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "ts": item.ts.isoformat() if item.ts else None,
            "label": None if item.days_before is None else f"D-{item.days_before}",
            "text": item.text,
        }
        for item in context.items
    ]


def evidence(nights: list[Night], context: DescriptiveContext, ids: str = "night") -> dict:
    return {
        "nights": [night_evidence(n.numeric, n.rendered.days_ago, ids) for n in nights],
        "context": context_evidence(context),
    }


def citations(text: str | None, known: set[str] | frozenset[str]) -> tuple[list[str], list[str]]:
    """(valid, invalid) evidence ids cited in a model answer, in order of appearance."""
    cited = list(dict.fromkeys(_CITED.findall(text or "")))
    return [i for i in cited if i in known], [i for i in cited if i not in known]


def redact_ids(text: str, subject: str | None = None) -> str:
    """Patient ids typed into a question never reach the model: the subject becomes 'this patient'."""

    def name(match: re.Match) -> str:
        return "this patient" if subject and match.group(0).upper() == subject.upper() else "another patient"

    return _PATIENT_ID.sub(name, text)
