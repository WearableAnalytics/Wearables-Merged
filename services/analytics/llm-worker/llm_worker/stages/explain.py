import json
import re

import pandas as pd
from psycopg import Connection

from ..dto import Explanation, Fact
from ..pipeline import Context
from ..semantic import LotusModel, SemanticOperator

DECISION_TEXT = {
    "notify": "notify the physician: no documented benign cause explains the values",
    "suppress": "hold back the notification: a documented benign cause explains the values ({rationale})",
    "red_flag_bypass": "RED FLAG: a safety threshold was crossed, always notify the physician",
    "unparseable_notify": "notify the physician: the triage answer was unclear",
}

_JSON = re.compile(r"\{.*\}", re.DOTALL)


class Explain:
    """L4 with LOTUS sem_map: a short note for the physician that cites evidence ids.

    Citations are checked against the evidence that was actually shown; unknown ids are dropped and recorded.
    If the model answer cannot be used, a template explanation is written instead (`fallback = true`).
    """

    name = "explain"

    def __init__(self, operator: SemanticOperator, model: LotusModel):
        self.operator, self.model = operator, model

    def run(self, batch: list[Context], conn: Connection | None) -> list[dict]:
        df = pd.DataFrame(
            {
                "numeric": [c.rendered.numeric for c in batch],
                "context": [c.rendered.context for c in batch],
                "decision": [_decision_text(c) for c in batch],
            }
        )
        result = self.operator(df, self.model)

        outputs = []
        for ctx, value in zip(batch, result.values, strict=True):
            ctx.explained = self._explanation(ctx, value)
            ctx.explanation = ctx.explained.text
            outputs.append(ctx.explained.model_dump(mode="json"))
        return outputs

    def _explanation(self, ctx: Context, answer: str | None) -> Explanation:
        parsed = _parse(answer)
        common = dict(candidate_id=ctx.event.event_id, operator=self.operator.spec.ref, model=self.model.model)
        if parsed is None:
            return Explanation(text=_template(ctx), cited_ids=_deviating_ids(ctx), fallback=True, **common)
        text, cited = parsed
        known = ctx.rendered.ids
        return Explanation(
            text=text,
            cited_ids=[i for i in cited if i in known],
            invalid_cited_ids=[i for i in cited if i not in known],
            **common,
        )


def _decision_text(ctx: Context) -> str:
    decision = ctx.decision
    return DECISION_TEXT[decision.verdict].format(rationale=(decision.rationale or "see context").strip())


def _parse(answer: str | None) -> tuple[str, list[str]] | None:
    if not answer or not (match := _JSON.search(answer)):
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    text, cited = data.get("explanation"), data.get("cited_ids", [])
    if not isinstance(text, str) or not text.strip() or not isinstance(cited, list):
        return None
    return text.strip(), [str(i) for i in cited]


def _deviating(ctx: Context) -> list[Fact]:
    return [f for f in ctx.bundle.numeric.tonight if f.z is not None and abs(f.z) >= 2]


def _deviating_ids(ctx: Context) -> list[str]:
    return [f.id for f in _deviating(ctx)]


def _template(ctx: Context) -> str:
    facts = ", ".join(f"{f.id} {f.value:g} {f.unit} (z={f.z:+.1f})" for f in _deviating(ctx)) or "no large deviation"
    return f"[template] Decision: {_decision_text(ctx)}. Deviating tonight: {facts}."
