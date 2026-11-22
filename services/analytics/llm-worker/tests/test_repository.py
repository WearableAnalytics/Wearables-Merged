import threading
import time
from datetime import UTC, date, datetime

import pytest

from llm_worker import repository
from llm_worker.providers.scenarios import load_bundled_store

from .conftest import add_event, event_row

pytestmark = pytest.mark.integration


def test_claim_returns_nothing_when_the_queue_is_empty(conn):
    assert repository.claim(conn, worker_id="a", lease_seconds=60) is None


def test_claim_takes_the_oldest_pending_event_and_locks_it(conn):
    first = add_event(conn, patient_id="p-001")
    add_event(conn, patient_id="p-002")

    event = repository.claim(conn, worker_id="a", lease_seconds=60)

    assert event.event_id == first
    assert event.features == {"rhr_z": 2.4, "temp_z": 1.9}
    assert event.attempts == 1
    row = event_row(conn, first)
    assert row["state"] == "processing"
    assert row["locked_by"] == "a"
    assert row["locked_until"] > row["started_at"]


def test_two_workers_never_claim_the_same_event(pool):
    with pool.connection() as conn:
        for i in range(20):
            add_event(conn, patient_id=f"p-{i:03}")

    claimed: dict[str, list[int]] = {"a": [], "b": []}

    def drain(worker_id: str) -> None:
        with pool.connection() as conn:
            while event := repository.claim(conn, worker_id=worker_id, lease_seconds=60):
                claimed[worker_id].append(event.event_id)

    threads = [threading.Thread(target=drain, args=(name,)) for name in claimed]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    everything = claimed["a"] + claimed["b"]
    assert sorted(everything) == list(range(1, 21))


def test_an_expired_lease_can_be_claimed_by_someone_else(conn):
    event_id = add_event(conn)
    repository.claim(conn, worker_id="a", lease_seconds=0)
    time.sleep(0.01)

    event = repository.claim(conn, worker_id="b", lease_seconds=60)

    assert event.event_id == event_id
    assert event.attempts == 2
    assert event_row(conn, event_id)["locked_by"] == "b"


def test_finish_writes_the_result_back(conn):
    event_id = add_event(conn)
    event = repository.claim(conn, worker_id="a", lease_seconds=60)

    assert repository.finish(conn, event, worker_id="a", result={"explain": {"model": "stub"}}, explanation="hello")

    row = event_row(conn, event_id)
    assert row["state"] == "finished"
    assert row["result"] == {"explain": {"model": "stub"}}
    assert row["explanation"] == "hello"
    assert row["finished_at"] is not None
    assert row["locked_until"] is None


def test_a_worker_that_lost_its_lease_cannot_write_back(conn):
    event_id = add_event(conn)
    stale = repository.claim(conn, worker_id="a", lease_seconds=0)
    time.sleep(0.01)
    repository.claim(conn, worker_id="b", lease_seconds=60)

    assert not repository.finish(conn, stale, worker_id="a", result={}, explanation="late")
    assert repository.fail(conn, stale, worker_id="a", error="late", max_attempts=3, backoff_seconds=0) is None
    assert event_row(conn, event_id)["state"] == "processing"


def test_fail_puts_the_event_back_with_a_backoff(conn):
    event_id = add_event(conn)
    event = repository.claim(conn, worker_id="a", lease_seconds=60)

    state = repository.fail(conn, event, worker_id="a", error="boom", max_attempts=3, backoff_seconds=30)

    row = event_row(conn, event_id)
    assert state == "pending"
    assert row["error"] == "boom"
    assert (row["run_after"] - datetime.now(UTC)).total_seconds() > 20
    assert repository.claim(conn, worker_id="a", lease_seconds=60) is None


def test_fail_gives_up_after_the_last_attempt(conn):
    event_id = add_event(conn)
    for _ in range(3):
        event = repository.claim(conn, worker_id="a", lease_seconds=60)
        state = repository.fail(conn, event, worker_id="a", error="boom", max_attempts=3, backoff_seconds=0)

    assert state == "failed"
    assert event_row(conn, event_id)["attempts"] == 3
    assert repository.claim(conn, worker_id="a", lease_seconds=60) is None


def test_claim_batch_takes_up_to_the_limit_in_queue_order(conn):
    ids = [add_event(conn, patient_id=f"p-{i}") for i in range(10)]

    batch = repository.claim_batch(conn, worker_id="a", lease_seconds=60, limit=8)

    assert [event.event_id for event in batch] == ids[:8]
    assert all(event_row(conn, i)["state"] == "processing" for i in ids[:8])
    assert all(event_row(conn, i)["state"] == "pending" for i in ids[8:])


def test_two_workers_claiming_batches_never_overlap(pool):
    with pool.connection() as conn:
        for i in range(20):
            add_event(conn, patient_id=f"p-{i}")
    claimed: dict[str, list[int]] = {"a": [], "b": []}

    def consume(worker_id: str) -> None:
        with pool.connection() as conn:
            while batch := repository.claim_batch(conn, worker_id=worker_id, lease_seconds=60, limit=3):
                claimed[worker_id] += [event.event_id for event in batch]

    threads = [threading.Thread(target=consume, args=(w,)) for w in claimed]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(claimed["a"] + claimed["b"]) == list(range(1, 21))
    assert not set(claimed["a"]) & set(claimed["b"])


def test_an_event_becomes_an_alert_candidate(conn):
    add_event(conn, reasons="rhr_z>2, temp_delta>0.5", red_flag=True, features={"l2_score": 0.7})

    event = repository.claim(conn, worker_id="a", lease_seconds=60)
    candidate = event.to_candidate()

    assert candidate.candidate_id == event.event_id
    assert candidate.trigger_reasons == ["rhr_z>2", "temp_delta>0.5"]
    assert candidate.red_flag is True and candidate.l2_score == 0.7


def test_seed_enqueues_one_candidate_per_bundled_scenario(conn):
    store = load_bundled_store()

    repository.seed(conn, store)
    repository.seed(conn, store)  # idempotent

    rows = conn.execute("SELECT patient_id, night_date, red_flag FROM worker.suspicious_events").fetchall()
    assert len(rows) == len(store.names())
    assert {(r[0], r[2]) for r in rows} >= {("P-009", True), ("P-001", False)}
    assert {r[1] for r in rows} == {date(2026, 3, 14)}
