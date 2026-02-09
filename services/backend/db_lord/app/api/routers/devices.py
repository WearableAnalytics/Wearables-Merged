from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_filters import FilterSet
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import get_device_service
from app.api.streaming import stream_as_ndjson
from app.filters import DeviceFilters, DeviceSorting, SortingValues
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate
from app.services.device_service import DeviceService

router = APIRouter()


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(item_in: DeviceCreate, service: Annotated[DeviceService, Depends(get_device_service)]):
    return await service.create(item_in)


@router.get("/", response_model=CursorPage[DeviceResponse])
async def list_devices(
    service: Annotated[DeviceService, Depends(get_device_service)],
    filters: Annotated[FilterSet, Depends(DeviceFilters)],
    sorting: Annotated[SortingValues, Depends(DeviceSorting)],
):
    return await service.list(filters=filters, sorting=sorting)


@router.get("/stream")
async def stream_devices(
    service: Annotated[DeviceService, Depends(get_device_service)],
    filters: Annotated[FilterSet, Depends(DeviceFilters)],
    sorting: Annotated[SortingValues, Depends(DeviceSorting)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(filters=filters, sorting=sorting, batch_size=batch_size))


@router.get("/{id}", response_model=DeviceResponse)
async def get_device(id: UUID, service: Annotated[DeviceService, Depends(get_device_service)]):
    return await service.get(id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(id: UUID, service: Annotated[DeviceService, Depends(get_device_service)]):
    await service.delete(id)
    return None


@router.put("/{id}", response_model=DeviceResponse, status_code=status.HTTP_200_OK)
async def update_device(
    id: UUID, item_in: DeviceUpdate, service: Annotated[DeviceService, Depends(get_device_service)]
):
    return await service.update(id, item_in)
