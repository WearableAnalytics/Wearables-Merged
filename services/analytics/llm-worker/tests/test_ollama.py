"""Real model through LOTUS (local Ollama). Not part of the default run:

    uv run pytest -m ollama -s            # WORKER_LLM_BASE_URL / WORKER_LLM_MODEL pick the endpoint and model

Hard assertions cover what the code guarantees (red flags, citations, the plumbing of a plain-language question).
Judgement quality is model-dependent and is NOT asserted: the per-scenario table is printed for review (`-s`) and
measured on the cluster model (ADR-0005). qwen2.5:7b on 2026-11-21: triage@1 5-6 of 8 scenarios as expected;
`future_note_leak` was wrongly suppressed (a hike six days earlier was taken as the cause).
"""

import httpx
import pandas as pd
import pytest

from llm_worker.evidence import gather
from llm_worker.pipeline import Event, run_pipeline
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.render import render
from llm_worker.semantic import LotusModel, OperatorSpec, build_operator
from llm_worker.settings import Settings
from llm_worker.stages import default_stages

pytestmark = pytest.mark.ollama

STORE = load_bundled_store()


@pytest.fixture(scope="module")
def settings() -> Settings:
    s = Settings()
    try:
        httpx.get(s.llm_base_url.removesuffix("/v1") + "/api/tags", timeout=3).raise_for_status()
    except Exception as exc:
        pytest.skip(f"no Ollama at {s.llm_base_url}: {exc}")
    return s


@pytest.fixture(scope="module")
def results(settings):
    events = []
    for i, name in enumerate(STORE.names(), start=1):
        c = STORE.get(name).candidate(candidate_id=i)
        events.append(
            Event(i, c.patient_id, c.night_date, ", ".join(c.trigger_reasons), c.red_flag, {"l2_score": c.l2_score}, 1)
        )
    ctxs = run_pipeline(events, default_stages(settings, store=STORE), conn=None)
    by_name = {STORE.patient(ctx.event.patient_id).name: ctx for ctx in ctxs}

    print(f"\n\nmodel: {settings.llm_model}")
    print(f"{'scenario':26} {'expected':16} {'got':18} {'fallback':8} cited")
    for name, ctx in by_name.items():
        print(
            f"{name:26} {STORE.get(name).expect_verdict:16} {ctx.decision.verdict:18} "
            f"{str(ctx.explained.fallback):8} {ctx.explained.cited_ids}"
        )
        print(f"{'':26} triage: {(ctx.decision.rationale or '').strip()[:160]}")
        print(f"{'':26} note:   {ctx.explanation[:200]}")
    return by_name


def test_red_flags_are_never_suppressed(results):
    assert results["red_flag"].decision.verdict == "red_flag_bypass"
    assert results["red_flag"].notify is True


def test_every_candidate_gets_an_explanation_with_only_known_citations(results):
    for ctx in results.values():
        assert ctx.explanation
        assert set(ctx.explained.cited_ids) <= ctx.rendered.ids


def test_a_plain_language_question_finds_the_right_patient(settings):
    """A data scientist's question, written in English, no code: who travelled to the mountains?"""
    question = OperatorSpec.adhoc(
        "filter", "In {context}, the patient says they travelled to the mountains or to high altitude"
    )
    op = build_operator(question, columns={"numeric", "context"})
    names = STORE.names()
    rows = [render(gather(STORE.get(n).candidate(candidate_id=1), STORE.numeric, STORE.descriptive)) for n in names]
    df = pd.DataFrame({"numeric": [r.numeric for r in rows], "context": [r.context for r in rows]})

    result = op(df, LotusModel(base_url=settings.llm_base_url, model=settings.llm_model))

    hits = [n for n, hit in zip(names, result.values, strict=True) if hit]
    print(f"\nquestion: {question.instruction}\nhits: {hits}")
    assert "altitude_documented" in hits
