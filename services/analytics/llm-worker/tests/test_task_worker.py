"""The worker end to end: submit -> queue -> handler by template -> write-back -> notification (fake model)."""

import pytest

from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.semantic import LotusModel
from llm_worker.settings import Settings
from llm_worker.tasks import service
from llm_worker.tasks.model import TaskOutcome, TaskRequest
from llm_worker.tasks.registry import Deps, build_handlers
from llm_worker.worker import Worker

from .conftest import chat_request, notifications, task_row

pytestmark = pytest.mark.integration

STORE = load_bundled_store()
SUPPRESSED = {
    ("P-001", "2026-03-14"),
    ("P-003", "2026-03-14"),
    ("P-004", "2026-03-14"),
    ("P-008", "2026-03-14"),
    ("P-013", "2026-03-14"),
}  # documented benign causes (see the scenarios' `expect`)


class FakeNotifier:
    def __init__(self, pool):
        self.pool, self.sent = pool, []

    def notify(self, run, notification) -> None:
        with self.pool.connection() as conn:
            committed = task_row(conn, run.task_id)["state"]
        self.sent.append((notification["patient_id"], notification["verdict"], committed))


def make_worker(pool, fake_llm, handlers=None, **overrides):
    settings = Settings(**({"id": "worker-test", "backoff_seconds": 0, "poll_interval_seconds": 0.05} | overrides))
    if handlers is None:
        handlers = build_handlers(Deps(STORE, LotusModel(base_url=fake_llm.base_url, model="fake-small")))
    notifier = FakeNotifier(pool)
    return Worker(pool, handlers, notifier, settings), notifier


def drain(worker) -> int:
    n = 0
    while worker.run_once():
        n += 1
    return n


# --- submitting: permissions belong to the template


def test_simulating_the_pipeline_enqueues_one_alert_task_per_flagged_night_once(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm)

    assert service.simulate_pipeline(conn, STORE, worker.handlers) == (14, 14)
    assert service.simulate_pipeline(conn, STORE, worker.handlers) == (0, 14)


def test_chat_cannot_submit_an_alert_triage_task(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm)
    request = chat_request("alert_triage", patient_id="P-001", night="2026-03-14")

    with pytest.raises(service.TaskRejected, match="chat"):
        service.submit(conn, request, worker.handlers)


def test_an_unknown_template_or_bad_params_are_rejected(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm)

    with pytest.raises(service.TaskRejected, match="unknown template"):
        service.submit(conn, chat_request("drop_tables"), worker.handlers)
    with pytest.raises(service.TaskRejected, match="unknown patient"):
        service.submit(conn, chat_request(patient_id="P-999"), worker.handlers)


def test_submit_normalises_params_and_takes_the_priority_from_the_template(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm)

    submitted = service.submit(conn, chat_request(patient_id="P-010"), worker.handlers)

    row = task_row(conn, submitted.task_id)
    assert row["params"] == {"patient_id": "P-010", "since_days": 7} and row["priority"] == 10
    assert submitted.created and submitted.template == "patient_explain"


# --- running


def test_run_once_does_nothing_on_an_empty_queue(pool, fake_llm):
    worker, notifier = make_worker(pool, fake_llm)

    assert worker.run_once() is False and notifier.sent == []


def test_pipeline_alerts_are_triaged_and_only_unsuppressed_ones_notify_after_commit(pool, conn, fake_llm):
    worker, notifier = make_worker(pool, fake_llm)
    service.simulate_pipeline(conn, STORE, worker.handlers)

    assert drain(worker) == 2  # 14 alerts in batches of 8

    rows = [task_row(conn, i) for i in range(1, 15)]
    assert all(r["state"] == "finished" and r["answer"] for r in rows)
    sent = {(n["patient_id"], n["night_date"].isoformat()) for n in notifications(conn)}
    flagged = {(c.patient_id, c.night_date.isoformat()) for c in STORE.all_candidates()}
    assert sent == flagged - SUPPRESSED
    assert len(notifier.sent) == 9 and all(state == "finished" for _, _, state in notifier.sent)


def test_a_chat_question_is_answered_without_any_notification(pool, conn, fake_llm):
    worker, notifier = make_worker(pool, fake_llm)
    submitted = service.submit(conn, chat_request(patient_id="P-010"), worker.handlers)

    drain(worker)

    row = task_row(conn, submitted.task_id)
    assert row["state"] == "finished" and row["answer"].startswith("[fake model]")
    assert row["spec_versions"]["trajectory"] == "trajectory@1" and row["model"] == "fake-small"
    assert notifications(conn) == [] and notifier.sent == []


def test_the_clinical_path_runs_before_waiting_chat_questions(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm)
    chat = service.submit(conn, chat_request(patient_id="P-010"), worker.handlers)
    service.simulate_pipeline(conn, STORE, worker.handlers)

    worker.run_once()

    assert task_row(conn, chat.task_id)["state"] == "pending"
    assert task_row(conn, 2)["state"] == "finished"  # the first alert


class NotifyingChatHandler:
    """A buggy handler that claims every result should notify. The worker must not trust it."""

    template, triggers, priority, batch_size = "patient_explain", frozenset({"chat"}), 10, 1

    def validate(self, params):
        return params

    def run(self, runs):
        return [TaskOutcome(answer="Notify now!", notify=True, result={"verdict": "notify"}) for _ in runs]


def test_only_pipeline_alert_triage_can_ever_write_a_notification(pool, conn, fake_llm):
    worker, notifier = make_worker(pool, fake_llm, handlers={"patient_explain": NotifyingChatHandler()})
    service.submit(conn, chat_request(patient_id="P-010"), worker.handlers)

    drain(worker)

    assert notifications(conn) == [] and notifier.sent == []


def test_a_model_outage_puts_the_batch_back_for_a_retry(pool, conn, fake_llm):
    worker, notifier = make_worker(pool, fake_llm, backoff_seconds=60)
    submitted = service.submit(conn, chat_request(patient_id="P-010"), worker.handlers)
    fake_llm.mode = "error"

    worker.run_once()

    row = task_row(conn, submitted.task_id)
    assert row["state"] == "pending" and "LLMUnavailable" in row["error"]


def test_a_worker_can_be_limited_to_chat_templates(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm, templates="patient_explain,cohort_query")
    service.simulate_pipeline(conn, STORE, worker.handlers)
    chat = service.submit(conn, chat_request(patient_id="P-014"), worker.handlers)

    drain(worker)

    assert task_row(conn, chat.task_id)["state"] == "finished"
    assert task_row(conn, 1)["state"] == "pending"


def test_a_task_whose_lease_expired_too_often_is_failed(pool, conn, fake_llm):
    worker, _ = make_worker(pool, fake_llm, max_attempts=1)
    submitted = service.submit(conn, chat_request(patient_id="P-014"), worker.handlers)
    conn.execute("UPDATE tasks.task_runs SET attempts = 1 WHERE task_id = %s", (submitted.task_id,))

    worker.run_once()

    assert task_row(conn, submitted.task_id)["state"] == "failed"


def test_requests_are_validated_before_they_reach_the_queue():
    with pytest.raises(ValueError):
        TaskRequest(template="cohort_query", prompt="", trigger="chat", submitted_by="doctor")
    with pytest.raises(ValueError):
        TaskRequest(template="cohort_query", prompt="x" * 1001, trigger="chat", submitted_by="doctor")
