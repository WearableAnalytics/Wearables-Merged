import logging
import threading

from psycopg import Connection
from psycopg_pool import ConnectionPool

from .notify import Notifier
from .settings import Settings
from .tasks import repository
from .tasks.model import TaskOutcome, TaskRun, may_notify
from .tasks.registry import TaskHandler

log = logging.getLogger(__name__)


class Worker:
    """Claims the most urgent tasks, runs them with the handler of their template, writes the results back."""

    def __init__(self, pool: ConnectionPool, handlers: dict[str, TaskHandler], notifier: Notifier, settings: Settings):
        self.pool = pool
        self.handlers = handlers
        self.notifier = notifier
        self.settings = settings

    def run(self, stop: threading.Event) -> None:
        log.info("worker %s started (templates: %s)", self.settings.id, self.settings.template_list or "all")
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
        sent = []
        with self.pool.connection() as conn:
            runs = repository.claim(conn, s.id, s.lease_seconds, self._batch_size, templates=s.template_list)
            if not runs:
                return False
            template = runs[0].template
            log.info("claimed %d %s task(s): %s", len(runs), template, [r.task_id for r in runs])

            runnable = []
            for run in runs:
                if run.attempts > s.max_attempts:
                    self._fail(conn, run, "lease expired too many times; the worker probably crashed")
                else:
                    runnable.append(run)
            if not runnable:
                return True

            handler = self.handlers.get(template)
            try:
                if handler is None:
                    raise LookupError(f"no handler for template {template!r}")
                outcomes = handler.run(runnable)
                if len(outcomes) != len(runnable):
                    raise RuntimeError(f"{template} returned {len(outcomes)} outcomes for {len(runnable)} tasks")
            except Exception as exc:  # e.g. the model is down: the whole batch is retried with backoff
                log.exception("%s batch %s failed", template, [r.task_id for r in runnable])
                for run in runnable:
                    self._fail(conn, run, f"{type(exc).__name__}: {exc}")
                return True

            for run, outcome in zip(runnable, outcomes, strict=True):
                if outcome.error is not None:
                    self._fail(conn, run, outcome.error)
                    continue
                notification = _notification(run, outcome)
                if repository.finish(conn, run, s.id, outcome, notification):
                    log.info("finish task %s (%s)", run.task_id, template)
                    if notification:
                        sent.append((run, notification))
                else:
                    log.warning("lost the lease on task %s, someone else will finish it", run.task_id)

        for run, notification in sent:  # after the commit
            self.notifier.notify(run, notification)
        return True

    def _batch_size(self, template: str) -> int:
        handler = self.handlers.get(template)
        return min(handler.batch_size, self.settings.batch_size) if handler else 1

    def _fail(self, conn: Connection, run: TaskRun, error: str) -> None:
        s = self.settings
        state = repository.fail(conn, run, s.id, error, s.max_attempts, s.backoff_seconds)
        log.warning("task %s is %s: %s", run.task_id, state or "no longer ours", error)


def _notification(run: TaskRun, outcome: TaskOutcome) -> dict | None:
    """Only a pipeline alert_triage task may notify, whatever its handler says."""
    if not (outcome.notify and may_notify(run)):
        return None
    return {
        "patient_id": run.params["patient_id"],
        "night_date": run.params["night"],
        "verdict": outcome.result.get("verdict", "notify"),
        "explanation": outcome.answer,
    }
