"""cohort_query: a physician or data scientist asks across all patients. Read-only.

1. Optional exact numeric predicate (`filters`, e.g. wrist_temp_delta z >= 2): runs in the data source (SQL), and only
   the patients with a matching night go on. No model involved.
2. One anonymous row per remaining patient (age band, sex, the nights that differ, documented context); LOTUS
   sem_filter applies the natural-language criterion to every row, sem_map says why each match matched.
3. Each match comes back with its nights and context as data. Patient ids never reach the model.
"""

import pandas as pd

from ...render import RENDER_VERSION, render_patient_summary
from ...semantic import build_operator, load_spec
from ..model import TaskOutcome, TaskRun
from ..registry import Deps, parse_params, register_task
from .common import FilterParams, citations, context_now, evidence, recent_nights, redact_ids


@register_task
class CohortQuery:
    template = "cohort_query"
    triggers = frozenset({"chat"})
    priority = 10
    batch_size = 1

    def __init__(self, deps: Deps):
        self.source, self.model = deps.source, deps.model
        self.match_spec, self.reason_spec = load_spec("cohort_match"), load_spec("cohort_reason")
        for spec in (self.match_spec, self.reason_spec):
            build_operator(spec.fill(criterion=""), {"summary"})

    def validate(self, params: dict) -> dict:
        return parse_params(FilterParams, params).model_dump()

    def run(self, runs: list[TaskRun]) -> list[TaskOutcome]:
        return [self._run(r) for r in runs]

    def _run(self, run: TaskRun) -> TaskOutcome:
        p = FilterParams.model_validate(run.params)
        filters = [str(c) for c in p.filters]
        result = {"since_days": p.since_days, "filters": filters, "match": p.match, "prefiltered": None}

        selected_nights: dict[str, set] = {}
        if p.filters:
            for pid, night in self.source.nights_matching(p.filters, p.match, p.since_days):
                selected_nights.setdefault(pid, set()).add(night)
            patient_ids = sorted(selected_nights)
            result["prefiltered"] = patient_ids
        else:
            patient_ids = self.source.patient_ids()
        result |= {"checked": len(patient_ids), "matches": [], "unclear": []}
        spec_versions = {"match": self.match_spec.ref, "reason": self.reason_spec.ref, "render": RENDER_VERSION}

        if not patient_ids:
            joiner = " and " if p.match == "all" else " or "
            answer = f"No patient meets the numeric filter ({joiner.join(filters)})."
            return TaskOutcome(answer=answer, result=result, spec_versions=spec_versions)

        rows = []
        for pid in patient_ids:
            nights, context = recent_nights(self.source, pid, p.since_days), context_now(self.source, pid)
            rows.append((pid, nights, context, render_patient_summary(context, [n.rendered for n in nights])))

        criterion = redact_ids(run.prompt)
        match = build_operator(self.match_spec.fill(criterion=criterion), {"summary"})
        verdicts = match(pd.DataFrame({"summary": [r[3].text for r in rows]}), self.model).values
        hits = [r for r, v in zip(rows, verdicts, strict=True) if v is True]
        result["unclear"] = [r[0] for r, v in zip(rows, verdicts, strict=True) if v is None]

        reasons: list[str | None] = []
        if hits:
            reason = build_operator(self.reason_spec.fill(criterion=criterion), {"summary"})
            reasons = reason(pd.DataFrame({"summary": [r[3].text for r in hits]}), self.model).values

        for (pid, nights, context, summary), text in zip(hits, reasons, strict=True):
            valid, invalid = citations(text, summary.ids)
            if p.filters:
                shown = [n for n in nights if n.numeric.night_date in selected_nights[pid]]
            else:
                shown = [n for n in nights if n.rendered.deviating]
            result["matches"].append(
                {
                    "patient_id": pid,
                    "reason": text,
                    "cited_ids": valid,
                    "invalid_cited_ids": invalid,
                    "evidence": evidence(shown, context),
                }
            )

        matches = result["matches"]
        if matches:
            n = len(patient_ids)
            head = f"of the {n} patients that meet the numeric filter" if p.filters else f"of {n} patients"
            lines = [f"{len(matches)} {head} match."]
            lines += [f"- {m['patient_id']}: {m['reason']}" for m in matches]
            answer = "\n".join(lines)
        else:
            answer = "No patient matches."
        return TaskOutcome(answer=answer, result=result, model=self.model.model, spec_versions=spec_versions)
