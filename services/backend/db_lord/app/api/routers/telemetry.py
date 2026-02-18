from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import AwareDatetime

from app.api.dependencies import TelemetryServiceDep
from app.api.streaming import stream_as_ndjson
from app.api.telemetry.query_params import TelemetryTagsDep
from app.pagination import CursorParamsNoTotal
from app.schemas.telemetry import (
    TelemetryCreate,
    TelemetryPageResponse,
    TelemetryPointResponse,
    TelemetryRawPageResponse,
    TelemetryRawPointResponse,
)

router = APIRouter()

FieldsQuery = Annotated[
    list[str] | None, Query(description="Select specific fields to return (e.g. ?fields=heart_rate&fields=oxygen)")
]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_telemetry(item_in: TelemetryCreate, service: TelemetryServiceDep):
    await service.record_telemetry(item_in)


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def record_telemetry_batch(items_in: list[TelemetryCreate], service: TelemetryServiceDep):
    await service.record_batch(items_in)


@router.get(
    "/",
    response_model=TelemetryPageResponse,
)
async def read_telemetry(
    service: TelemetryServiceDep,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    measurement: str | None = None,
    bucket: str | None = None,
    tags: TelemetryTagsDep = None,
    fields: FieldsQuery = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()

    result = await service.read_telemetry(
        measurement,
        start,
        end,
        tags,
        fields,
        raw_params.size,
        raw_params.cursor,
        bucket=bucket,
    )
    return TelemetryPageResponse.create(result.items, params=params, next_=result.next_cursor)


@router.get(
    "/raw",
    response_model=TelemetryRawPageResponse,
)
async def read_telemetry_raw(
    service: TelemetryServiceDep,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    measurement: str | None = None,
    bucket: str | None = None,
    tags: TelemetryTagsDep = None,
    fields: FieldsQuery = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()

    result = await service.read_telemetry_raw(
        measurement,
        start,
        end,
        tags,
        fields,
        raw_params.size,
        raw_params.cursor,
        bucket=bucket,
    )
    return TelemetryRawPageResponse.create(result.items, params=params, next_=result.next_cursor)


@router.get(
    "/stream",
)
async def stream_telemetry(
    service: TelemetryServiceDep,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    measurement: str | None = None,
    bucket: str | None = None,
    tags: TelemetryTagsDep = None,
    fields: FieldsQuery = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()
    return stream_as_ndjson(
        service.stream_telemetry(
            measurement,
            start,
            end,
            tags,
            fields,
            raw_params.size,
            raw_params.cursor,
            bucket=bucket,
        ),
        schema=TelemetryPointResponse,
    )


@router.get(
    "/raw/stream",
)
async def stream_telemetry_raw(
    service: TelemetryServiceDep,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    measurement: str | None = None,
    bucket: str | None = None,
    tags: TelemetryTagsDep = None,
    fields: FieldsQuery = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()
    return stream_as_ndjson(
        service.stream_telemetry_raw(
            measurement,
            start,
            end,
            tags,
            fields,
            raw_params.size,
            raw_params.cursor,
            bucket=bucket,
        ),
        schema=TelemetryRawPointResponse,
    )
