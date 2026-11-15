"""Keep authenticated participant identity separate from provider record identity."""

import json
import re
from datetime import UTC, datetime
from uuid import uuid4

from .crypto import canonical, digest
from .models import IngestPayload

INPUT_KIND = "wearables.ingestion/1"
RESULT_KIND = "wearables.ingestion-result/1"


class Conflict(Exception):
    """An immutable request key or source record was reused with different data."""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("Non-finite JSON number")


def parse_upload(raw, claims, request_key, settings):
    document = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    payload = IngestPayload.model_validate(document)
    readings = list(payload.readings())
    if not 1 <= len(readings) <= settings.max_readings:
        raise ValueError("Invalid number of readings")
    strict = payload.contractVersion is not None
    if strict:
        # The v1 numeric contract preserves binary64 values and microsecond timestamps.
        # Higher-precision time series need an explicit future contract, not silent truncation.
        def check_times(value, field=""):
            if isinstance(value, dict):
                for name, item in value.items():
                    check_times(item, name)
            elif isinstance(value, list):
                for item in value:
                    check_times(item)
            elif (
                field
                in {
                    "timestamp",
                    "collectionStart",
                    "collectionEnd",
                    "lastSendTime",
                    "periodStart",
                    "periodEnd",
                    "startTime",
                    "endTime",
                }
                and value is not None
            ):
                if (
                    not isinstance(value, str)
                    or not re.fullmatch(
                        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
                    )
                    or datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is None
                ):
                    raise ValueError("v1 timestamps require an explicit UTC offset and at most six fractional digits")
            elif field == "value" and (isinstance(value, bool) or isinstance(value, int) and abs(value) > 2**53):
                raise ValueError("The numeric contract requires a representable binary64 value")

        check_times(document)
    if request_key is not None and not re.fullmatch(r"[!-~]{1,128}", request_key):
        raise ValueError("Invalid Idempotency-Key")
    wire_hash = digest(raw)
    request_hash = digest(canonical(["key", request_key])) if request_key else digest(canonical(["body", wire_hash]))
    upload_id = str(uuid4())
    scope = [claims["caseId"], claims["patientId"]]
    # sourceId identifies the provider's namespace, not the phone's installation ID.
    source = (
        [payload.sourcePlatform, payload.sourceId]
        if strict
        else [payload.sourcePlatform, payload.sourceName, payload.deviceInfo.deviceId]
    )
    source_key = digest(canonical(scope + source))
    # Copy only the bounded metadata needed by the mapper. Keep unmodelled global
    # metadata in the original archive, rather than duplicating it N times.
    base = {
        "deviceInfo": {"platform": payload.deviceInfo.platform, "deviceId": payload.deviceInfo.deviceId},
        "sourceName": payload.sourceName,
        "sourcePlatform": payload.sourcePlatform,
        "timestamp": payload.timestamp.isoformat(),
        "contractVersion": payload.contractVersion,
    }
    base["caseId"], base["participantId"] = scope
    records = []
    for ordinal, (category, _index, reading) in enumerate(readings):
        point = reading.model_dump(mode="json", exclude_none=True)
        for name in ("timestamp", "periodStart", "periodEnd", "startTime", "endTime"):
            value = getattr(reading, name, None)
            if value is not None and value.utcoffset() is not None:
                point[name] = value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        point_hash = digest(canonical([category, point]))
        identity = (
            ["source", source_key, reading.sourceRecordId] if strict else ["upload", *scope, request_hash, ordinal]
        )
        record_payload = dict(base)
        record_payload["measurements"] = {name: [] for name in ("instantaneous", "cumulative", "duration")}
        record_payload["measurements"][category] = [point]
        records.append(
            {
                "id": str(uuid4()),
                "record_key": digest(canonical(identity)),
                "input_sha256": point_hash,
                "source_key": source_key,
                "identity_mode": "source-record" if strict else "upload-only",
                "payload": canonical(record_payload),
            }
        )
    return {
        "id": upload_id,
        "case_id": scope[0],
        "participant_id": scope[1],
        "request_key": request_hash,
        "raw_sha256": wire_hash,
        "raw": raw,
        "records": records,
        "reading_count": len(readings),
    }
