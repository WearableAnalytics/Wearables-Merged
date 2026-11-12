from datetime import datetime, timezone

import pytest

from app.main import ingest
from app.models import IngestPayload


@pytest.mark.asyncio
async def test_importer_preserves_writer_and_record_identity_and_binds_patient():
    stamp = datetime(2026, 11, 12, tzinfo=timezone.utc)
    payload = IngestPayload.model_validate({
        "contractVersion": "wearables-numeric/1",
        "sourceId": "writer-app", "sourcePlatform": "apple-health", "sourceName": "Watch",
        "deviceInfo": {"platform": "ios", "deviceId": "collector-1"},
        "batchInfo": {"collectionStart": stamp, "collectionEnd": stamp}, "timestamp": stamp,
        "measurements": {"instantaneous": [{"type": "HEART_RATE", "value": 72,
            "unit": "BEATS_PER_MINUTE", "timestamp": stamp,
            "sourceRecordId": "00123", "sourceDeviceId": "watch-1"}]},
    })
    import asyncio
    delivered = asyncio.Event()
    result = []
    loop = asyncio.get_running_loop()
    class Producer:
        def produce_measurements(self, messages):
            result.extend(messages)
            loop.call_soon_threadsafe(delivered.set)
    await ingest(payload, Producer(), {"caseId": "case-1", "patientId": "participant-1"})
    await asyncio.wait_for(delivered.wait(), 3)
    assert result[0]["deviceInfo"]["deviceId"] == "collector-1"
    assert result[0]["participantId"] == "participant-1"
    assert result[0]["sourceId"] == "writer-app"
    assert result[0]["measurements"]["instantaneous"][0]["sourceRecordId"] == "00123"
