import json
import logging
import time
from typing import Dict, Any, List, Optional

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

    def _ensure_producer(self, max_retries: Optional[int] = None):
        if self.producer is not None:
            return

        conf = {
            'bootstrap.servers': self._settings.kafka_bootstrap_servers,
            'client.id': self._settings.kafka_client_id,
        }

        retries = max(1, max_retries if max_retries is not None else self._connect_retries)
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                self.producer = Producer(conf)
                logger.info("Cloud Connector connected to Kafka at %s", self._settings.kafka_bootstrap_servers)
                return
            except KafkaException as e:
                last_exc = e
                if attempt < retries:
                    wait = self._connect_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Kafka not available (attempt %d/%d), retrying in %.1fs...",
                        attempt, retries, wait
                    )
                    time.sleep(wait)
        logger.error("Failed to connect to Kafka after %d attempts: %s", retries, last_exc)

    @staticmethod
    def _normalize_for_fhir_mapper(obj: Any) -> Any:
        """Keep provider metric identity and timestamp offsets unchanged."""
        if isinstance(obj, dict):
            return {key: CloudKafkaPublisher._normalize_for_fhir_mapper(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [CloudKafkaPublisher._normalize_for_fhir_mapper(value) for value in obj]
        return obj

    def _produce_one(self, payload: Dict[str, Any]) -> str:
        normalized = self._normalize_for_fhir_mapper(payload)
        # Send JSON object for fhir-mapper-validator
        payload_bytes = json.dumps(normalized, default=str).encode("utf-8")
        patient_id = (
            payload.get("participantId")
            or payload.get("deviceInfo", {}).get("deviceId", "unknown")
        )
        self.producer.produce(
            topic=self.topic,
            key=patient_id.encode("utf-8"),
            value=payload_bytes,
        )
        return patient_id

    def publish_payload(
        self,
        payload: Dict[str, Any],
        flush_timeout: float = 5.0,
        max_connect_retries: Optional[int] = None,
    ) -> bool:
        return (
            self.publish_batch(
                [payload], flush_timeout=flush_timeout, max_connect_retries=max_connect_retries
            )
            == 1
        )

    def publish_batch(
        self,
        payloads: List[Dict[str, Any]],
        flush_timeout: float = 5.0,
        max_connect_retries: Optional[int] = None,
    ) -> int:
        if not payloads:
            return 0
        self._ensure_producer(max_retries=max_connect_retries)
        if not self.producer:
            logger.error("Kafka producer not initialized, dropping %d message(s)", len(payloads))
            return 0

        try:
            patient_ids = [self._produce_one(payload) for payload in payloads]
            self.producer.poll(0)
            remaining = self.producer.flush(timeout=flush_timeout)
            if isinstance(remaining, int) and remaining > 0:
                delivered = max(0, len(payloads) - remaining)
                logger.error(
                    "Kafka flush timed out (%d/%d message(s) still queued)",
                    remaining,
                    len(payloads),
                )
                return delivered
            logger.info(
                "Successfully produced %d cloud telemetry batch(es) (%s) to %s",
                len(payloads),
                ", ".join(set(patient_ids)),
                self.topic,
            )
            return len(payloads)
        except Exception as e:
            logger.error("Failed to publish batch to Kafka: %s", e)
            return 0


_publisher_instance = None

def get_publisher() -> CloudKafkaPublisher:
    global _publisher_instance
    if _publisher_instance is None:
        _publisher_instance = CloudKafkaPublisher()
    return _publisher_instance
