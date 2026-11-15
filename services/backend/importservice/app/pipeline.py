"""Bounded Kafka delivery with broker callbacks, and authenticated mapper results."""

import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from uuid import UUID

from confluent_kafka import Consumer, Producer
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recordId: UUID
    generation: int = Field(ge=1, le=1_000_000)
    inputSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    mapperVersion: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["normalized", "rejected"]
    lineProtocol: str | None = Field(default=None, max_length=32_000)
    errorCode: Literal["mapping_failed", "fhir_validation_failed", "timestamp_failed", "unit_mismatch"] | None = None

    @model_validator(mode="after")
    def check_outcome(self):
        if self.status == "normalized" and (not self.lineProtocol or self.errorCode):
            raise ValueError("A normalized result needs line protocol only")
        if self.status == "rejected" and (not self.errorCode or self.lineProtocol):
            raise ValueError("A rejected result needs an error code only")
        return self


class KafkaGateway:
    def __init__(self, settings):
        self.settings = settings
        common = {"bootstrap.servers": settings.kafka_bootstrap_servers, **json.loads(settings.kafka_security_json)}
        self.producer = Producer(
            {
                **common,
                "client.id": settings.kafka_client_id,
                "enable.idempotence": True,
                "acks": "all",
                "linger.ms": 5,
                "message.timeout.ms": settings.delivery_timeout_ms,
                "request.timeout.ms": min(3000, settings.delivery_timeout_ms),
                "queue.buffering.max.messages": 128,
                "queue.buffering.max.kbytes": 8192,
            }
        )
        self.consumer = Consumer(
            {
                **common,
                "group.id": settings.kafka_results_group,
                "enable.auto.commit": False,
                "enable.auto.offset.store": False,
                "auto.offset.reset": "earliest",
                "fetch.message.max.bytes": 2_000_000,
            }
        )
        self.reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingestion-results")
        self.writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ingestion-publish")
        self.consumer.subscribe([settings.kafka_results_topic])

    def _publish(self, topic, key, wire):
        result = []

        def delivered(error, message):
            result.append(None if error else (message.partition(), message.offset()))

        self.producer.produce(topic, key=str(key).encode(), value=wire, on_delivery=delivered)
        deadline = time.monotonic() + self.settings.delivery_timeout_ms / 1000 + 0.5
        while not result and time.monotonic() < deadline:
            self.producer.poll(0.1)
        if not result or result[0] is None:
            raise TimeoutError("Kafka did not confirm delivery")
        return result[0]

    async def publish(self, topic, key, wire):
        return await asyncio.get_running_loop().run_in_executor(self.writer, self._publish, topic, key, wire)

    async def poll(self):
        return await asyncio.get_running_loop().run_in_executor(self.reader, self.consumer.poll, 0.1)

    async def commit(self, message):
        await asyncio.get_running_loop().run_in_executor(
            self.reader, lambda: self.consumer.commit(message=message, asynchronous=False)
        )

    async def close(self):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.reader, self.consumer.close)
        await loop.run_in_executor(self.writer, self.producer.flush, self.settings.delivery_timeout_ms / 1000)
        self.reader.shutdown(wait=False)
        self.writer.shutdown(wait=False)
