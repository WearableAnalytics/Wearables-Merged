"""Evidence bundle -> the two text columns the semantic operators read: `numeric` and `context` (plan §7.2).

Rules: every line starts with its evidence id; dates are relative to the night (D-1 = the day before);
z keeps its sign; missing data is written as `missing`, never left out; no patient identifiers.
Changing the output format changes RENDER_VERSION, which is stored with every result.
"""

from dataclasses import dataclass
from datetime import date

from .dto import ContextItem, DescriptiveContext, EvidenceBundle, Fact, NumericContext

RENDER_VERSION = "render.v1"
DEVIATION_Z = 1.0  # a night "differs" from the baseline when any signal is at least this many spreads away

_SEX = {"F": "female", "M": "male"}


@dataclass(frozen=True)
class RenderedRow:
    numeric: str
    context: str
    ids: frozenset[str]


def render(bundle: EvidenceBundle) -> RenderedRow:
    return RenderedRow(
        numeric=_numeric(bundle),
        context=_context(bundle),
        ids=frozenset(bundle.evidence_ids()),
    )


def _numeric(bundle: EvidenceBundle) -> str:
    c, d, n = bundle.candidate, bundle.descriptive, bundle.numeric
    lines = [f"Tonight · age {d.age_band} · {_SEX.get(d.sex, d.sex)}"]
    trigger = f"flagged by: {', '.join(c.trigger_reasons) or 'unknown'}"
    if c.l2_score is not None:
        trigger += f" (model score {c.l2_score:.2f})"
    lines.append(trigger)
    if c.red_flag:
        lines.append("RED FLAG: a safety threshold was crossed; this night is always shown to a clinician.")
    width = max((len(f.id) for f in n.tonight), default=0)
    lines += [_fact(f, width, n.coverage.get(f.name, 1.0)) for f in n.tonight]
    return "\n".join(lines)


def _fact(f: Fact, width: int, coverage: float) -> str:
    parts = [f.id.ljust(width)]
    parts.append("missing" if f.value is None else f"{_num(f.value)} {f.unit}")
    if f.baseline is not None:
        parts.append(f"baseline {_num(f.baseline)}")
    if f.z is not None:
        parts.append(f"z={f.z:+.1f}")
    if f.previous:
        parts.append("previous " + ", ".join(f"D-{i} {_num(v)}" for i, v in enumerate(f.previous, start=1)))
    if coverage < 1.0:
        parts.append(f"coverage {coverage:.0%}")
    return "  ".join(parts)


def _context(bundle: EvidenceBundle) -> str:
    return render_context(bundle.descriptive)


def render_context(d: DescriptiveContext) -> str:
    if not d.items:
        return "No documented context."
    lines = [_item(item) for item in d.items]
    if d.truncated:
        lines.append(f"({d.truncated} older entries not shown)")
    return "\n".join(lines)


def _item(item: ContextItem) -> str:
    when = "" if item.days_before is None else f"{_day(item.days_before)}, "
    return f"{item.id} ({when}{item.kind}) {item.text}"


def _day(days_before: int) -> str:
    return "D-0" if days_before == 0 else f"D{-days_before:+d}"


def _num(value: float | None) -> str:
    return "missing" if value is None else f"{value:g}"


# --- several nights of one patient (patient_explain, cohort_query). Ids carry the night: n2:rhr = rhr on D-2.


@dataclass(frozen=True)
class RenderedNight:
    night_date: date
    days_ago: int
    text: str
    ids: frozenset[str]
    deviating_ids: frozenset[str]
    deviating_text: str  # header + only the lines that differ

    @property
    def deviating(self) -> bool:
        return bool(self.deviating_ids)


@dataclass(frozen=True)
class RenderedSummary:
    text: str
    ids: frozenset[str]


def render_night(numeric: NumericContext, days_ago: int) -> RenderedNight:
    """One night, every signal against the personal baseline. Previous nights are separate rows, so not repeated."""
    facts = [f.model_copy(update={"id": f"n{days_ago}:{f.name}", "previous": []}) for f in numeric.tonight]
    width = max((len(f.id) for f in facts), default=0)
    header = f"D-{days_ago} ({numeric.night_date.isoformat()})"
    lines = {f.id: _fact(f, width, numeric.coverage.get(f.name, 1.0)) for f in facts}
    off = [f for f in facts if f.z is not None and abs(f.z) >= DEVIATION_Z]
    return RenderedNight(
        night_date=numeric.night_date,
        days_ago=days_ago,
        text="\n".join([header, *lines.values()]),
        ids=frozenset(lines),
        deviating_ids=frozenset(f.id for f in off),
        deviating_text="\n".join([header, *(lines[f.id] for f in off)]),
    )


def render_patient_summary(descriptive: DescriptiveContext, nights: list[RenderedNight]) -> RenderedSummary:
    """One patient's recent record as one row: who (age band, sex), the nights that differ, the documented context.

    No patient identifier: the row is matched back to the patient by position after the model call.
    """
    deviating = sorted((n for n in nights if n.deviating), key=lambda n: n.night_date)
    lines = [f"Patient · age {descriptive.age_band} · {_SEX.get(descriptive.sex, descriptive.sex)}"]
    lines.append(f"Nights that differ from the personal baseline (of the last {len(nights)}):")
    lines += [n.deviating_text for n in deviating] or ["none"]
    lines += ["Documented context:", render_context(descriptive)]
    ids = {i for n in deviating for i in n.deviating_ids} | {item.id for item in descriptive.items}
    return RenderedSummary(text="\n".join(lines), ids=frozenset(ids))
