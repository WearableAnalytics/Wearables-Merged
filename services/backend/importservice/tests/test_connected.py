"""Real Kafka -> Java/HAPI -> journal -> Kafka -> Telegraf -> InfluxDB test.

Requires the isolated test compose stack and a freshly packaged mapper JAR.
Every record in this test is synthetic; it does not connect to a phone or cloud.
"""

import asyncio
import csv
import io
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from authlib.jose import JsonWebToken

from app import security
from app.main import create_app
from app.pipeline import KafkaGateway
from app.worker import Worker

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("INGEST_TEST_STACK") != "1", reason="Set INGEST_TEST_STACK=1 for the real stack"),
]


async def until_receipt(client, upload_id, predicate):
    deadline = time.monotonic() + 120
    last = None
    while time.monotonic() < deadline:
        response = await client.get("/ingest/" + upload_id)
        assert response.status_code == 200
        last = response.json()
        if predicate(last):
            return last
        await asyncio.sleep(0.2)
    raise AssertionError("Receipt did not reach expected state: " + json.dumps(last))


async def test_real_pipeline_preserves_value_time_identity_and_partial_failure(repository, batch, claims, monkeypatch):
    settings = repository.settings
    settings.kafka_bootstrap_servers = "127.0.0.1:59092"
    settings.influxdb_url = "http://127.0.0.1:18199"
    settings.influxdb_org = "wearables_test"
    settings.influxdb_bucket = "ingestion_test"
    settings.influxdb_token = os.environ["INGEST_TEST_INFLUX_TOKEN"]
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    mapper = Path(__file__).resolve().parents[2] / "fhir-mapper-validator"
    jar = mapper / "target/mapper-validator-1.0-SNAPSHOT-shaded.jar"
    assert jar.is_file(), "Package the mapper before running this test"
    log_path = Path(os.environ["INGEST_TEST_LOG_DIR"]) / "connected-mapper.log"
    env = dict(
        os.environ,
        INGEST_SIGNING_KEY=settings.signing_key_b64,
        MAPPING_YAML_PATH=str(mapper / "config/mapping-2026-01-28.yaml"),
        KAFKA_BROKER_ENV_VAR=settings.kafka_bootstrap_servers,
        APP_ID="reliable-ingestion-test-" + str(uuid4()),
        VALIDATION_FREQUENCY="0",
    )
    app = create_app(settings)
    app.state.repository = repository
    token = (
        JsonWebToken(["HS256"])
        .encode(
            {"alg": "HS256"},
            {
                "iss": settings.registration_issuer,
                "type": "case-verification",
                "exp": int(time.time()) + 600,
                "sub": claims["caseId"],
                **claims,
            },
            settings.jwt_secret,
        )
        .decode()
    )
    gateway = KafkaGateway(settings)
    worker = Worker(repository, gateway, settings)
    task = None
    with log_path.open("w") as log:
        process = subprocess.Popen(
            ["java", "-Xmx1024m", "-jar", str(jar)], cwd=mapper, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://local-test",
                headers={"Authorization": "Bearer " + token},
            ) as client:
                response = await client.post("/ingest", json=batch)
                assert response.status_code == 202
                first = response.json()
                assert first["brokerConfirmedCount"] == first["normalizedCount"] == first["storedConfirmedCount"] == 0
                # Accepted work is in PostgreSQL before a delivery worker even runs.
                task = asyncio.create_task(worker.run())
                completed = await until_receipt(client, first["acceptanceId"], lambda r: r["storedConfirmedCount"] == 1)
                assert completed["normalizedCount"] == 1 and completed["rejectedCount"] == 0
                assert process.poll() is None, "Mapper stopped unexpectedly"

                again = await client.post("/ingest", json=batch)
                assert again.json()["acceptanceId"] == first["acceptanceId"] and again.json()["replayed"]
                batch["timestamp"] = "2026-10-30T12:00:00Z"
                batch["deviceInfo"]["deviceId"] = "replacement-phone"
                changed_delivery = (await client.post("/ingest", json=batch)).json()
                assert changed_delivery["acceptanceId"] != first["acceptanceId"]
                assert changed_delivery["storedConfirmedCount"] == 1

                async with repository.pool.connection() as conn:
                    rows = await (await conn.execute("SELECT * FROM ingestion.records")).fetchall()
                    assert len(rows) == 1
                    record_id = str(rows[0]["id"])
                query = (
                    'from(bucket: "ingestion_test") |> range(start: 2026-10-30T10:00:00Z, stop: 2026-10-30T11:00:00Z) '
                    '|> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value") '
                    f'|> filter(fn: (r) => r.ingestion_record_id == "{record_id}")'
                )
                async with httpx.AsyncClient() as influx:
                    result = await influx.post(
                        settings.influxdb_url + "/api/v2/query",
                        params={"org": settings.influxdb_org},
                        headers={"Authorization": "Token " + settings.influxdb_token, "Accept": "application/csv"},
                        json={"query": query},
                    )
                    assert result.status_code == 200
                    points = list(csv.DictReader(line for line in io.StringIO(result.text) if not line.startswith("#")))
                    assert len(points) == 1, "A retried source record created another point"
                    assert float(points[0]["value"]) == 72.12345678901234
                    assert points[0]["_time"] == "2026-10-30T10:15:00Z"
                    assert points[0]["device-id"] == claims["patientId"]
                    assert points[0]["source-device-id"] == "phone-installation-9"
                    assert points[0]["ingestion_raw_sha256"] == first["rawSha256"]

                batch["measurements"]["instantaneous"] = [
                    {
                        "sourceRecordId": "reading-43",
                        "type": "HEART_RATE",
                        "value": 74,
                        "unit": "BEATS_PER_MINUTE",
                        "timestamp": "2026-10-30T10:16:00Z",
                    },
                    {
                        "sourceRecordId": "bad-reading",
                        "type": "UNMAPPED_TEST_METRIC",
                        "value": 1,
                        "unit": "COUNT",
                        "timestamp": "2026-10-30T10:16:00Z",
                    },
                ]
                partial = await client.post("/ingest", json=batch)
                assert partial.status_code == 202
                receipt = await until_receipt(
                    client,
                    partial.json()["acceptanceId"],
                    lambda r: r["storedConfirmedCount"] == 1 and r["rejectedCount"] == 1,
                )
                assert receipt["recordCount"] == 2 and receipt["normalizedCount"] == 1
        finally:
            if task:
                worker.stop.set()
                await task
            else:
                await worker.http.aclose()
            await gateway.close()
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
