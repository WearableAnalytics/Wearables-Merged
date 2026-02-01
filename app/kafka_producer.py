import json
import logging
import time
from typing import Iterable, Dict, Any

from confluent_kafka import Producer
from confluent_kafka import KafkaException

from .config import get_settings

logger = logging.getLogger(__name__)


class MeasurementProducer:
    def __init__(self):
        self._settings = get_settings()
        self.topic = self._settings.kafka_topic
        self.producer = None

        self._connect_retries = int(getattr(self._settings, 'kafka_connect_retries', 3))
        self._connect_backoff = float(getattr(self._settings, 'kafka_connect_backoff', 1.0))

    def _make_config(self) -> dict:
        servers = self._settings.kafka_bootstrap_servers
        return {
            'bootstrap.servers': servers,
            'client.id': self._settings.kafka_client_id,
            'linger.ms': self._settings.kafka_linger_ms,
            'batch.size': self._settings.kafka_batch_size,
            'queue.buffering.max.kbytes': self._settings.kafka_buffer_memory // 1024,
        }

    def _ensure_producer(self):
        if self.producer is not None:
            return

        last_exc = None
        for attempt in range(1, self._connect_retries + 1):
            try:
                self.producer = Producer(self._make_config())
                logger.info("Connected to Kafka on attempt %d", attempt)
                return
            except KafkaException as e:
                last_exc = e
                wait = self._connect_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Kafka not available (attempt %d/%d), retrying in %.1fs...",
                    attempt, self._connect_retries, wait
                )
                time.sleep(wait)
            except Exception as e:
                last_exc = e
                logger.exception("Unexpected error creating Kafka Producer: %s", e)
                break

        logger.error(
            "Failed to connect to Kafka after %d attempts: %s",
            self._connect_retries, last_exc
        )

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Kafka delivery failed: %s", err)

    def _send(self, message: Dict[str, Any]):
        self._ensure_producer()
        if self.producer is None:
            raise KafkaException("No Kafka brokers available to send message")

        value = json.dumps(message).encode('utf-8')
        self.producer.produce(
            self.topic,
            value=value,
            callback=self._delivery_callback,
        )

    def produce_measurements(self, messages: Iterable[Dict[str, Any]]):
        count = 0
        send_attempts = 3
        for msg in messages:
            for attempt in range(1, send_attempts + 1):
                try:
                    self._send(msg)
                    count += 1
                    break
                except KafkaException:
                    logger.warning(
                        "Kafka unavailable when sending message (attempt %d/%d)",
                        attempt, send_attempts
                    )
                    if attempt == send_attempts:
                        raise
                    time.sleep(0.05 * attempt)
        return count


producer_singleton: MeasurementProducer | None = None


def get_producer() -> MeasurementProducer:
    global producer_singleton
    if producer_singleton is None:
        producer_singleton = MeasurementProducer()
    return producer_singleton
