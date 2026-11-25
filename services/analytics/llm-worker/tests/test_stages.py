from datetime import date

import pytest

from llm_worker.pipeline import Context, Event, run_pipeline
from llm_worker.settings import Settings
from llm_worker.stages import default_stages
from llm_worker.stages.explain import Explain
from llm_worker.stages.semantic_filter import SemanticFilter


class FakeSleep:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_event(**overrides) -> Event:
    values = dict(
        event_id=1,
        patient_id="p-001",
        night_date=date(2026, 3, 14),
        reasons="rule:multi_signal",
        red_flag=False,
        features={"rhr_z": 2.4, "temp_z": 1.9},
        attempts=1,
    )
    return Event(**(values | overrides))


class Recorder:
    def __init__(self, name: str, output: dict, stop: bool = False):
        self.name = name
        self.output = output
        self.stop = stop
        self.seen: list[str] = []

    def run(self, ctx: Context, conn) -> dict:
        self.seen.append(",".join(ctx.result))
        ctx.stop = self.stop
        return self.output


def test_pipeline_stores_each_stage_output_under_its_name():
    first, second = Recorder("first", {"a": 1}), Recorder("second", {"b": 2})

    ctx = run_pipeline(make_event(), [first, second], conn=None)

    assert ctx.result == {"first": {"a": 1}, "second": {"b": 2}}
    assert second.seen == ["first"]


def test_pipeline_stops_when_a_stage_asks_to():
    first, second = Recorder("first", {}, stop=True), Recorder("second", {})

    ctx = run_pipeline(make_event(), [first, second], conn=None)

    assert list(ctx.result) == ["first"]
    assert second.seen == []


def test_semantic_filter_skips_red_flags_without_doing_any_work():
    sleep = FakeSleep()
    ctx = Context(make_event(red_flag=True))

    output = SemanticFilter(seconds=5, sleep=sleep).run(ctx, conn=None)

    assert output == {"skipped": "red_flag"}
    assert sleep.calls == []


def test_semantic_filter_works_for_a_while_and_explains_nothing_yet():
    sleep = FakeSleep()
    ctx = Context(make_event())

    output = SemanticFilter(seconds=5, sleep=sleep).run(ctx, conn=None)

    assert output == {"explained": False, "cause": None}
    assert sleep.calls == [5]


def test_explain_writes_an_explanation_from_the_numbers_and_the_context():
    sleep = FakeSleep()
    ctx = Context(make_event(), patient={"diary": [{"text": "slept badly"}], "profile": [{"text": "54 y, female"}]})
    ctx.result["semantic_filter"] = {"explained": False, "cause": None}

    output = Explain(seconds=5, sleep=sleep).run(ctx, conn=None)

    assert sleep.calls == [5]
    assert "2026-03-14" in ctx.explanation
    assert "rule:multi_signal" in ctx.explanation
    assert "rhr_z=2.4" in ctx.explanation and "temp_z=1.9" in ctx.explanation
    assert "1 diary entry" in ctx.explanation
    assert output == {"model": "stub", "length": len(ctx.explanation)}


def test_explain_says_a_red_flag_always_needs_review():
    ctx = Context(make_event(red_flag=True))
    ctx.result["semantic_filter"] = {"skipped": "red_flag"}

    Explain(seconds=0, sleep=FakeSleep()).run(ctx, conn=None)

    assert "red flag" in ctx.explanation.lower()
    assert "review" in ctx.explanation.lower()


def test_default_stages_split_the_work_between_filter_and_explain():
    sleep = FakeSleep()

    stages = default_stages(Settings(work_seconds=10), sleep=sleep)
    ctx = Context(make_event())
    for stage in stages[1:]:
        stage.run(ctx, conn=None)

    assert [stage.name for stage in stages] == ["load_context", "semantic_filter", "explain"]
    assert sleep.calls == [5, 5]


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WORKER_WORK_SECONDS", "2.5")
    monkeypatch.setenv("WORKER_ID", "worker-a")

    settings = Settings()

    assert settings.work_seconds == 2.5
    assert settings.id == "worker-a"
