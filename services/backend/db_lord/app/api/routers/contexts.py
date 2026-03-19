from uuid import UUID

from fastapi import APIRouter, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import ContextFiltersDep, ContextServiceDep, ContextSortingDep
from app.api.params import STREAM_BATCH_SIZE_DEFAULT, StreamBatchSizeParam
from app.api.streaming import stream_as_ndjson
from app.schemas.context import ContextCreate, ContextResponse, ContextUpdate

router = APIRouter()


@router.post("/", response_model=ContextResponse, status_code=status.HTTP_201_CREATED)
async def create_context(item_in: ContextCreate, service: ContextServiceDep):
    return await service.create(item_in)


@router.patch("/{id:uuid}", response_model=ContextResponse)
async def update_context(id: UUID, item_in: ContextUpdate, service: ContextServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(id: UUID, service: ContextServiceDep):
    await service.delete(id)


@router.get("/{id:uuid}", response_model=ContextResponse)
async def get_context(id: UUID, service: ContextServiceDep):
    return await service.get(id)


@router.get("/", response_model=CursorPage[ContextResponse])
async def list_contexts(service: ContextServiceDep, filters: ContextFiltersDep, sorting: ContextSortingDep):
    return await service.list(filters, sorting)


@router.get("/stream")
async def stream_contexts(
    service: ContextServiceDep,
    filters: ContextFiltersDep,
    sorting: ContextSortingDep,
    batch_size: StreamBatchSizeParam = STREAM_BATCH_SIZE_DEFAULT,
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=ContextResponse)
