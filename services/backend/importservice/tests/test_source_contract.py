import json
from threading import Event
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main


def test_importer_preserves_writer_and_record_identity_and_binds_patient():
    stamp = "2026-11-12T00:00:00Z"
    payload = {
        "contractVersion": "wearables-numeric/1",
        "sourceId": "writer-app", "sourcePlatform": "apple-health", "sourceName": "Watch",
        "deviceInfo": {"platform": "ios", "deviceId": "collector-1"},
        "batchInfo": {"collectionStart": stamp, "collectionEnd": stamp}, "timestamp": stamp,
        "measurements": {"instantaneous": [{"type": "HEART_RATE", "value": 72,
            "unit": "BEATS_PER_MINUTE", "timestamp": stamp,
            "sourceRecordId": "00123", "sourceDeviceId": "watch-1"}]},
    }
    claims = {"caseId": str(uuid4()), "patientId": str(uuid4())}
    delivered = Event()
    result = []

    class Producer:
        def produce_measurements(self, messages):
            result.extend(messages)
            delivered.set()

    class Archive:
        async def accept(self, upload):
            result.extend(json.loads(record["payload"]) for record in upload["records"])
            delivered.set()
            return upload["id"], False

        async def receipt(self, upload_id, _claims):
            return {"acceptanceId": upload_id, "status": "archived"}

    # Exercise the public HTTP boundary in both the current importer and the
    # separately reviewed receipt-backed importer when the branches are combined.
    application = main.create_app() if hasattr(main, "create_app") else main.app
    application.dependency_overrides[main.verify_case_verification_token] = lambda: claims
    if hasattr(main, "get_repository"):
        application.dependency_overrides[main.get_repository] = lambda: Archive()
    else:
        application.dependency_overrides[main.get_producer] = lambda: Producer()
    try:
        response = TestClient(application).post("/ingest", json=payload)
        assert response.status_code == (202 if hasattr(main, "get_repository") else 200)
        assert delivered.wait(3), "Importer did not forward the accepted reading"
    finally:
        application.dependency_overrides.clear()
    assert result[0]["deviceInfo"]["deviceId"] == "collector-1"
    assert result[0]["participantId"] == claims["patientId"]
    assert result[0]["caseId"] == claims["caseId"]
    assert result[0]["sourceId"] == "writer-app"
    point = result[0]["measurements"]["instantaneous"][0]
    assert point["sourceRecordId"] == "00123"
    assert point["sourceDeviceId"] == "watch-1"
