from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_filters import FilterSet
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import get_wearable_service
from app.api.streaming import stream_as_ndjson
from app.filters import SortingValues, WearableFilters, WearableSorting
from app.schemas.wearable import WearableCreate, WearableResponse, WearableUpdate
from app.services.wearable_service import WearableService

router = APIRouter()


@router.post("/", response_model=WearableResponse, status_code=status.HTTP_201_CREATED)
async def create_wearable(item_in: WearableCreate, service: Annotated[WearableService, Depends(get_wearable_service)]):
    return await service.create(item_in)


@router.get("/", response_model=CursorPage[WearableResponse])
async def list_wearables(
    service: Annotated[WearableService, Depends(get_wearable_service)],
    filters: Annotated[FilterSet, Depends(WearableFilters)],
    sorting: Annotated[SortingValues, Depends(WearableSorting)],
):
    return await service.list(filters, sorting)


@router.get("/stream")
async def stream_wearables(
    service: Annotated[WearableService, Depends(get_wearable_service)],
    filters: Annotated[FilterSet, Depends(WearableFilters)],
    sorting: Annotated[SortingValues, Depends(WearableSorting)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size))


@router.get("/{id}", response_model=WearableResponse)
async def get_wearable(id: UUID, service: Annotated[WearableService, Depends(get_wearable_service)]):
    return await service.get(id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wearable(id: UUID, service: Annotated[WearableService, Depends(get_wearable_service)]):
    await service.delete(id)
    return None


@router.put("/{id}", response_model=WearableResponse, status_code=status.HTTP_200_OK)
async def update_wearable(
    id: UUID, item_in: WearableUpdate, service: Annotated[WearableService, Depends(get_wearable_service)]
):
    return await service.update(id, item_in)
