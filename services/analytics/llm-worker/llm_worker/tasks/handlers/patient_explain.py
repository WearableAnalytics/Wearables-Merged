"""patient_explain: a physician asks about one patient. Read-only.

Cheap filter first (only nights that differ from the baseline), then LOTUS:
sem_map writes one line per such night, sem_agg turns the lines plus the documented context into the answer.
The nights of the whole window come back as evidence, straight from the data source.
"""

import pandas as pd

from ...render import DEVIATION_Z, RENDER_VERSION, render_context
from ...semantic import build_operator, load_spec
from ..model import TaskOutcome, TaskRun
from ..registry import Deps, ParamsError, parse_params, register_task
from .common import WindowParams, citations, context_now, evidence, recent_nights, redact_ids


class PatientParams(WindowParams):
    patient_id: str


@register_task
class PatientExplain:
    template = "patient_explain"
    triggers = frozenset({"pipeline", "chat"})
    priority = 10
    batch_size = 1

    def __init__(self, deps: Deps):
        self.source, self.model = deps.source, deps.model
        self.night_spec, self.trajectory_spec = load_spec("night_summary"), load_spec("trajectory")
        build_operator(self.night_spec, {"night"})
        build_operator(self.trajectory_spec.fill(context="", question=""), {"night_line"})

    def validate(self, params: dict) -> dict:
        p = parse_params(PatientParams, params)
        if not self.source.has_patient(p.patient_id):
            raise ParamsError(f"unknown patient {p.patient_id}")
        return p.model_dump()

    def run(self, runs: list[TaskRun]) -> list[TaskOutcome]:
        return [self._run(r) for r in runs]

    def _run(self, run: TaskRun) -> TaskOutcome:
        p = PatientParams.model_validate(run.params)
        nights = recent_nights(self.source, p.patient_id, p.since_days)
        context = context_now(self.source, p.patient_id)
        deviating = [n for n in nights if n.rendered.deviating]
        evidence_ids = {i for n in deviating for i in n.rendered.ids} | {item.id for item in context.items}
        result = {
            "patient_id": p.patient_id,
            "since_days": p.since_days,
            "nights_considered": [n.numeric.night_date.isoformat() for n in nights],
            "evidence": evidence(nights, context),
            "evidence_ids": sorted(evidence_ids),
            "night_lines": [],
            "cited_ids": [],
            "invalid_cited_ids": [],
        }
        if not deviating:
            answer = (
                f"No night in the last {p.since_days} differs from this patient's own baseline "
                f"by {DEVIATION_Z:g} spread or more; the signals are stable."
            )
            return TaskOutcome(answer=answer, result=result, spec_versions={"render": RENDER_VERSION})

        night_op = build_operator(self.night_spec, {"night"})
        lines = night_op(pd.DataFrame({"night": [n.rendered.text for n in deviating]}), self.model).values
        pairs = [(n.rendered, line) for n, line in zip(deviating, lines, strict=True)]
        night_lines = [f"D-{n.days_ago} ({n.night_date.isoformat()}): {line or 'no summary'}" for n, line in pairs]
        result["night_lines"] = [{"night": n.night_date.isoformat(), "line": line} for n, line in pairs]

        spec = self.trajectory_spec.fill(
            context=" ".join(render_context(context).splitlines()), question=redact_ids(run.prompt, p.patient_id)
        )
        [answer] = build_operator(spec, {"night_line"})(pd.DataFrame({"night_line": night_lines}), self.model).values
        if not answer:
            answer = "[no model summary] " + " ".join(night_lines)
        result["cited_ids"], result["invalid_cited_ids"] = citations(answer, evidence_ids)
        return TaskOutcome(
            answer=answer,
            result=result,
            model=self.model.model,
            spec_versions={
                "night": self.night_spec.ref,
                "trajectory": self.trajectory_spec.ref,
                "render": RENDER_VERSION,
            },
        )
