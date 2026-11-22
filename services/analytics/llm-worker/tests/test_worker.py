"""The worker end to end: queue -> mocked evidence -> LOTUS (fake model over HTTP) -> write-back -> notify."""

import threading
import time

import pytest

from llm_worker import repository
from llm_worker.providers.scenarios import load_bundled_store
from llm_worker.settings import Settings
from llm_worker.stages import default_stages
from llm_worker.worker import Worker

from .conftest import add_event, event_row

pytestmark = pytest.mark.integration

STORE = load_bundled_store()


class FakeNotifier:
    def __init__(self, pool):
        self.pool = pool
        self.sent: list[tuple[str, str]] = []

    def notify(self, event, explanation: str) -> None:
        with self.pool.connection() as conn:
            state = event_row(conn, event.event_id)["state"]
        self.sent.append((event.patient_id, state))


def make_worker(pool, fake_llm, **overrides) -> tuple[Worker, FakeNotifier]:
    values = dict(
        id="worker-test",
        poll_interval_seconds=0.05,
        backoff_seconds=0,
        llm_base_url=fake_llm.base_url,
        llm_model="fake-small",
    )
    settings = Settings(**(values | overrides))
    notifier = FakeNotifier(pool)
    return Worker(pool, default_stages(settings, store=STORE), notifier, settings), notifier


def seeded(conn) -> dict[str, int]:
    repository.seed(conn, STORE)
    rows = conn.execute("SELECT patient_id, event_id FROM worker.suspicious_events").fetchall()
    return {STORE.patient(pid).name: event_id for pid, event_id in rows}


def test_run_once_does_nothing_on_an_empty_queue(pool, fake_llm):
    worker, notifier = make_worker(pool, fake_llm)

    assert worker.run_once() is False
    assert notifier.sent == []


def test_a_candidate_goes_through_evidence_triage_and_explain(pool, conn, fake_llm):
    ids = seeded(conn)
    worker, _ = make_worker(pool, fake_llm, batch_size=20)

    worker.run_once()

    row = event_row(conn, ids["vaccination_documented"])
    assert row["state"] == "finished" and row["attempts"] == 1
    assert set(row["result"]) == {"load_evidence", "triage", "explain"}
    assert row["result"]["triage"]["verdict"] == "suppress"
    assert row["result"]["triage"]["operator"] == "triage@1"
    assert row["result"]["explain"]["cited_ids"]
    assert row["explanation"].startswith("[fake model]")


def test_one_run_handles_a_batch_of_eight(pool, conn, fake_llm):
    ids = seeded(conn)  # 9 scenarios
    worker, _ = make_worker(pool, fake_llm)

    worker.run_once()

    states = [event_row(conn, i)["state"] for i in ids.values()]
    assert states.count("finished") == 8 and states.count("pending") == 1
    triage_calls = [r for r in fake_llm.requests if "Claim:" in r["messages"][-1]["content"]]
    assert len(triage_calls) == 7  # 8 candidates, one of them a red flag that skips the model

    worker.run_once()
    assert all(event_row(conn, i)["state"] == "finished" for i in ids.values())


def test_suppressed_candidates_are_not_notified_but_red_flags_always_are(pool, conn, fake_llm):
    seeded(conn)
    worker, notifier = make_worker(pool, fake_llm)

    while worker.run_once():
        pass

    notified = {STORE.patient(pid).name for pid, _ in notifier.sent}
    assert "red_flag" in notified and "alcohol_undocumented" in notified
    assert "vaccination_documented" not in notified and "alcohol_documented" not in notified
    assert {state for _, state in notifier.sent} == {"finished"}  # only after the write-back


def test_a_model_outage_puts_the_whole_batch_back_and_notifies_nobody(pool, conn, fake_llm):
    ids = seeded(conn)
    fake_llm.mode = "error"
    worker, notifier = make_worker(pool, fake_llm, max_attempts=2, batch_size=20)

    worker.run_once()
    row = event_row(conn, ids["vaccination_documented"])
    assert row["state"] == "pending" and "LLMUnavailable" in row["error"]

    worker.run_once()
    assert event_row(conn, ids["vaccination_documented"])["state"] == "failed"
    assert notifier.sent == []


def test_a_candidate_without_evidence_fails_alone(pool, conn, fake_llm):
    ids = seeded(conn)
    missing = add_event(conn, patient_id="nobody")
    worker, _ = make_worker(pool, fake_llm, batch_size=20)

    worker.run_once()

    row = event_row(conn, missing)
    assert row["state"] == "pending" and "nobody" in row["error"]
    assert all(event_row(conn, i)["state"] == "finished" for i in ids.values())


def test_an_event_whose_lease_kept_expiring_is_given_up(pool, conn, fake_llm):
    event_id = seeded(conn)["red_flag"]
    conn.execute(
        "UPDATE worker.suspicious_events SET run_after = now() + interval '1 hour' WHERE event_id <> %s", (event_id,)
    )
    for _ in range(3):
        repository.claim(conn, worker_id="crashed", lease_seconds=0)
        time.sleep(0.01)
    worker, notifier = make_worker(pool, fake_llm, max_attempts=3)

    worker.run_once()

    row = event_row(conn, event_id)
    assert row["state"] == "failed" and "lease" in row["error"]
    assert notifier.sent == []


def test_run_keeps_consuming_until_stopped(pool, conn, fake_llm):
    worker, notifier = make_worker(pool, fake_llm, batch_size=3)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,))
    thread.start()

    seeded(conn)
    deadline = time.monotonic() + 60
    while len(notifier.sent) < 5 and time.monotonic() < deadline:  # 9 scenarios, 4 of them suppressed
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=30)

    assert not thread.is_alive()
    assert len(notifier.sent) == 5


def test_run_survives_an_unexpected_error_in_the_loop(pool, conn, fake_llm, monkeypatch):
    worker, notifier = make_worker(pool, fake_llm)
    calls = {"n": 0}
    real = repository.claim_batch

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("connection reset")
        return real(*args, **kwargs)

    monkeypatch.setattr(repository, "claim_batch", flaky)
    seeded(conn)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,))
    thread.start()

    deadline = time.monotonic() + 60
    while not notifier.sent and time.monotonic() < deadline:
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=30)

    assert notifier.sent
