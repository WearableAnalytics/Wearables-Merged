import copy
import json

import pytest
from cryptography.exceptions import InvalidTag

from app.contracts import INPUT_KIND, RESULT_KIND, parse_upload
from app.crypto import ArchiveCipher, digest, sign, verify


def test_archive_is_authenticated_and_bound_to_its_row(settings):
    cipher = ArchiveCipher(settings)
    key_id, blob = cipher.seal(b"original health data", "upload:one")
    assert b"original health data" not in blob
    assert cipher.open(key_id, blob, "upload:one") == b"original health data"
    with pytest.raises(InvalidTag):
        cipher.open(key_id, blob, "upload:two")
    with pytest.raises(InvalidTag):
        cipher.open(key_id, blob[:-1] + bytes([blob[-1] ^ 1]), "upload:one")


def test_pipeline_signature_cannot_be_changed_or_used_as_a_result(settings):
    key = settings.decode_key(settings.signing_key_b64)
    wire = sign({"value": 72}, key, INPUT_KIND)
    assert verify(wire, key, INPUT_KIND) == {"value": 72}
    envelope = json.loads(wire)
    envelope["payload"] = envelope["payload"][:-2] + "AA"
    with pytest.raises(ValueError):
        verify(json.dumps(envelope).encode(), key, INPUT_KIND)
    with pytest.raises(ValueError):
        verify(wire, key, RESULT_KIND)


def test_preserves_original_hash_binds_person_and_retains_sender(batch, claims, settings):
    batch["participantId"] = "forged-person"
    raw = json.dumps(batch, indent=3).encode()
    upload = parse_upload(raw, claims, None, settings)
    data = json.loads(upload["records"][0]["payload"])
    assert upload["raw"] == raw and upload["raw_sha256"] == digest(raw)
    assert data["participantId"] == claims["patientId"]
    assert data["caseId"] == claims["caseId"]
    assert data["deviceInfo"]["deviceId"] == "phone-installation-9"
    assert "authorizationToken" not in data["deviceInfo"]
    assert data["measurements"]["instantaneous"][0]["value"] == 72.12345678901234


def test_source_identity_survives_a_new_upload_time_and_sender(batch, claims, settings):
    first = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    batch["timestamp"] = "2026-10-30T12:00:00Z"
    batch["deviceInfo"]["deviceId"] = "replacement-phone"
    second = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    assert first["raw_sha256"] != second["raw_sha256"]
    assert first["records"][0]["record_key"] == second["records"][0]["record_key"]
    assert first["records"][0]["input_sha256"] == second["records"][0]["input_sha256"]


def test_offsets_identify_the_same_source_instant(batch, claims, settings):
    first = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    batch["measurements"]["instantaneous"][0]["timestamp"] = "2026-10-30T12:15:00+02:00"
    second = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    assert first["records"][0]["input_sha256"] == second["records"][0]["input_sha256"]


def test_legacy_has_only_upload_identity_and_does_not_invent_source_ids(batch, claims, settings):
    batch.pop("contractVersion")
    batch.pop("sourceId")
    batch["measurements"]["instantaneous"][0].pop("sourceRecordId")
    first = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    assert first["records"][0]["identity_mode"] == "upload-only"
    batch["timestamp"] = "2026-10-30T12:00:00Z"
    second = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    assert first["records"][0]["record_key"] != second["records"][0]["record_key"]


@pytest.mark.parametrize("timestamp", ["2026-10-30T10:15:00", "2026-10-30T10:15:00.123456789Z", 123])
def test_v1_refuses_ambiguous_or_unrepresentable_times(batch, claims, settings, timestamp):
    batch["measurements"]["instantaneous"][0]["timestamp"] = timestamp
    with pytest.raises(ValueError):
        parse_upload(json.dumps(batch).encode(), claims, None, settings)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, 2**53 + 1])
def test_v1_refuses_non_finite_or_unrepresentable_values(batch, claims, settings, value):
    batch["measurements"]["instantaneous"][0]["value"] = value
    with pytest.raises(ValueError):
        parse_upload(json.dumps(batch).encode(), claims, None, settings)


def test_rejects_duplicate_json_keys(batch, claims, settings):
    raw = json.dumps(batch).encode().replace(b'"value": 72.12345678901234', b'"value": 72,"value": 74')
    with pytest.raises(ValueError):
        parse_upload(raw, claims, None, settings)


def test_record_payload_does_not_amplify_global_extras(batch, claims, settings):
    batch["unusedProviderMetadata"] = "x" * 100_000
    batch["deviceInfo"]["unusedExtra"] = "x" * 100_000
    upload = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    assert len(upload["records"][0]["payload"]) < 3000


def test_limits_empty_and_large_batches(batch, claims, settings):
    settings.max_readings = 1
    point = batch["measurements"]["instantaneous"][0]
    batch["measurements"]["instantaneous"].append(copy.deepcopy(point))
    with pytest.raises(ValueError):
        parse_upload(json.dumps(batch).encode(), claims, None, settings)

    batch["measurements"]["instantaneous"] = []
    with pytest.raises(ValueError):
        parse_upload(json.dumps(batch).encode(), claims, None, settings)


def test_existing_numeric_category_shapes_keep_their_distinct_time_fields(batch, claims, settings):
    batch["measurements"]["cumulative"] = [
        {
            "sourceRecordId": "steps-1",
            "type": "STEPS",
            "value": 100,
            "unit": "COUNT",
            "periodStart": "2026-10-30T10:00:00Z",
            "periodEnd": "2026-10-30T10:30:00Z",
            "duration": 1800,
        }
    ]
    batch["measurements"]["duration"] = [
        {
            "sourceRecordId": "sleep-1",
            "type": "SLEEP_ASLEEP",
            "value": 30,
            "unit": "MINUTE",
            "startTime": "2026-10-30T10:00:00Z",
            "endTime": "2026-10-30T10:30:00Z",
            "durationMinutes": 30,
        }
    ]
    upload = parse_upload(json.dumps(batch).encode(), claims, None, settings)
    assert upload["reading_count"] == 3 and len({r["record_key"] for r in upload["records"]}) == 3
    points = [json.loads(r["payload"])["measurements"] for r in upload["records"]]
    assert points[0]["instantaneous"][0]["timestamp"] == "2026-10-30T10:15:00Z"
    assert points[1]["cumulative"][0]["periodEnd"] == "2026-10-30T10:30:00Z"
    assert points[2]["duration"][0]["durationMinutes"] == 30
