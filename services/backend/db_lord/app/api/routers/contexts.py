from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_filters import FilterSet
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import get_context_service
from app.api.streaming import stream_as_ndjson
from app.filters import ContextFilters, ContextSorting, SortingValues
from app.schemas.context import ContextCreate, ContextResponse, ContextUpdate
from app.services.context_service import ContextService

router = APIRouter()


@router.post("/", response_model=ContextResponse, status_code=status.HTTP_201_CREATED)
async def create_context(item_in: ContextCreate, service: Annotated[ContextService, Depends(get_context_service)]):
    return await service.create(item_in)


@router.get("/", response_model=CursorPage[ContextResponse])
async def list_contexts(
    service: Annotated[ContextService, Depends(get_context_service)],
    filters: Annotated[FilterSet, Depends(ContextFilters)],
    sorting: Annotated[SortingValues, Depends(ContextSorting)],
):
    return await service.list(filters=filters, sorting=sorting)


@router.get("/stream")
async def stream_contexts(
    service: Annotated[ContextService, Depends(get_context_service)],
    filters: Annotated[FilterSet, Depends(ContextFilters)],
    sorting: Annotated[SortingValues, Depends(ContextSorting)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(filters=filters, sorting=sorting, batch_size=batch_size))


@router.get("/{id}", response_model=ContextResponse)
async def get_context(id: UUID, service: Annotated[ContextService, Depends(get_context_service)]):
    return await service.get(id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(id: UUID, service: Annotated[ContextService, Depends(get_context_service)]):
    await service.delete(id)
    return None


@router.put("/{id}", response_model=ContextResponse, status_code=status.HTTP_200_OK)
async def update_context(
    id: UUID, item_in: ContextUpdate, service: Annotated[ContextService, Depends(get_context_service)]
):
    return await service.update(id, item_in)
