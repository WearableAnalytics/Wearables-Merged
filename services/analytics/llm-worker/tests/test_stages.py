"""Pipeline and stages, without a database or a model: operators are replaced by scripted fakes."""

import json
from datetime import date

import pytest

from llm_worker.dto import AlertCandidate
from llm_worker.pipeline import Context, Event, run_pipeline
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.semantic import LLMUnavailable, LotusModel, OperatorSpec
from llm_worker.semantic.operators import OperatorResult
from llm_worker.settings import Settings
from llm_worker.stages import default_stages
from llm_worker.stages.evidence import LoadEvidence
from llm_worker.stages.explain import Explain
from llm_worker.stages.triage import SemanticTriage

STORE = load_bundled_store()
MODEL = LotusModel(base_url="http://unused/v1", model="scripted")


def event_for(name: str, event_id: int = 1) -> Event:
    c = STORE.get(name).candidate(candidate_id=event_id)
    return Event(
        event_id=event_id,
        patient_id=c.patient_id,
        night_date=c.night_date,
        reasons=", ".join(c.trigger_reasons),
        red_flag=c.red_flag,
        features={"l2_score": c.l2_score},
        attempts=1,
    )


def loaded(*names: str) -> list[Context]:
    batch = [Context(event_for(n, i)) for i, n in enumerate(names, start=1)]
    LoadEvidence(STORE.numeric, STORE.descriptive).run(batch, conn=None)
    return batch


class ScriptedOperator:
    """Returns scripted values and records the rows it was given."""

    def __init__(self, kind: str, values, rationales=None, raises: Exception | None = None):
        self.spec = OperatorSpec(name=f"scripted_{kind}", version=3, kind=kind, instruction="{numeric} {context}")
        self.values, self.rationales, self.raises = values, rationales, raises
        self.calls: list = []

    def __call__(self, df, model):
        self.calls.append(df.copy())
        if self.raises:
            raise self.raises
        values = list(self.values[: len(df)])
        rationales = (self.rationales or ["scripted rationale"] * len(df))[: len(df)]
        return OperatorResult(values=values, rationales=rationales, raw=[str(v) for v in values])


# --- pipeline


class Recorder:
    def __init__(self, name, output=None, stop_ids=(), error_ids=()):
        self.name, self.output, self.stop_ids, self.error_ids = name, output or {}, stop_ids, error_ids
        self.seen: list[list[int]] = []

    def run(self, batch, conn):
        self.seen.append([ctx.event.event_id for ctx in batch])
        for ctx in batch:
            ctx.stop = ctx.event.event_id in self.stop_ids
            if ctx.event.event_id in self.error_ids:
                ctx.error = "broken"
        return [dict(self.output) for _ in batch]


def test_pipeline_runs_each_stage_once_per_batch_and_stores_outputs_by_name():
    first, second = Recorder("first", {"a": 1}), Recorder("second", {"b": 2})

    ctxs = run_pipeline([event_for("red_flag", 1), event_for("alcohol_documented", 2)], [first, second], conn=None)

    assert first.seen == [[1, 2]] and second.seen == [[1, 2]]
    assert all(ctx.result == {"first": {"a": 1}, "second": {"b": 2}} for ctx in ctxs)


def test_a_context_that_stopped_or_failed_skips_the_remaining_stages():
    first, second = Recorder("first", stop_ids={1}, error_ids={2}), Recorder("second")

    ctxs = run_pipeline([event_for("red_flag", i) for i in (1, 2, 3)], [first, second], conn=None)

    assert second.seen == [[3]]
    assert [ctx.error for ctx in ctxs] == [None, "broken", None]


def test_event_converts_to_an_alert_candidate():
    candidate = event_for("vaccination_documented", 5).to_candidate()

    assert isinstance(candidate, AlertCandidate)
    assert candidate.candidate_id == 5 and candidate.trigger_reasons[0] == "rhr_z>2"
    assert candidate.l2_score == pytest.approx(0.41)


# --- load_evidence


def test_load_evidence_attaches_bundle_and_rendered_text():
    (ctx,) = loaded("vaccination_documented")

    assert ctx.bundle.candidate.patient_id == "P-001"
    assert "n:rhr" in ctx.rendered.numeric and "flu shot" in ctx.rendered.context


def test_load_evidence_output_summarises_what_was_read():
    ctx = Context(event_for("long_context_truncation"))

    (output,) = LoadEvidence(STORE.numeric, STORE.descriptive).run([ctx], conn=None)

    assert output["context_items"] == 20 and output["truncated_context_items"] == 10
    assert output["render"] == "render.v1"
    assert output["numeric_source"] == "scenario:long_context_truncation"


def test_load_evidence_marks_only_the_candidate_without_data_as_failed():
    good = Context(event_for("red_flag", 1))
    missing = Context(Event(2, "nobody", date(2026, 3, 14), "x", False, {}, 1))

    LoadEvidence(STORE.numeric, STORE.descriptive).run([good, missing], conn=None)

    assert good.error is None and good.bundle is not None
    assert "nobody" in missing.error


# --- triage (L3, sem_filter)


