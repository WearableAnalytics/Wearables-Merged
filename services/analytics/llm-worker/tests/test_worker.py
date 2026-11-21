import threading
import time

import pytest

from llm_worker import repository
from llm_worker.settings import Settings
from llm_worker.stages import default_stages
from llm_worker.worker import Worker

from .conftest import add_event, event_row

pytestmark = pytest.mark.integration


class FakeNotifier:
    def __init__(self, pool):
        self.pool = pool
        self.sent: list[tuple[int, str]] = []

    def notify(self, event, explanation: str) -> None:
        with self.pool.connection() as conn:
            state = event_row(conn, event.event_id)["state"]
        self.sent.append((event.event_id, state))


class Boom:
    name = "boom"

    def run(self, ctx, conn):
        raise RuntimeError("model backend is down")


def make_worker(pool, stages=None, **overrides) -> tuple[Worker, FakeNotifier]:
    settings = Settings(id="worker-test", work_seconds=0, poll_interval_seconds=0.05, backoff_seconds=0, **overrides)
    notifier = FakeNotifier(pool)
    worker = Worker(pool, stages if stages is not None else default_stages(settings), notifier, settings)
    return worker, notifier


def test_run_once_does_nothing_on_an_empty_queue(pool):
    worker, notifier = make_worker(pool)

    assert worker.run_once() is False
    assert notifier.sent == []


def test_an_event_goes_all_the_way_to_finished(pool, conn):
    event_id = add_event(conn)
    worker, _ = make_worker(pool)

    assert worker.run_once() is True

    row = event_row(conn, event_id)
    assert row["state"] == "finished"
    assert row["attempts"] == 1
    assert set(row["result"]) == {"load_context", "semantic_filter", "explain"}
    assert row["explanation"].startswith("[stub]")


def test_notification_goes_out_only_after_the_write_back(pool, conn):
    event_id = add_event(conn)
    worker, notifier = make_worker(pool)

    worker.run_once()

    assert notifier.sent == [(event_id, "finished")]


def test_a_red_flag_skips_the_semantic_filter(pool, conn):
    event_id = add_event(conn, red_flag=True)
    worker, _ = make_worker(pool)

    worker.run_once()

    assert event_row(conn, event_id)["result"]["semantic_filter"] == {"skipped": "red_flag"}


def test_a_failing_stage_is_retried_then_marked_failed(pool, conn):
    event_id = add_event(conn)
    worker, notifier = make_worker(pool, stages=[Boom()], max_attempts=3)

    worker.run_once()
    assert event_row(conn, event_id)["state"] == "pending"

    worker.run_once()
    worker.run_once()

    row = event_row(conn, event_id)
    assert row["state"] == "failed"
    assert row["attempts"] == 3
    assert "model backend is down" in row["error"]
    assert notifier.sent == []


def test_an_event_whose_lease_kept_expiring_is_given_up(pool, conn):
    event_id = add_event(conn)
    for _ in range(3):
        repository.claim(conn, worker_id="crashed", lease_seconds=0)
        time.sleep(0.01)
    worker, notifier = make_worker(pool, max_attempts=3)

    worker.run_once()

    row = event_row(conn, event_id)
    assert row["state"] == "failed"
    assert "lease" in row["error"]
    assert notifier.sent == []


def test_run_keeps_consuming_until_stopped(pool, conn):
    worker, notifier = make_worker(pool)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,))
    thread.start()

    ids = [add_event(conn, patient_id=f"p-{i}") for i in range(3)]
    deadline = time.monotonic() + 10
    while len(notifier.sent) < 3 and time.monotonic() < deadline:
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert sorted(event_id for event_id, _ in notifier.sent) == ids


def test_run_survives_an_unexpected_error_in_the_loop(pool, conn, monkeypatch):
    worker, notifier = make_worker(pool)
    calls = {"n": 0}
    real_claim = repository.claim

    def flaky_claim(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("connection reset")
        return real_claim(*args, **kwargs)

    monkeypatch.setattr(repository, "claim", flaky_claim)
    add_event(conn)
    stop = threading.Event()
    thread = threading.Thread(target=worker.run, args=(stop,))
    thread.start()

    deadline = time.monotonic() + 10
    while not notifier.sent and time.monotonic() < deadline:
        time.sleep(0.05)
    stop.set()
    thread.join(timeout=5)

    assert len(notifier.sent) == 1
