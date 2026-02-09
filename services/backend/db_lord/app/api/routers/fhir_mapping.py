from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import get_fhir_mapping_service, get_fhir_mapping_tree_service
from app.api.streaming import stream_as_ndjson
from app.schemas.fhir_mapping import (
    FHIRMappingCreate,
    FHIRMappingResponse,
    FHIRMappingTreeCreate,
    FHIRMappingTreeResponse,
    FHIRMappingTreeUpdate,
    FHIRMappingUpdate,
)
from app.services.fhir_mapping_service import FHIRMappingService, FHIRMappingTreeService

router = APIRouter()


# FHIR Mappings (Parent)
@router.get("/", response_model=CursorPage[FHIRMappingResponse])
async def list_fhir_mappings(
    service: Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)],
):
    return await service.list()


@router.get("/stream")
async def stream_fhir_mappings(
    service: Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(batch_size=batch_size))


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=FHIRMappingResponse)
async def create_fhir_mapping(
    payload: FHIRMappingCreate, service: Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)]
):
    return await service.create(payload)


# FHIR Mapping Trees (Child)
@router.get("/trees", response_model=CursorPage[FHIRMappingTreeResponse])
async def list_mapping_trees(service: Annotated[FHIRMappingTreeService, Depends(get_fhir_mapping_tree_service)]):
    return await service.list()


@router.get("/trees/stream")
async def stream_mapping_trees(
    service: Annotated[FHIRMappingTreeService, Depends(get_fhir_mapping_tree_service)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(batch_size=batch_size))


@router.post("/trees", status_code=status.HTTP_201_CREATED, response_model=FHIRMappingTreeResponse)
async def create_mapping_tree(
    payload: FHIRMappingTreeCreate, service: Annotated[FHIRMappingTreeService, Depends(get_fhir_mapping_tree_service)]
):
    return await service.create(payload)


@router.get("/trees/{id}", response_model=FHIRMappingTreeResponse)
async def get_mapping_tree(
    id: UUID, service: Annotated[FHIRMappingTreeService, Depends(get_fhir_mapping_tree_service)]
):
    return await service.get(id)


@router.patch("/trees/{id}", response_model=FHIRMappingTreeResponse)
async def update_mapping_tree(
    id: UUID,
    payload: FHIRMappingTreeUpdate,
    service: Annotated[FHIRMappingTreeService, Depends(get_fhir_mapping_tree_service)],
):
    return await service.update(id, payload)


@router.delete("/trees/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping_tree(
    id: UUID, service: Annotated[FHIRMappingTreeService, Depends(get_fhir_mapping_tree_service)]
):
    await service.delete(id)


@router.get("/{id}", response_model=FHIRMappingResponse)
async def get_fhir_mapping(id: UUID, service: Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)]):
    return await service.get(id)


@router.patch("/{id}", response_model=FHIRMappingResponse)
async def update_fhir_mapping(
    id: UUID, payload: FHIRMappingUpdate, service: Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)]
):
    return await service.update(id, payload)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fhir_mapping(id: UUID, service: Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)]):
    await service.delete(id)