def test_triage_sends_all_non_red_flag_rows_to_the_operator_in_one_call():
    batch = loaded("vaccination_documented", "red_flag", "alcohol_undocumented")
    op = ScriptedOperator("filter", [True, False])

    outputs = SemanticTriage(op, MODEL).run(batch, conn=None)

    assert len(op.calls) == 1 and len(op.calls[0]) == 2  # the red flag never reached the model
    assert [o["verdict"] for o in outputs] == ["suppress", "red_flag_bypass", "notify"]
    assert [ctx.notify for ctx in batch] == [False, True, True]


def test_a_red_flag_is_never_suppressed_even_if_the_model_would():
    batch = loaded("red_flag")
    op = ScriptedOperator("filter", [True])

    (output,) = SemanticTriage(op, MODEL).run(batch, conn=None)

    assert output["verdict"] == "red_flag_bypass" and batch[0].notify is True
    assert op.calls == []


def test_an_unclear_answer_still_notifies():
    batch = loaded("vaccination_documented")

    (output,) = SemanticTriage(ScriptedOperator("filter", [None]), MODEL).run(batch, conn=None)

    assert output["verdict"] == "unparseable_notify" and batch[0].notify is True


def test_triage_records_the_rationale_operator_version_and_model():
    batch = loaded("alcohol_documented")

    (output,) = SemanticTriage(ScriptedOperator("filter", [True], ["wine before bed"]), MODEL).run(batch, conn=None)

    assert output["rationale"] == "wine before bed"
    assert output["operator"] == "scripted_filter@3" and output["model"] == "scripted"
    assert batch[0].decision.verdict == "suppress"


def test_a_model_outage_fails_the_whole_batch_so_it_is_retried():
    batch = loaded("vaccination_documented")

    with pytest.raises(LLMUnavailable):
        SemanticTriage(ScriptedOperator("filter", [], raises=LLMUnavailable("down")), MODEL).run(batch, conn=None)


# --- explain (L4, sem_map)


def answer(text: str, *ids: str) -> str:
    return json.dumps({"explanation": text, "cited_ids": list(ids)})


def triaged(*names_and_verdicts):
    batch = loaded(*[n for n, _ in names_and_verdicts])
    values = [{"suppress": True, "notify": False}[v] for n, v in names_and_verdicts if n != "red_flag"]
    SemanticTriage(ScriptedOperator("filter", values), MODEL).run(batch, conn=None)
    return batch


def test_explain_runs_for_every_candidate_and_passes_the_decision_to_the_model():
    batch = triaged(("vaccination_documented", "suppress"), ("red_flag", None), ("alcohol_undocumented", "notify"))
    op = ScriptedOperator("map", [answer("ok", "n:rhr")] * 3)

    Explain(op, MODEL).run(batch, conn=None)

    (df,) = op.calls
    assert len(df) == 3 and set(df.columns) >= {"numeric", "context", "decision"}
    assert "hold back" in df["decision"][0] and "red flag" in df["decision"][1].lower()
    assert "no documented benign cause" in df["decision"][2]


def test_explain_keeps_valid_citations_and_drops_invented_ones():
    batch = triaged(("vaccination_documented", "suppress"))
    op = ScriptedOperator("map", [answer("Flu shot the day before (c:104); HR up (n:rhr).", "n:rhr", "c:104", "c:999")])

    (output,) = Explain(op, MODEL).run(batch, conn=None)

    assert output["cited_ids"] == ["n:rhr", "c:104"]
    assert output["invalid_cited_ids"] == ["c:999"]
    assert batch[0].explanation.startswith("Flu shot the day before")


def test_an_unusable_model_answer_falls_back_to_a_template_that_still_explains():
    batch = triaged(("alcohol_undocumented", "notify"))

    (output,) = Explain(ScriptedOperator("map", ["Sorry, I cannot help with that."]), MODEL).run(batch, conn=None)

    assert output["fallback"] is True
    assert "n:rhr" in batch[0].explanation and "notify" in batch[0].explanation.lower()


def test_explanation_tolerates_json_inside_extra_text():
    batch = triaged(("vaccination_documented", "suppress"))
    wrapped = "Here is the note:\n```json\n" + answer("Vaccination explains it.", "c:104") + "\n```"

    (output,) = Explain(ScriptedOperator("map", [wrapped]), MODEL).run(batch, conn=None)

    assert output["fallback"] is False and output["cited_ids"] == ["c:104"]


# --- wiring


def test_default_stages_are_evidence_then_triage_then_explain():
    stages = default_stages(Settings(llm_model="qwen2.5:7b"))

    assert [stage.name for stage in stages] == ["load_evidence", "triage", "explain"]
    assert stages[1].operator.spec.ref == "triage@1" and stages[2].operator.spec.ref == "explain@1"
    assert stages[1].model.model == "qwen2.5:7b"


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKER_ID", "worker-a")
    monkeypatch.setenv("WORKER_BATCH_SIZE", "4")
    monkeypatch.setenv("WORKER_LLM_BASE_URL", "http://ollama:11434/v1")
    monkeypatch.setenv("WORKER_LLM_MODEL", "gemma4:26b-a4b")

    settings = Settings()

    assert (settings.id, settings.batch_size) == ("worker-a", 4)
    assert (settings.llm_base_url, settings.llm_model) == ("http://ollama:11434/v1", "gemma4:26b-a4b")


def test_batch_size_defaults_to_eight():
    assert Settings().batch_size == 8
