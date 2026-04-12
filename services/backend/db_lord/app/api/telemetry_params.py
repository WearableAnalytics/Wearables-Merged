from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from app.telemetry.constants import (
    RESERVED_TELEMETRY_QUERY_KEYS,
    TELEMETRY_TAG_NAMES,
)
from app.telemetry.tag_filters import merge_tag_filter
from app.telemetry.types import TelemetryTags


def get_core_telemetry_tags(
    patient_id: str | None = None,
    device_id: str | None = None,
    wearable_id: str | None = None,
    case_id: str | None = None,
    context_id: str | None = None,
    mapping_id: str | None = None,
    dot_dependency_file_id: UUID | None = None,
) -> TelemetryTags | None:
    raw_tag_values: dict[str, str | UUID | None] = {
        "patient_id": patient_id,
        "device_id": device_id,
        "wearable_id": wearable_id,
        "case_id": case_id,
        "context_id": context_id,
        "mapping_id": mapping_id,
        "dot_dependency_file_id": dot_dependency_file_id,
    }
    tags: TelemetryTags = {}
    for tag_key in TELEMETRY_TAG_NAMES:
        tag_value = raw_tag_values[tag_key]
        if tag_value:
            tags[tag_key] = [str(tag_value)]
    return tags or None


def get_direct_query_telemetry_tags(request: Request) -> TelemetryTags | None:
    if "tag" in request.query_params:
        raise HTTPException(
            status_code=422,
            detail="Unsupported telemetry tag format. Use direct query params like ?sensor_type=ecg&site=icu.",
        )

    tags: TelemetryTags = {}
    for key, value in request.query_params.multi_items():
        if key in RESERVED_TELEMETRY_QUERY_KEYS or value == "":
            continue
        merge_tag_filter(tags, key, value)
    return tags or None


def get_telemetry_tags(
    core_tags: Annotated[TelemetryTags | None, Depends(get_core_telemetry_tags)] = None,
    direct_tags: Annotated[TelemetryTags | None, Depends(get_direct_query_telemetry_tags)] = None,
) -> TelemetryTags | None:
    if core_tags is None and direct_tags is None:
        return None

    tags: TelemetryTags = {}
    if direct_tags:
        tags.update(direct_tags)
    if core_tags:
        tags.update(core_tags)
    return tags
