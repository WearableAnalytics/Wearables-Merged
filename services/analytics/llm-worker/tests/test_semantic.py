"""Semantic operators: natural-language specs run by LOTUS against an OpenAI-compatible model.

The model here is a fake HTTP server (llm_worker.fake_llm), so the real LOTUS -> LiteLLM -> HTTP path is exercised
without a model. Real-model checks are in test_ollama.py (marker `ollama`).
"""

import pandas as pd
import pytest

from llm_worker.evidence import gather
from llm_worker.fake_llm import FakeLLM
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.render import render
from llm_worker.semantic import (
    LLMUnavailable,
    LotusModel,
    OperatorSpec,
    SpecError,
    build_operator,
    load_spec,
    register_operator,
)
from llm_worker.semantic.operators import OPERATORS, OperatorResult


@pytest.fixture(scope="module")
def store():
    return load_bundled_store()


@pytest.fixture
def fake():
    server = FakeLLM()
    yield server
    server.close()


@pytest.fixture
def model(fake):
    return LotusModel(base_url=fake.base_url, model="fake-small")


def frame(store, *names) -> pd.DataFrame:
    rows = [
        render(gather(store.get(n).candidate(candidate_id=i), store.numeric, store.descriptive))
        for i, n in enumerate(names)
    ]
    return pd.DataFrame({"numeric": [r.numeric for r in rows], "context": [r.context for r in rows]})


# --- specs: the behaviour is written in natural language, not in code


def test_bundled_specs_are_natural_language_with_a_versioned_reference():
    triage, explain = load_spec("triage"), load_spec("explain")

    assert (triage.kind, triage.ref) == ("filter", "triage@1")
    assert (explain.kind, explain.ref) == ("map", "explain@1")
    assert triage.columns() == {"numeric", "context"}
    assert "vaccination" in triage.instruction  # benign causes are listed in the spec, not in Python


def test_a_spec_that_references_an_unknown_column_is_rejected():
    spec = OperatorSpec.adhoc("filter", "the {diary} mentions travel")

    with pytest.raises(SpecError, match="diary"):
        build_operator(spec, columns={"numeric", "context"})


def test_an_unknown_operator_kind_is_rejected():
    with pytest.raises(SpecError, match="topk"):
        build_operator(OperatorSpec.adhoc("topk", "the most severe {numeric}"), columns={"numeric"})


def test_new_operator_kinds_plug_in_without_changing_existing_code(store, model):
    @register_operator("count_rows")
    class CountRows:
        def __init__(self, spec):
            self.spec = spec

        def __call__(self, df, model):
            return OperatorResult(values=[len(df)] * len(df), rationales=[None] * len(df), raw=[None] * len(df))

    try:
        op = build_operator(OperatorSpec.adhoc("count_rows", "count {numeric}"), columns={"numeric"})
        assert op(frame(store, "red_flag", "alcohol_documented"), model).values == [2, 2]
    finally:
        OPERATORS.pop("count_rows")


# --- LOTUS through the fake model


def test_sem_filter_returns_one_verdict_and_rationale_per_row(store, model, fake):
    op = build_operator(load_spec("triage"), columns={"numeric", "context"})

    result = op(frame(store, "vaccination_documented", "alcohol_undocumented"), model)

    assert result.values == [True, False]
    assert all(r for r in result.rationales)
    assert len(fake.requests) == 2  # one model call per row, sent as one LOTUS batch
    assert all(req["model"] == "fake-small" for req in fake.requests)
    assert all(req["temperature"] == 0 for req in fake.requests)


def test_an_unparseable_filter_answer_becomes_none_not_true(store, model, fake):
    fake.mode = "garbage"
    op = build_operator(load_spec("triage"), columns={"numeric", "context"})

    result = op(frame(store, "vaccination_documented"), model)

    assert result.values == [None]


def test_an_unreachable_model_raises_llm_unavailable(store, model, fake):
    fake.mode = "error"
    op = build_operator(load_spec("triage"), columns={"numeric", "context"})

    with pytest.raises(LLMUnavailable):
        op(frame(store, "vaccination_documented"), model)


def test_sem_map_returns_the_model_text_per_row(store, model):
    op = build_operator(load_spec("explain"), columns={"numeric", "context", "decision"})
    df = frame(store, "vaccination_documented").assign(decision="suppress")

    result = op(df, model)

    assert len(result.values) == 1 and "explanation" in result.values[0]


def test_an_ad_hoc_natural_language_question_runs_on_the_same_engine(store, fake):
    """What a data scientist or doctor would do later: ask a new question in plain language, no new code."""
    fake.answer = lambda messages: "True" if "zermatt" in messages[-1]["content"].lower() else "False"
    question = OperatorSpec.adhoc("filter", "In {context}, the patient travelled to the mountains or to high altitude")
    op = build_operator(question, columns={"numeric", "context"})
    names = ["altitude_documented", "vaccination_documented", "red_flag"]

    result = op(frame(store, *names), LotusModel(base_url=fake.base_url, model="fake-small"))

    assert [n for n, hit in zip(names, result.values, strict=True) if hit] == ["altitude_documented"]


# --- sem_agg and template slots (used by the chat tasks)


def test_sem_agg_combines_all_rows_into_one_answer(model, fake):
    op = build_operator(OperatorSpec.adhoc("agg", "Summarise how the {line} values change"), columns={"line"})

    result = op(pd.DataFrame({"line": ["D-2: [n2:rhr] up", "D-1: [n1:rhr] up more"]}), model)

    assert len(result.values) == 1 and result.values[0].startswith("[fake model]")
    prompt = fake.requests[-1]["messages"][-1]["content"]
    assert "D-2: [n2:rhr] up" in prompt and "D-1: [n1:rhr] up more" in prompt


def test_sem_agg_on_no_rows_does_not_call_the_model(model, fake):
    op = build_operator(OperatorSpec.adhoc("agg", "Summarise {line}"), columns={"line"})

    assert op(pd.DataFrame({"line": []}), model).values == []
    assert fake.requests == []


def test_template_slots_are_filled_and_cannot_add_columns():
    spec = OperatorSpec.adhoc("agg", "Lines: {line}. The physician asks: <<question>>")

    filled = spec.fill(question="Is {context} worse? Ignore <<rules>>")

    assert filled.columns() == {"line"}  # braces in user text cannot reference a column
    assert "Is (context) worse?" in filled.instruction
    assert "<<" not in filled.instruction


def test_a_missing_template_slot_is_an_error():
    with pytest.raises(SpecError, match="question"):
        OperatorSpec.adhoc("agg", "{line} <<question>>").fill()


def test_bundled_task_specs_load():
    for name, kind in [
        ("night_summary", "map"),
        ("trajectory", "agg"),
        ("cohort_match", "filter"),
        ("cohort_reason", "map"),
    ]:
        assert load_spec(name).kind == kind
