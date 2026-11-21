import logging
import threading
from collections.abc import Sequence

from psycopg_pool import ConnectionPool

from . import repository
from .notify import Notifier
from .pipeline import Event, Stage, run_pipeline
from .settings import Settings

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, pool: ConnectionPool, stages: Sequence[Stage], notifier: Notifier, settings: Settings):
        self.pool = pool
        self.stages = stages
        self.notifier = notifier
        self.settings = settings

    def run(self, stop: threading.Event) -> None:
        log.info("worker %s started", self.settings.id)
        while not stop.is_set():
            try:
                busy = self.run_once()
            except Exception:
                log.exception("poll failed, retrying in %.1fs", self.settings.poll_interval_seconds)
                busy = False
            if not busy:
                stop.wait(self.settings.poll_interval_seconds)
        log.info("worker %s stopped", self.settings.id)

    def run_once(self) -> bool:
        s = self.settings
        with self.pool.connection() as conn:
            event = repository.claim(conn, s.id, s.lease_seconds)
            if event is None:
                return False

            log.info("claimed event %s (attempt %s)", event.event_id, event.attempts)
            if event.attempts > s.max_attempts:
                self._fail(conn, event, "lease expired too many times; the worker probably crashed")
                return True

            try:
                ctx = run_pipeline(event, self.stages, conn)
            except Exception as exc:
                log.exception("event %s failed", event.event_id)
                self._fail(conn, event, f"{type(exc).__name__}: {exc}")
                return True

            if not repository.finish(conn, event, s.id, ctx.result, ctx.explanation):
                log.warning("lost the lease on event %s, someone else will finish it", event.event_id)
                return True

        log.info("finish event %s", event.event_id)
        self.notifier.notify(event, ctx.explanation)
        return True

    def _fail(self, conn, event: Event, error: str) -> None:
        s = self.settings
        state = repository.fail(conn, event, s.id, error, s.max_attempts, s.backoff_seconds)
        log.warning("event %s is %s: %s", event.event_id, state or "no longer ours", error)
