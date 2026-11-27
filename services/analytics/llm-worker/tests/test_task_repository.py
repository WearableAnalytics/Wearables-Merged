"""The task queue in PostgreSQL: one table for every kind of task, claimed with FOR UPDATE SKIP LOCKED."""

import threading

import pytest

from llm_worker.tasks import repository
from llm_worker.tasks.model import TaskOutcome

from .conftest import chat_request, notifications, pipeline_request, task_row

pytestmark = pytest.mark.integration

LEASE = 60


def one(conn, worker_id="w1", **kwargs):
    return repository.claim(conn, worker_id, LEASE, batch_size=lambda template: 1, **kwargs)


def test_claim_returns_nothing_when_the_queue_is_empty(conn):
    assert one(conn) == []


def test_enqueue_stores_the_request_and_its_priority(conn):
    task_id, created = repository.enqueue(conn, chat_request(), priority=10)

    row = task_row(conn, task_id)
    assert created
    assert (row["template"], row["trigger"], row["submitted_by"], row["priority"]) == (
        "patient_explain",
        "chat",
        "doctor",
        10,
    )
    assert row["params"] == {"patient_id": "P-001", "since_days": 7}
    assert row["state"] == "pending"


def test_the_same_pipeline_event_is_enqueued_only_once(conn):
    first, created = repository.enqueue(conn, pipeline_request(), priority=0)
    again, created_again = repository.enqueue(conn, pipeline_request(), priority=0)

    assert created and not created_again
    assert first == again


def test_chat_tasks_have_no_dedup_key_and_are_never_merged(conn):
    a, _ = repository.enqueue(conn, chat_request(), priority=10)
    b, _ = repository.enqueue(conn, chat_request(), priority=10)

    assert a != b


def test_higher_priority_is_claimed_first_even_if_it_arrived_later(conn):
    repository.enqueue(conn, chat_request(), priority=10)
    alert, _ = repository.enqueue(conn, pipeline_request(), priority=0)

    [run] = one(conn)

    assert run.task_id == alert and run.template == "alert_triage" and run.attempts == 1
    assert task_row(conn, alert)["state"] == "processing"


def test_a_batch_only_contains_tasks_of_the_same_template(conn):
    for night in ("2026-03-12", "2026-03-13"):
        repository.enqueue(conn, pipeline_request(night=night), priority=0)
    repository.enqueue(conn, chat_request(), priority=10)

    runs = repository.claim(conn, "w1", LEASE, batch_size=lambda template: 8)

    assert [r.template for r in runs] == ["alert_triage", "alert_triage"]


def test_batch_size_comes_from_the_template_of_the_first_task(conn):
    for night in ("2026-03-11", "2026-03-12", "2026-03-13"):
        repository.enqueue(conn, pipeline_request(night=night), priority=0)

    runs = repository.claim(conn, "w1", LEASE, batch_size=lambda template: 2 if template == "alert_triage" else 1)

    assert len(runs) == 2


def test_a_worker_can_be_limited_to_some_templates(conn):
    repository.enqueue(conn, pipeline_request(), priority=0)
    chat, _ = repository.enqueue(conn, chat_request(), priority=10)

    [run] = one(conn, templates=["patient_explain", "cohort_query"])

    assert run.task_id == chat


def test_two_workers_never_claim_the_same_task(pool):
    with pool.connection() as conn:
        for night in range(1, 21):
            repository.enqueue(conn, pipeline_request(night=f"2026-03-{night:02d}"), priority=0)

    claimed: list[int] = []
    lock = threading.Lock()

    def drain(worker_id: str) -> None:
        with pool.connection() as conn:
            while runs := repository.claim(conn, worker_id, LEASE, batch_size=lambda t: 3):
                with lock:
                    claimed.extend(r.task_id for r in runs)

    threads = [threading.Thread(target=drain, args=(f"w{i}",)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(claimed) == list(range(1, 21))


def test_an_expired_lease_can_be_claimed_by_someone_else(conn):
    task_id, _ = repository.enqueue(conn, chat_request(), priority=10)
    repository.claim(conn, "w1", -1, batch_size=lambda t: 1)  # lease already over

    [run] = one(conn, worker_id="w2")

    assert run.task_id == task_id and run.attempts == 2


def test_finish_writes_the_answer_and_result(conn):
    task_id, _ = repository.enqueue(conn, chat_request(), priority=10)
    [run] = one(conn)
    outcome = TaskOutcome(answer="Stable.", result={"nights": 7}, model="fake", spec_versions={"x": "x@1"})

    assert repository.finish(conn, run, "w1", outcome, notification=None)

    row = task_row(conn, task_id)
    assert (row["state"], row["answer"], row["result"], row["model"]) == ("finished", "Stable.", {"nights": 7}, "fake")
    assert row["spec_versions"] == {"x": "x@1"} and row["finished_at"] is not None
    assert notifications(conn) == []


def test_finish_writes_the_notification_in_the_same_step(conn):
    task_id, _ = repository.enqueue(conn, pipeline_request(), priority=0)
    [run] = one(conn)
    notification = {"patient_id": "P-001", "night_date": "2026-03-14", "verdict": "notify", "explanation": "x"}

    repository.finish(conn, run, "w1", TaskOutcome(answer="x"), notification=notification)

    [sent] = notifications(conn)
    assert (sent["task_id"], sent["patient_id"], sent["verdict"]) == (task_id, "P-001", "notify")


def test_a_worker_that_lost_its_lease_cannot_write_back(conn):
    task_id, _ = repository.enqueue(conn, pipeline_request(), priority=0)
    [run] = repository.claim(conn, "w1", -1, batch_size=lambda t: 1)
    one(conn, worker_id="w2")
    notification = {"patient_id": "P-001", "night_date": "2026-03-14", "verdict": "notify", "explanation": "x"}

    assert not repository.finish(conn, run, "w1", TaskOutcome(answer="late"), notification=notification)
    assert task_row(conn, task_id)["state"] == "processing"
    assert notifications(conn) == []


def test_fail_puts_the_task_back_with_a_backoff(conn):
    task_id, _ = repository.enqueue(conn, chat_request(), priority=10)
    [run] = one(conn)

    state = repository.fail(conn, run, "w1", "model down", max_attempts=3, backoff_seconds=30)

    row = task_row(conn, task_id)
    assert state == "pending" and row["error"] == "model down"
    assert one(conn) == []  # not due yet


def test_fail_gives_up_after_the_last_attempt(conn):
    task_id, _ = repository.enqueue(conn, chat_request(), priority=10)
    [run] = one(conn)

    assert repository.fail(conn, run, "w1", "broken", max_attempts=1, backoff_seconds=0) == "failed"
    assert task_row(conn, task_id)["state"] == "failed"


def test_tasks_and_notifications_can_be_listed_newest_first(conn):
    a, _ = repository.enqueue(conn, chat_request(), priority=10)
    b, _ = repository.enqueue(conn, pipeline_request(), priority=0)

    assert [t["task_id"] for t in repository.list_tasks(conn)] == [b, a]
    assert [t["task_id"] for t in repository.list_tasks(conn, trigger="chat")] == [a]
    assert repository.get_task(conn, a)["template"] == "patient_explain"
    assert repository.get_task(conn, 999) is None
    assert repository.list_notifications(conn) == []
