from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime

from app.api.dependencies import TelemetryServiceDep
from app.api.streaming import stream_as_ndjson
from app.api.telemetry_params import get_telemetry_tags
from app.schemas.telemetry import (
    TelemetryCreate,
    TelemetryPointResponse,
    TelemetryRawPointResponse,
    TelemetryRawWindowResponse,
    TelemetryWindowResponse,
)
from app.telemetry.constants import TELEMETRY_DEFAULT_LIMIT, TELEMETRY_MAX_LIMIT
from app.telemetry.types import TelemetryTags

router = APIRouter()

MeasurementQuery = Annotated[str | None, Query(description="Optional Influx measurement name to read from.")]
BucketQuery = Annotated[str | None, Query(description="Optional Influx bucket override.")]
StartQuery = Annotated[AwareDatetime | None, Query(description="Inclusive lower bound for the telemetry time range.")]
EndQuery = Annotated[AwareDatetime | None, Query(description="Exclusive upper bound for the telemetry time range.")]
FieldsQuery = Annotated[list[str] | None, Query(description="Optional field filter.", examples=["heart_rate", "spo2"])]
WindowLimitQuery = Annotated[
    int,
    Query(
        ge=1,
        le=TELEMETRY_MAX_LIMIT,
        description="Target number of items to return from the requested time window.",
    ),
]
StreamLimitQuery = Annotated[
    int | None,
    Query(
        ge=1,
        le=TELEMETRY_MAX_LIMIT,
        description="Optional hard cap for streamed items. Omit to stream the full requested range.",
    ),
]


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Write one telemetry point",
    description="Persist one structured telemetry point into InfluxDB. "
    "This endpoint exists for testing and manual inspection. Normal writes should go through the ingestion service.",
)
async def record_telemetry(item_in: TelemetryCreate, service: TelemetryServiceDep):
    await service.record_telemetry(item_in)


@router.post(
    "/batch",
    status_code=status.HTTP_201_CREATED,
    summary="Write a telemetry batch",
    description="Persist multiple telemetry points into InfluxDB in a single request. "
    "This endpoint exists for testing and manual inspection. Normal writes should go through the ingestion service.",
)
async def record_telemetry_batch(items_in: list[TelemetryCreate], service: TelemetryServiceDep):
    await service.record_batch(items_in)


@router.get(
    "/",
    response_model=TelemetryWindowResponse,
    summary="Read structured telemetry",
    description="Read structured telemetry items from a time window. Raw Influx rows are grouped in Python by "
    "timestamp, measurement, and tag set before they are returned. Follow up requests use `next_end` as the next "
    "`end` until `has_more` is false. `limit` is a target lower bound and the response may include more items to "
    "keep a boundary timestamp complete.",
)
async def read_telemetry(
    service: TelemetryServiceDep,
    measurement: MeasurementQuery = None,
    bucket: BucketQuery = None,
    tags: Annotated[TelemetryTags | None, Depends(get_telemetry_tags)] = None,
    fields: FieldsQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: WindowLimitQuery = TELEMETRY_DEFAULT_LIMIT,
):
    result = await service.read_window(measurement, start, end, tags, fields, limit, bucket)
    return TelemetryWindowResponse(
        items=[TelemetryPointResponse.model_validate(item) for item in result.items],
        has_more=result.has_more,
        next_end=result.next_end,
    )


@router.get(
    "/raw",
    response_model=TelemetryRawWindowResponse,
    summary="Read raw telemetry rows",
    description="Read raw telemetry rows from a time window. Each item represents one field row. "
    "Follow up requests use `next_end` as the next `end` until `has_more` is false. `limit` "
    "is a target lower bound and the response may include more rows to keep a boundary timestamp complete.",
)
async def read_telemetry_raw(
    service: TelemetryServiceDep,
    measurement: MeasurementQuery = None,
    bucket: BucketQuery = None,
    tags: Annotated[TelemetryTags | None, Depends(get_telemetry_tags)] = None,
    fields: FieldsQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: WindowLimitQuery = TELEMETRY_DEFAULT_LIMIT,
):
    result = await service.read_raw_window(measurement, start, end, tags, fields, limit, bucket)
    return TelemetryRawWindowResponse(
        items=[TelemetryRawPointResponse.model_validate(item) for item in result.items],
        has_more=result.has_more,
        next_end=result.next_end,
    )


@router.get(
    "/stream",
    summary="Stream structured telemetry",
    description="Stream structured telemetry items as NDJSON. Raw Influx rows are loaded in bounded time chunks, "
    "grouped in Python by timestamp, measurement, and tag set, and then emitted one structured item at a time. "
    "Omitting `limit` streams the full requested range.",
)
async def stream_telemetry(
    service: TelemetryServiceDep,
    measurement: MeasurementQuery = None,
    bucket: BucketQuery = None,
    tags: Annotated[TelemetryTags | None, Depends(get_telemetry_tags)] = None,
    fields: FieldsQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: StreamLimitQuery = None,
):
    return stream_as_ndjson(
        service.stream_structured(measurement, start, end, tags, fields, limit, bucket), TelemetryPointResponse
    )


@router.get(
    "/raw/stream",
    summary="Stream raw telemetry rows",
    description="Stream raw telemetry rows as NDJSON. Each emitted item represents one field row. "
    "Omitting `limit` streams the full requested range.",
)
async def stream_telemetry_raw(
    service: TelemetryServiceDep,
    measurement: MeasurementQuery = None,
    bucket: BucketQuery = None,
    tags: Annotated[TelemetryTags | None, Depends(get_telemetry_tags)] = None,
    fields: FieldsQuery = None,
    start: StartQuery = None,
    end: EndQuery = None,
    limit: StreamLimitQuery = None,
):
    return stream_as_ndjson(
        service.stream_raw(measurement, start, end, tags, fields, limit, bucket), TelemetryRawPointResponse
    )
