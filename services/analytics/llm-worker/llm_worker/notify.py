import logging
from typing import Protocol

from .tasks.model import TaskRun

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, run: TaskRun, notification: dict) -> None: ...


class LogNotifier:
    """Stand-in for the clinician channel. The notification itself is already stored in tasks.notifications."""

    def notify(self, run: TaskRun, notification: dict) -> None:
        log.info(
            "[notify] %s on %s: %s (task %s)",
            notification["patient_id"],
            notification["night_date"],
            notification["verdict"],
            run.task_id,
        )
