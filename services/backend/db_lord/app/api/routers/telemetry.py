from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api import deps
from app.api.deps import get_current_user
from app.schemas.telemetry import TelemetryCreate, TelemetryPageResponse
from app.services.telemetry_service import TelemetryService

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_telemetry(
    item_in: TelemetryCreate, service: Annotated[TelemetryService, Depends(deps.get_telemetry_service)]
):
    await service.record_telemetry(item_in)
    return None


@router.post("/batch", status_code=status.HTTP_201_CREATED)
async def record_telemetry_batch(
    items_in: list[TelemetryCreate], service: Annotated[TelemetryService, Depends(deps.get_telemetry_service)]
):
    await service.record_batch(items_in)
    return None


@router.get("/", response_model=TelemetryPageResponse)
async def read_telemetry(
    service: Annotated[TelemetryService, Depends(deps.get_telemetry_service)],
    measurement: str,
    start: datetime | None = None,
    end: datetime | None = None,
    page_size: int = Query(100, ge=1, le=5000),
    cursor: str | None = None,
    patient_id: str | None = None,
    device_id: str | None = None,
    case_id: str | None = None,
):
    tags = {}
    if patient_id:
        tags["patient_id"] = patient_id
    if device_id:
        tags["device_id"] = device_id
    if case_id:
        tags["case_id"] = case_id

    return await service.read_telemetry(
        measurement=measurement,
        start=start,
        end=end,
        tags=tags if tags else None,
        page_size=page_size,
        cursor=cursor,
    )
