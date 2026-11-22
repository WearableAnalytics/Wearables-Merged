import pandas as pd
from psycopg import Connection

from ..dto import TriageDecision
from ..pipeline import Context
from ..semantic import LotusModel, SemanticOperator


class SemanticTriage:
    """L3 with LOTUS sem_filter: does a documented benign cause explain the night?

    Safety rules, in code: red flags never reach the model and are always notified; an unclear answer notifies.
    One operator call per batch; a model outage raises and the whole batch is retried.
    """

    name = "triage"

    def __init__(self, operator: SemanticOperator, model: LotusModel):
        self.operator, self.model = operator, model

    def run(self, batch: list[Context], conn: Connection | None) -> list[dict]:
        to_judge = [ctx for ctx in batch if not ctx.event.red_flag]
        if to_judge:
            df = pd.DataFrame(
                {"numeric": [c.rendered.numeric for c in to_judge], "context": [c.rendered.context for c in to_judge]}
            )
            result = self.operator(df, self.model)
            for ctx, value, rationale in zip(to_judge, result.values, result.rationales, strict=True):
                verdict = {True: "suppress", False: "notify", None: "unparseable_notify"}[value]
                ctx.decision = self._decision(ctx, verdict, rationale)

        for ctx in batch:
            if ctx.event.red_flag:
                ctx.decision = self._decision(
                    ctx, "red_flag_bypass", "Red flag: always shown to a clinician.", model=None
                )
            ctx.notify = ctx.decision.verdict != "suppress"
        return [ctx.decision.model_dump(mode="json") for ctx in batch]

    def _decision(self, ctx: Context, verdict: str, rationale: str | None, model: str | None = "") -> TriageDecision:
        return TriageDecision(
            candidate_id=ctx.event.event_id,
            verdict=verdict,
            rationale=rationale,
            operator=self.operator.spec.ref,
            model=self.model.model if model == "" else model,
        )
