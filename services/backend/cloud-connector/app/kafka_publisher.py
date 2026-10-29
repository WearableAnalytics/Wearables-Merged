import json
import logging
import time
from typing import Dict, Any, Optional

from confluent_kafka import Producer, KafkaException
from .config import get_settings

logger = logging.getLogger(__name__)


class CloudKafkaPublisher:
    """Publishes normalized IngestPayloads from cloud providers to Kafka 'wearables-raw'"""

    def __init__(self):
        self._settings = get_settings()
        self.topic = self._settings.kafka_topic
        self.producer: Optional[Producer] = None
        self._connect_retries = self._settings.kafka_connect_retries
        self._connect_backoff = self._settings.kafka_connect_backoff

    def _ensure_producer(self):
        if self.producer is not None:
            return

        conf = {
            'bootstrap.servers': self._settings.kafka_bootstrap_servers,
            'client.id': self._settings.kafka_client_id,
        }

        last_exc = None
        for attempt in range(1, self._connect_retries + 1):
            try:
                self.producer = Producer(conf)
                logger.info("Cloud Connector connected to Kafka at %s", self._settings.kafka_bootstrap_servers)
                return
            except KafkaException as e:
                last_exc = e
                wait = self._connect_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "Kafka not available (attempt %d/%d), retrying in %.1fs...",
                    attempt, self._connect_retries, wait
                )
                time.sleep(wait)
        logger.error("Failed to connect to Kafka after %d attempts: %s", self._connect_retries, last_exc)

    def publish_payload(self, payload: Dict[str, Any]) -> bool:
        self._ensure_producer()
        if not self.producer:
            logger.error("Kafka producer not initialized, dropping message")
            return False

        try:
            # Wrap in list as expected by fhir-mapper-validator
            msg_data = [payload] if not isinstance(payload, list) else payload
            payload_bytes = json.dumps(msg_data, default=str).encode('utf-8')
            
            patient_id = payload.get("deviceInfo", {}).get("deviceId", "unknown")
            key = patient_id.encode('utf-8')

            self.producer.produce(
                topic=self.topic,
                key=key,
                value=payload_bytes,
            )
            self.producer.poll(0)
            self.producer.flush(timeout=5.0)
            logger.info("Successfully produced cloud telemetry for patient %s to %s", patient_id, self.topic)
            return True
        except Exception as e:
            logger.error("Failed to publish message to Kafka: %s", e)
            return False


_publisher_instance = None

def get_publisher() -> CloudKafkaPublisher:
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = CloudKafkaPublisher()
    return _publisher_instance
