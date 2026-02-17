from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import DeviceFiltersDep, DeviceServiceDep, DeviceSortingDep
from app.api.streaming import stream_as_ndjson
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceUpdate

router = APIRouter()


@router.post("/", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(item_in: DeviceCreate, service: DeviceServiceDep):
    return await service.create(item_in)


@router.patch("/{id:uuid}", response_model=DeviceResponse)
async def update_device(id: UUID, item_in: DeviceUpdate, service: DeviceServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(id: UUID, service: DeviceServiceDep):
    await service.delete(id)


@router.get("/{id:uuid}", response_model=DeviceResponse)
async def get_device(id: UUID, service: DeviceServiceDep):
    return await service.get(id)


@router.get("/", response_model=CursorPage[DeviceResponse])
async def list_devices(service: DeviceServiceDep, filters: DeviceFiltersDep, sorting: DeviceSortingDep):
    return await service.list(filters, sorting)


@router.get("/stream")
async def stream_devices(
    service: DeviceServiceDep,
    filters: DeviceFiltersDep,
    sorting: DeviceSortingDep,
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=DeviceResponse)
