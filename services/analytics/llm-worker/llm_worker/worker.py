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
        """Claim up to `batch_size` candidates, run them through the pipeline together, write each one back."""
        s = self.settings
        finished = []
        with self.pool.connection() as conn:
            events = repository.claim_batch(conn, s.id, s.lease_seconds, s.batch_size)
            if not events:
                return False
            log.info("claimed %d event(s): %s", len(events), [e.event_id for e in events])

            runnable = []
            for event in events:
                if event.attempts > s.max_attempts:
                    self._fail(conn, event, "lease expired too many times; the worker probably crashed")
                else:
                    runnable.append(event)
            if not runnable:
                return True

            try:
                ctxs = run_pipeline(runnable, self.stages, conn)
            except Exception as exc:  # e.g. the model is down: the whole batch is retried with backoff
                log.exception("batch %s failed", [e.event_id for e in runnable])
                for event in runnable:
                    self._fail(conn, event, f"{type(exc).__name__}: {exc}")
                return True

            for ctx in ctxs:
                if ctx.error is not None:
                    self._fail(conn, ctx.event, ctx.error)
                elif repository.finish(conn, ctx.event, s.id, ctx.result, ctx.explanation):
                    finished.append(ctx)
                else:
                    log.warning("lost the lease on event %s, someone else will finish it", ctx.event.event_id)

        for ctx in finished:
            verdict = ctx.decision.verdict if ctx.decision else "?"
            log.info("finish event %s (%s)", ctx.event.event_id, verdict)
            if ctx.notify:
                self.notifier.notify(ctx.event, ctx.explanation)
        return True

    def _fail(self, conn, event: Event, error: str) -> None:
        s = self.settings
        state = repository.fail(conn, event, s.id, error, s.max_attempts, s.backoff_seconds)
        log.warning("event %s is %s: %s", event.event_id, state or "no longer ours", error)
