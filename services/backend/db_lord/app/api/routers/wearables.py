from uuid import UUID

from fastapi import APIRouter, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import WearableFiltersDep, WearableServiceDep, WearableSortingDep
from app.api.params import STREAM_BATCH_SIZE_DEFAULT, StreamBatchSizeParam
from app.api.streaming import stream_as_ndjson
from app.schemas.assignment import WearableAssignmentResponse
from app.schemas.wearable import WearableCreate, WearableResponse, WearableUpdate

router = APIRouter()


@router.post("/", response_model=WearableResponse, status_code=status.HTTP_201_CREATED)
async def create_wearable(item_in: WearableCreate, service: WearableServiceDep):
    return await service.create(item_in)


@router.patch("/{id:uuid}", response_model=WearableResponse)
async def update_wearable(id: UUID, item_in: WearableUpdate, service: WearableServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wearable(id: UUID, service: WearableServiceDep):
    await service.delete(id)


@router.get("/{id:uuid}", response_model=WearableResponse)
async def get_wearable(id: UUID, service: WearableServiceDep):
    return await service.get(id)


@router.get("/{id:uuid}/assignments", response_model=list[WearableAssignmentResponse])
async def get_wearable_assignments(id: UUID, service: WearableServiceDep):
    return await service.get_assignments(id)


@router.get("/", response_model=CursorPage[WearableResponse])
async def list_wearables(service: WearableServiceDep, filters: WearableFiltersDep, sorting: WearableSortingDep):
    return await service.list(filters, sorting)


@router.get("/stream")
async def stream_wearables(
    service: WearableServiceDep,
    filters: WearableFiltersDep,
    sorting: WearableSortingDep,
    batch_size: StreamBatchSizeParam = STREAM_BATCH_SIZE_DEFAULT,
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=WearableResponse)
