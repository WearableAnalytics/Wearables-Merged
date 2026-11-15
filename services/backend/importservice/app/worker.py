"""Replay from the durable journal; never treat publication as storage proof."""

import asyncio
import csv
import io
import json
import logging
import time

import httpx

from .contracts import RESULT_KIND
from .crypto import verify
from .pipeline import ProcessingResult

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, repository, gateway, settings):
        self.repo, self.gateway, self.settings = repository, gateway, settings
        self.key = settings.decode_key(settings.signing_key_b64)
        self.stop = asyncio.Event()
        self.http = httpx.AsyncClient(timeout=3, follow_redirects=False)

    async def run(self):
        tasks = [asyncio.create_task(fn()) for fn in (self.deliver, self.results, self.observe)]
        try:
            await self.stop.wait()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self.http.aclose()

    async def deliver(self):
        next_sweep = 0
        while True:
            try:
                if time.monotonic() >= next_sweep:
                    await self.repo.recover_stalled()
                    next_sweep = time.monotonic() + 15
                job = await self.repo.claim()
                if job is None:
                    await asyncio.sleep(0.2)
                    continue
                broker = None
                try:
                    broker = await self.gateway.publish(job["topic"], job["record_id"], job["wire"])
                except Exception:
                    logger.warning("ingestion_broker_delivery_failed")
                await self.repo.finish(job, broker)
            except Exception:
                logger.warning("ingestion_delivery_worker_unavailable")
                await asyncio.sleep(1)

    async def results(self):
        message = None
        while True:
            try:
                if message is None:
                    message = await self.gateway.poll()
                if message is None or message.error():
                    message = None
                    await asyncio.sleep(0.05)
                    continue
                try:
                    result = ProcessingResult.model_validate(verify(message.value(), self.key, RESULT_KIND))
                except (ValueError, KeyError, TypeError):
                    # Poison messages must not stop this consumer. Log no health payload.
                    logger.warning("ingestion_untrusted_result")
                else:
                    await self.repo.apply_result(result.model_dump(mode="json", exclude_none=True))
                # Commit only after the database transaction, or deliberate rejection.
                try:
                    await self.gateway.commit(message)
                finally:
                    # A failed commit after a database commit can be replayed safely.
                    message = None
            except Exception:
                logger.warning("ingestion_result_worker_unavailable")
                await asyncio.sleep(1)

    async def storage_observed(self, row):
        timestamp = row["timestamp_ns"]
        query = (
            f"from(bucket: {json.dumps(self.settings.influxdb_bucket)}) "
            f"|> range(start: time(v: {timestamp}), stop: time(v: {timestamp + 1})) "
            '|> filter(fn: (r) => r._field == "ingestion_output_sha256" '
            f'and r._value == "{row["output_sha256"]}") |> limit(n: 1)'
        )
        async with self.http.stream(
            "POST",
            self.settings.influxdb_url.rstrip("/") + "/api/v2/query",
            params={"org": self.settings.influxdb_org},
            headers={"Authorization": "Token " + self.settings.influxdb_token, "Accept": "application/csv"},
            json={"query": query},
        ) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > 64_000:
                    raise ValueError("Storage observation response is too large")
        lines = (line for line in io.StringIO(body.decode()) if not line.startswith("#"))
        return any(record.get("_value") == row["output_sha256"] for record in csv.DictReader(lines))

    async def observe(self):
        while True:
            try:
                if self.settings.influxdb_token:
                    for row in await self.repo.unconfirmed():
                        if await self.storage_observed(row):
                            await self.repo.confirm_storage(row)
            except Exception:
                logger.warning("ingestion_storage_observation_unavailable")
            await asyncio.sleep(5)
