"""Black-box check of the built images, migration command and rendered mapping.

Only runs against the named disposable local compose stack, never a remote engine.
"""

import asyncio
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import yaml
from authlib.jose import JsonWebToken
from psycopg.conninfo import conninfo_to_dict, make_conninfo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("INGEST_TEST_IMAGES") != "1", reason="Set INGEST_TEST_IMAGES=1 for built-image checks"
    ),
]
ROOT = Path(__file__).resolve().parents[4]
NETWORK = "ingestion-deployment-test_default"


def docker(*arguments, check=True):
    return subprocess.run(["docker", *arguments], capture_output=True, text=True, check=check).stdout.strip()


def rendered(chart):
    helm = os.getenv("HELM_BINARY") or shutil.which("helm")
    result = subprocess.run(
        [helm, "template", "image-test", str(ROOT / "gitops/apps/services" / chart), "--set", "image.tag=local"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def env_file(directory, name, values):
    path = directory / name
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    path.chmod(0o600)
    return str(path)


async def wait_for(client, path, predicate, seconds=120):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            response = await client.get(path)
            if response.status_code == 200 and predicate(response.json()):
                return response.json()
        except httpx.HTTPError:
            pass
        await asyncio.sleep(0.3)
    raise AssertionError("Built-image endpoint did not reach the expected state: " + path)


async def test_built_images_retain_upload_during_kafka_outage_then_observe_storage(repository, batch, claims):
    assert docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}").startswith("unix://")
    assert (
        docker("network", "inspect", "--format", '{{index .Labels "com.docker.compose.project"}}', NETWORK)
        == "ingestion-deployment-test"
    )
    settings = repository.settings
    log_dir = Path(os.environ["INGEST_TEST_LOG_DIR"])
    importer_image = "wearables-ingestion-deployment-importer:local"
    mapper_image = "wearables-ingestion-deployment-mapper:local"
    suffix = uuid4().hex[:10]
    importer, mapper = "ingestion-importer-" + suffix, "ingestion-mapper-" + suffix
    configs = rendered("importservice")
    runtime = next(d["data"] for d in configs if d["kind"] == "ConfigMap")
    mapper_docs = rendered("mapper-validator")
    mapper_env = next(d["data"] for d in mapper_docs if d["metadata"]["name"] == "mapper-app-env-config")
    mapping = next(d["data"]["mapping.yaml"] for d in mapper_docs if d["metadata"]["name"] == "mapping-config")
    runtime_role = conninfo_to_dict(settings.database_url)["user"]
    admin_headers = {"Authorization": "Token " + os.environ["INGEST_TEST_INFLUX_TOKEN"]}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:18199", headers=admin_headers) as influx:
        orgs = (await influx.get("/api/v2/orgs", params={"org": "wearables_test"})).json()["orgs"]
        org_id = orgs[0]["id"]
        buckets = (await influx.get("/api/v2/buckets", params={"orgID": org_id, "name": "ingestion_test"})).json()[
            "buckets"
        ]
        authorization = await influx.post(
            "/api/v2/authorizations",
            json={
                "orgID": org_id,
                "permissions": [
                    {"action": "read", "resource": {"type": "buckets", "id": buckets[0]["id"], "orgID": org_id}}
                ],
            },
        )
        assert authorization.status_code == 201
        read_auth = authorization.json()
        with tempfile.TemporaryDirectory(prefix="images-", dir=log_dir) as temporary:
            directory = Path(temporary)
            migration_env = env_file(
                directory,
                "migration.env",
                {
                    "INGEST_DATABASE_URL": make_conninfo(
                        os.environ["INGEST_TEST_DATABASE_URL"], host="postgres", port=5432
                    ),
                    "INGEST_RUNTIME_ROLE": runtime_role,
                },
            )
            runtime.update(
                {
                    "INGEST_DATABASE_URL": make_conninfo(settings.database_url, host="postgres", port=5432),
                    "JWT_SECRET": settings.jwt_secret,
                    "INGEST_ARCHIVE_KEY": settings.archive_key_b64,
                    "INGEST_SIGNING_KEY": settings.signing_key_b64,
                    "INFLUXDB_TOKEN": read_auth["token"],
                    "INFLUXDB_URL": "http://influx:8086",
                    "INFLUXDB_ORG": "wearables_test",
                    "INFLUXDB_BUCKET": "ingestion_test",
                    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
                    "UVICORN_WORKERS": "1",
                    "KAFKA_RESULTS_GROUP": "ingestion-image-test-" + suffix,
                }
            )
            mapper_env.update(
                {
                    "KAFKA_BROKER_ENV_VAR": "kafka:9092",
                    "APP_ID": "ingestion-image-mapper-" + suffix,
                    "INGEST_SIGNING_KEY": settings.signing_key_b64,
                    "JAVA_TOOL_OPTIONS": "-Xmx768m",
                }
            )
            runtime_path = env_file(directory, "runtime.env", runtime)
            mapper_path = env_file(directory, "mapper.env", mapper_env)
            mapping_path = directory / "mapping.yaml"
            mapping_path.write_text(mapping)
            token = (
                JsonWebToken(["HS256"])
                .encode(
                    {"alg": "HS256"},
                    {
                        "iss": runtime["JWT_ISSUER"],
                        "type": "case-verification",
                        "exp": int(time.time()) + 600,
                        "sub": claims["caseId"],
                        **claims,
                    },
                    settings.jwt_secret,
                )
                .decode()
            )
            try:
                for _ in range(2):
                    docker(
                        "run",
                        "--rm",
                        "--network",
                        NETWORK,
                        "--env-file",
                        migration_env,
                        importer_image,
                        "python",
                        "-m",
                        "app.migrate",
                    )
                docker(
                    "run",
                    "-d",
                    "--name",
                    mapper,
                    "--network",
                    NETWORK,
                    "--env-file",
                    mapper_path,
                    "-v",
                    str(mapping_path) + ":/config/mapping.yaml:ro",
                    mapper_image,
                )
                docker(
                    "run",
                    "-d",
                    "--name",
                    importer,
                    "--network",
                    NETWORK,
                    "--env-file",
                    runtime_path,
                    "-p",
                    "127.0.0.1::8000",
                    importer_image,
                )
                address = docker("port", importer, "8000/tcp")
                async with httpx.AsyncClient(
                    base_url="http://" + address, headers={"Authorization": "Bearer " + token}
                ) as client:
                    await wait_for(client, "/ready", lambda r: r["acceptanceGuarantee"] == "postgres-archive")
                    raw = json.dumps(batch).encode()
                    headers = {"Content-Type": "application/json", "Idempotency-Key": "image-first-" + suffix}
                    response = await client.post("/ingest", content=raw, headers=headers)
                    assert response.status_code == 202
                    receipt = response.json()
                    assert receipt["rawSha256"] == hashlib.sha256(raw).hexdigest()
                    assert receipt["readingCount"] == 1
                    await wait_for(
                        client,
                        "/ingest/" + receipt["acceptanceId"],
                        lambda r: r["processingState"] == "storage-observed",
                    )
                    repeated = await client.post("/ingest", content=raw, headers=headers)
                    assert repeated.status_code == 202 and repeated.json()["replayed"]
                    assert repeated.json()["acceptanceId"] == receipt["acceptanceId"]
                    assert (await client.post("/ingest", content=raw + b" ", headers=headers)).status_code == 409
                    docker("pause", "ingestion-deployment-test-kafka-1")
                    try:
                        delayed = copy.deepcopy(batch)
                        delayed["measurements"]["instantaneous"][0].update(
                            {
                                "sourceRecordId": "image-outage-" + suffix,
                                "timestamp": "2026-10-30T10:17:00Z",
                            }
                        )
                        accepted = await client.post("/ingest", json=delayed)
                        assert accepted.status_code == 202
                        queued = accepted.json()
                        assert queued["status"] == "archived" and queued["brokerConfirmedCount"] == 0
                        assert (await client.get("/ready")).status_code == 200
                    finally:
                        docker("unpause", "ingestion-deployment-test-kafka-1")
                    await wait_for(
                        client,
                        "/ingest/" + queued["acceptanceId"],
                        lambda r: r["processingState"] == "storage-observed",
                    )
            finally:
                for name in [importer, mapper]:
                    output = docker("logs", name, check=False)
                    (log_dir / (name + ".log")).write_text(output)
                    docker("rm", "-f", name, check=False)
                await influx.delete("/api/v2/authorizations/" + read_auth["id"])
