from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import AwareDatetime

from app.api.dependencies import FixedTelemetryTagsDep, TelemetryServiceDep, validate_fixed_telemetry_query_params
from app.api.streaming import stream_as_ndjson
from app.pagination import CursorParamsNoTotal
from app.schemas.telemetry import (
    TelemetryCreate,
    TelemetryPageResponse,
    TelemetryRawPageResponse,
    TelemetrySearchRequest,
)

router = APIRouter()


# TODO: field support??
@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_telemetry(item_in: TelemetryCreate, service: TelemetryServiceDep):
    await service.record_telemetry(item_in)
    return None


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def record_telemetry_batch(items_in: list[TelemetryCreate], service: TelemetryServiceDep):
    await service.record_batch(items_in)
    return None


@router.get(
    "/stream",
    dependencies=[Depends(validate_fixed_telemetry_query_params)],
)
async def stream_telemetry(
    service: TelemetryServiceDep,
    measurement: str,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    fixed_tags: FixedTelemetryTagsDep = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()
    return stream_as_ndjson(
        service.stream_telemetry(
            measurement, start, end, fixed_tags, page_size=raw_params.size, cursor=raw_params.cursor
        )
    )


@router.get(
    "/raw/stream",
    dependencies=[Depends(validate_fixed_telemetry_query_params)],
)
async def stream_telemetry_raw(
    service: TelemetryServiceDep,
    measurement: str,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    fixed_tags: FixedTelemetryTagsDep = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()
    return stream_as_ndjson(
        service.stream_telemetry_raw(
            measurement=measurement,
            start=start,
            end=end,
            tags=fixed_tags,
            page_size=raw_params.size,
            cursor=raw_params.cursor,
        )
    )


@router.get(
    "/",
    response_model=TelemetryPageResponse,
    dependencies=[Depends(validate_fixed_telemetry_query_params)],
)
async def read_telemetry(
    service: TelemetryServiceDep,
    measurement: str,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    fixed_tags: FixedTelemetryTagsDep = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()

    result = await service.read_telemetry(
        measurement=measurement,
        start=start,
        end=end,
        tags=fixed_tags,
        page_size=raw_params.size,
        cursor=raw_params.cursor,
    )
    return TelemetryPageResponse.create(result.items, params=params, next_=result.next_cursor)


@router.get(
    "/raw",
    response_model=TelemetryRawPageResponse,
    dependencies=[Depends(validate_fixed_telemetry_query_params)],
)
async def read_telemetry_raw(
    service: TelemetryServiceDep,
    measurement: str,
    params: Annotated[CursorParamsNoTotal, Depends(CursorParamsNoTotal)],
    fixed_tags: FixedTelemetryTagsDep = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
):
    raw_params = params.to_raw_params()

    result = await service.read_telemetry_raw(
        measurement=measurement,
        start=start,
        end=end,
        tags=fixed_tags,
        page_size=raw_params.size,
        cursor=raw_params.cursor,
    )
    return TelemetryRawPageResponse.create(result.items, params=params, next_=result.next_cursor)


@router.post("/search", response_model=TelemetryPageResponse)
async def search_telemetry(
    spec: TelemetrySearchRequest,
    service: TelemetryServiceDep,
):
    params = CursorParamsNoTotal(size=spec.size, cursor=spec.cursor)
    raw_params = params.to_raw_params()

    result = await service.read_telemetry(
        measurement=spec.measurement,
        start=spec.start,
        end=spec.end,
        tags=spec.tags if spec.tags else None,
        page_size=raw_params.size,
        cursor=raw_params.cursor,
    )
    return TelemetryPageResponse.create(result.items, params=params, next_=result.next_cursor)


@router.post("/raw/search", response_model=TelemetryRawPageResponse)
async def search_telemetry_raw(
    spec: TelemetrySearchRequest,
    service: TelemetryServiceDep,
):
    params = CursorParamsNoTotal(size=spec.size, cursor=spec.cursor)
    raw_params = params.to_raw_params()

    result = await service.read_telemetry_raw(
        measurement=spec.measurement,
        start=spec.start,
        end=spec.end,
        tags=spec.tags if spec.tags else None,
        page_size=raw_params.size,
        cursor=raw_params.cursor,
    )
    return TelemetryRawPageResponse.create(result.items, params=params, next_=result.next_cursor)
