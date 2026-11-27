"""The demo on a real model (local Ollama): every demo prompt and every flagged night, through the task handlers.

    uv run pytest -m ollama tests/test_demo_ollama.py -s     # WORKER_DEMO_REPORT=path.md also writes the report

Asserted: what the code guarantees (routing, read-only chat, red flags, citations checked, no errors).
Not asserted: answer quality. It is printed (and written to the report) for a human to judge against `expect`.
"""

import os
import time
from datetime import datetime

import httpx
import pytest

from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.settings import Settings
from llm_worker.stages import model_from
from llm_worker.tasks.bridge import alert_request
from llm_worker.tasks.demo import DEMO_PROMPTS
from llm_worker.tasks.model import TaskRun
from llm_worker.tasks.registry import Deps, build_handlers
from llm_worker.tasks.router import route

pytestmark = pytest.mark.ollama

STORE = load_bundled_store()
REPORT: list[str] = []


@pytest.fixture(scope="module")
def settings() -> Settings:
    s = Settings()
    try:
        httpx.get(s.llm_base_url.removesuffix("/v1") + "/api/tags", timeout=3).raise_for_status()
    except Exception as exc:
        pytest.skip(f"no Ollama at {s.llm_base_url}: {exc}")
    return s


@pytest.fixture(scope="module")
def handlers(settings):
    handlers = build_handlers(Deps(source=STORE, model=model_from(settings)))
    REPORT.append(f"# Demo on {settings.llm_model} ({datetime.now():%Y-%m-%d %H:%M})\n")
    yield handlers
    if path := os.environ.get("WORKER_DEMO_REPORT"):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(REPORT) + "\n")


def test_every_flagged_night_is_triaged(handlers):
    pairs = [pair for name in STORE.names() for pair in STORE.get(name).expected()]
    runs = []
    for i, (candidate, _) in enumerate(pairs, start=1):
        r = alert_request(candidate)
        runs.append(TaskRun(i, r.template, r.params, r.prompt, "pipeline", "pipeline", 1))

    start = time.perf_counter()
    outcomes = [o for b in range(0, len(runs), 8) for o in handlers["alert_triage"].run(runs[b : b + 8])]
    elapsed = time.perf_counter() - start

    REPORT.append(f"## alert_triage: {len(runs)} flagged nights in {elapsed:.0f} s\n")
    REPORT.append("| patient | night | expected | got | notify | explanation |")
    REPORT.append("| --- | --- | --- | --- | --- | --- |")
    hits = 0
    for (candidate, expected), run, o in zip(pairs, runs, outcomes, strict=True):
        assert o.error is None
        got = o.result["verdict"]
        hits += got == expected
        assert o.notify == (got != "suppress")
        if candidate.red_flag:
            assert got == "red_flag_bypass"
        assert not o.result["explain"]["invalid_cited_ids"] or o.result["explain"]["cited_ids"] is not None
        text = (o.answer or "").replace("\n", " ").replace("|", "/")
        REPORT.append(f"| {candidate.patient_id} | {run.params['night']} | {expected} | {got} | {o.notify} | {text} |")
    REPORT.append(f"\n**{hits} of {len(runs)} as expected.**\n")
    print("\n".join(REPORT))


@pytest.mark.parametrize("demo", DEMO_PROMPTS, ids=[f"prompt{i + 1}" for i in range(len(DEMO_PROMPTS))])
def test_demo_prompt(handlers, demo):
    routed = route(
        demo["text"], submitted_by="doctor", known_patients=set(STORE.patient_ids()), filters=demo.get("filters")
    )
    request = routed.request
    assert request.template == demo["template"]
    handler = handlers[request.template]
    assert "chat" in handler.triggers
    params = handler.validate(request.params)

    start = time.perf_counter()
    [outcome] = handler.run([TaskRun(1, request.template, params, request.prompt, "chat", "doctor", 1)])
    elapsed = time.perf_counter() - start

    assert outcome.error is None and outcome.answer
    assert outcome.notify is False
    if request.template == "cohort_query":
        assert {m["patient_id"] for m in outcome.result["matches"]} <= set(STORE.patient_ids())
        got = ", ".join(m["patient_id"] for m in outcome.result["matches"]) or "none"
    else:
        assert set(outcome.result["cited_ids"]) <= set(outcome.result["evidence_ids"])
        got = f"cited {outcome.result['cited_ids']}, invalid {outcome.result['invalid_cited_ids']}"

    REPORT.append(f"## {demo['text']}\n")
    REPORT.append(
        f"`{request.template}({params})` · {elapsed:.1f} s" + (f" · notice: {routed.notice}" if routed.notice else "")
    )
    REPORT.append(f"\n*Expected:* {demo['expect']}\n\n*Got:* {got}\n")
    REPORT.append("> " + (outcome.answer or "").replace("\n", "\n> ") + "\n")
    print("\n".join(REPORT[-4:]))
