from typing import Annotated

from fastapi import Depends, HTTPException, Request

# Non-tag query params for telemetry reads.
TELEMETRY_NON_TAG_QUERY_KEYS = frozenset(
    {
        "measurement",
        "start",
        "end",
        "field",
        "fields",
        "size",
        "cursor",
        "tag",
    }
)

CORE_TELEMETRY_TAG_QUERY_KEYS = frozenset(
    {
        "patient_id",
        "device_id",
        "wearable_id",
        "case_id",
        "context_id",
        "mapping_id",
        "code",
    }
)

RESERVED_TELEMETRY_QUERY_KEYS = TELEMETRY_NON_TAG_QUERY_KEYS | CORE_TELEMETRY_TAG_QUERY_KEYS


def _merge_tag_values(tags: dict[str, str | list[str]], key: str, values: list[str]) -> None:
    if not values:
        return

    existing = tags.get(key)
    if isinstance(existing, list):
        merged = [*existing, *values]
    elif isinstance(existing, str):
        merged = [existing, *values]
    else:
        merged = [*values]

    deduped = list(dict.fromkeys(merged))
    tags[key] = deduped[0] if len(deduped) == 1 else deduped


def get_core_telemetry_tags(
    patient_id: str | None = None,
    device_id: str | None = None,
    wearable_id: str | None = None,
    case_id: str | None = None,
    context_id: str | None = None,
    mapping_id: str | None = None,
    code: str | None = None,
) -> dict[str, str | list[str]] | None:
    tags: dict[str, str | list[str]] = {}
    if patient_id:
        tags["patient_id"] = patient_id
    if device_id:
        tags["device_id"] = device_id
    if wearable_id:
        tags["wearable_id"] = wearable_id
    if case_id:
        tags["case_id"] = case_id
    if context_id:
        tags["context_id"] = context_id
    if mapping_id:
        tags["mapping_id"] = mapping_id
    if code:
        tags["code"] = code
    return tags or None


def get_direct_query_telemetry_tags(request: Request) -> dict[str, str | list[str]] | None:
    if "tag" in request.query_params:
        raise HTTPException(
            status_code=422,
            detail=("Unsupported telemetry tag format. Use direct query params like ?sensor_type=ecg&site=icu."),
        )

    tags: dict[str, str | list[str]] = {}
    seen_keys: set[str] = set()

    for key, _ in request.query_params.multi_items():
        if key in seen_keys or key in RESERVED_TELEMETRY_QUERY_KEYS:
            continue
        seen_keys.add(key)

        values = [value for value in request.query_params.getlist(key) if value != ""]
        if not values:
            continue

        _merge_tag_values(tags, key, values)

    return tags or None


CoreTelemetryTagsDep = Annotated[dict[str, str | list[str]] | None, Depends(get_core_telemetry_tags)]
DirectTelemetryTagsDep = Annotated[dict[str, str | list[str]] | None, Depends(get_direct_query_telemetry_tags)]


def get_telemetry_tags(
    core_tags: CoreTelemetryTagsDep = None,
    direct_tags: DirectTelemetryTagsDep = None,
) -> dict[str, str | list[str]] | None:
    if core_tags is None and direct_tags is None:
        return None

    tags: dict[str, str | list[str]] = {}
    if direct_tags:
        tags.update(direct_tags)
    if core_tags:
        tags.update(core_tags)
    return tags


TelemetryTagsDep = Annotated[dict[str, str | list[str]] | None, Depends(get_telemetry_tags)]
