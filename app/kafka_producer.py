import json
import logging
from typing import Iterable, Dict, Any
from kafka import KafkaProducer, errors as kafka_errors
from .config import get_settings
import time
from math import ceil

logger = logging.getLogger(__name__)

class MeasurementProducer:
    def __init__(self):
        # Do NOT attempt to connect to Kafka at app startup; create producer lazily
        self._settings = get_settings()
        self.topic = self._settings.kafka_topic
        self.producer = None

        # connection retry params (seconds)
        self._connect_retries = int(getattr(self._settings, 'kafka_connect_retries', 3))
        self._connect_backoff = float(getattr(self._settings, 'kafka_connect_backoff', 1.0))

    def _ensure_producer(self):
        if self.producer is not None:
            return

        last_exc = None
        servers = self._settings.kafka_bootstrap_servers.split(',') if self._settings.kafka_bootstrap_servers else None
        for attempt in range(1, self._connect_retries + 1):
            try:
                self.producer = KafkaProducer(
                    bootstrap_servers=servers,
                    client_id=self._settings.kafka_client_id,
                    value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                    linger_ms=5,
                )
                logger.info("Connected to Kafka on attempt %d", attempt)
                return
            except kafka_errors.NoBrokersAvailable as e:
                last_exc = e
                wait = self._connect_backoff * (2 ** (attempt - 1))
                logger.warning("Kafka not available (attempt %d/%d), retrying in %.1fs...", attempt, self._connect_retries, wait)
                time.sleep(wait)
            except Exception as e:
                last_exc = e
                logger.exception("Unexpected error creating KafkaProducer: %s", e)
                break

        # If we reach here, we failed to create a producer
        logger.error("Failed to connect to Kafka after %d attempts: %s", self._connect_retries, last_exc)
        # leave self.producer as None

    def _send(self, message: Dict[str, Any]):
        # ensure we have a producer (may try to connect lazily)
        self._ensure_producer()
        if self.producer is None:
            # No available Kafka connection
            raise kafka_errors.NoBrokersAvailable("No Kafka brokers available to send message")

        try:
            future = self.producer.send(self.topic, value=message)
            future.add_errback(lambda exc: logger.error("Kafka send error: %s", exc))
        except Exception as e:
            logger.exception("Failed to send message to Kafka: %s", e)
            raise

    def produce_measurements(self, messages: Iterable[Dict[str, Any]]):
        count = 0
        # Try to send each message, fail fast if Kafka unavailable
        for msg in messages:
            # attempt per-message send with a small retry
            send_attempts = 3
            for attempt in range(1, send_attempts + 1):
                try:
                    self._send(msg)
                    count += 1
                    break
                except kafka_errors.NoBrokersAvailable:
                    logger.warning("Kafka unavailable when sending message (attempt %d/%d)", attempt, send_attempts)
                    if attempt == send_attempts:
                        raise
                    time.sleep(0.5 * attempt)
        if self.producer:
            try:
                self.producer.flush()
            except Exception:
                logger.exception("Error flushing producer")
        return count

producer_singleton: MeasurementProducer | None = None

def get_producer() -> MeasurementProducer:
    global producer_singleton
    if producer_singleton is None:
        producer_singleton = MeasurementProducer()
    return producer_singleton
