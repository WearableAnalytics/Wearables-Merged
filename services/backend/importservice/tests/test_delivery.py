import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.contracts import RESULT_KIND
from app.crypto import sign
from app.pipeline import KafkaGateway
from app.worker import Worker


def test_producer_waits_for_the_delivery_callback(settings):
    class Producer:
        polls = 0
        callback = None

        def produce(self, topic, key, value, on_delivery):
            self.callback = on_delivery

        def poll(self, _timeout):
            self.polls += 1
            if self.polls == 3:
                self.callback(None, SimpleNamespace(partition=lambda: 2, offset=lambda: 42))

    gateway = KafkaGateway.__new__(KafkaGateway)
    gateway.settings, gateway.producer = settings, Producer()
    assert gateway._publish("test", "record", b"message") == (2, 42)
    assert gateway.producer.polls == 3


def test_failed_broker_callback_is_not_a_receipt(settings):
    class Producer:
        callback = None

        def produce(self, topic, key, value, on_delivery):
            self.callback = on_delivery

        def poll(self, _timeout):
            self.callback("delivery failed", None)

    gateway = KafkaGateway.__new__(KafkaGateway)
    gateway.settings, gateway.producer = settings, Producer()
    with pytest.raises(TimeoutError):
        gateway._publish("test", "record", b"message")


async def test_database_failure_does_not_skip_a_result_by_committing_a_later_offset(settings):
    key = settings.decode_key(settings.signing_key_b64)
    bodies = [
        {
            "recordId": str(uuid4()),
            "generation": 1,
            "inputSha256": "a" * 64,
            "mapperVersion": "b" * 64,
            "status": "rejected",
            "errorCode": "mapping_failed",
        }
        for _ in range(2)
    ]
    messages = [
        SimpleNamespace(error=lambda: None, value=lambda body=body: sign(body, key, RESULT_KIND)) for body in bodies
    ]
    commits, applied = [], []

    async def poll():
        return messages.pop(0) if messages else None

    async def commit(message):
        commits.append(message)

    async def apply(body):
        applied.append(body["recordId"])
        if len(applied) == 1:
            raise OSError("simulated database interruption")

    worker = Worker(SimpleNamespace(apply_result=apply), SimpleNamespace(poll=poll, commit=commit), settings)
    task = asyncio.create_task(worker.results())
    try:
        async with asyncio.timeout(4):
            while len(commits) < 2:
                await asyncio.sleep(0.01)
        assert applied == [bodies[0]["recordId"], bodies[0]["recordId"], bodies[1]["recordId"]]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await worker.http.aclose()
