import logging
from typing import Protocol

from .pipeline import Event

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, event: Event, explanation: str | None) -> None: ...


class LogNotifier:
    def notify(self, event: Event, explanation: str | None) -> None:
        log.info("[notify] event %s for %s on %s is finished", event.event_id, event.patient_id, event.night_date)
