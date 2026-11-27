"""Chat text -> task request, by rules. No model: the routing is predictable, testable and shown to the user.

The text decides which template and which patient; everything else in it is the question (the semantic part).
"""

import re
from collections.abc import Collection
from dataclasses import dataclass

from .handlers.common import MAX_DAYS
from .model import TaskRequest

_PATIENT = re.compile(r"\bP-\d{3}\b", re.IGNORECASE)
_DAYS = re.compile(r"\b(\d{1,3})\s*(?:days?|nights?)\b", re.IGNORECASE)
_WEEKS = re.compile(r"\b(\d|one|two|three|four)\s*weeks?\b", re.IGNORECASE)
_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4}
_ACTION = re.compile(r"\b(notify|notification|alert|page|send|inform|escalate)\b", re.IGNORECASE)

READ_ONLY_NOTICE = "Chat tasks are read-only: they never notify clinicians or change any alert."
DEFAULT_DAYS = 7


class RouteError(ValueError):
    pass


@dataclass(frozen=True)
class Routed:
    request: TaskRequest
    notice: str | None = None


def route(
    text: str,
    submitted_by: str,
    known_patients: Collection[str],
    patient_id: str | None = None,
    template: str | None = None,
    filters: list[dict] | None = None,
    match: str = "any",
) -> Routed:
    text = text.strip()
    if not text:
        raise RouteError("empty question")

    patient = patient_id or _patient_in(text)
    if patient is not None:
        patient = patient.upper()
        if patient not in known_patients:
            raise RouteError(f"unknown patient {patient}")

    if filters and patient is not None:
        raise RouteError("numeric filters are for questions across patients; remove the filter or the patient")
    if template is None:
        template = "patient_explain" if patient else "cohort_query"
    if template == "patient_explain" and patient is None:
        raise RouteError("patient_explain needs a patient: select one or write its id, e.g. P-010")

    params: dict = {"since_days": _days(text)}
    if patient is not None and template != "cohort_query":
        params["patient_id"] = patient
    if filters:  # checked by the template (signal names, operators, ranges)
        params |= {"filters": filters, "match": match}

    request = TaskRequest(template=template, params=params, prompt=text, trigger="chat", submitted_by=submitted_by)
    return Routed(request, READ_ONLY_NOTICE if _ACTION.search(text) else None)


def _patient_in(text: str) -> str | None:
    match = _PATIENT.search(text)
    return match.group(0) if match else None


def _days(text: str) -> int:
    if match := _DAYS.search(text):
        return max(1, min(int(match.group(1)), MAX_DAYS))
    if match := _WEEKS.search(text):
        n = match.group(1).lower()
        return min(_NUMBERS.get(n) or int(n), 2) * 7
    return DEFAULT_DAYS
