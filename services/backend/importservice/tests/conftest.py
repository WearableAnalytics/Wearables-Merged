import base64
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from psycopg import AsyncConnection

from app.config import Settings
from app.crypto import ArchiveCipher
from app.repository import Repository


@pytest.fixture
def settings():
    return Settings(
        database_url=os.getenv("INGEST_TEST_DATABASE_URL", "postgresql://unused/ingestion_test"),
        jwt_secret="test-only-jwt-secret-" + "x" * 32,
        archive_key_b64=base64.b64encode(b"a" * 32).decode(),
        signing_key_b64=base64.b64encode(b"s" * 32).decode(),
    )


@pytest.fixture
def claims():
    return {"caseId": str(uuid4()), "patientId": str(uuid4())}


@pytest.fixture
def batch():
    return {
        "contractVersion": "wearables-numeric/1",
        "sourceId": "provider-account-7",
        "deviceInfo": {"platform": "iOS", "deviceId": "phone-installation-9", "authorizationToken": "not-a-real-token"},
        "batchInfo": {"collectionStart": "2026-10-30T10:00:00Z", "collectionEnd": "2026-10-30T11:00:00Z"},
        "sourceName": "synthetic-test",
        "sourcePlatform": "test-provider",
        "timestamp": "2026-10-30T11:00:00Z",
        "measurements": {
            "instantaneous": [
                {
                    "sourceRecordId": "reading-42",
                    "type": "HEART_RATE",
                    "value": 72.12345678901234,
                    "unit": "BEATS_PER_MINUTE",
                    "timestamp": "2026-10-30T10:15:00Z",
                }
            ],
            "cumulative": [],
            "duration": [],
        },
    }


@pytest_asyncio.fixture
async def repository(settings):
    if not os.getenv("INGEST_TEST_DATABASE_URL"):
        pytest.skip("Set INGEST_TEST_DATABASE_URL to the isolated ingestion_test database")
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as conn:
        database = await (await conn.execute("SELECT current_database()")).fetchone()
        if database[0] != "ingestion_test":
            raise RuntimeError("Refusing to reset any database except ingestion_test")
        await conn.execute("DROP SCHEMA IF EXISTS ingestion CASCADE")
        await conn.execute((Path(__file__).parents[1] / "migrations/001_ingestion.sql").read_text())
    repo = Repository(settings, ArchiveCipher(settings))
    await repo.open()
    try:
        yield repo
    finally:
        await repo.close()


def encoded(batch):
    return json.dumps(batch).encode()
