from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import (
    DotDependencyFileFiltersDep,
    DotDependencyFileServiceDep,
    DotDependencyFileSortingDep,
    FHIRMappingFiltersDep,
    FHIRMappingServiceDep,
    FHIRMappingSortingDep,
)
from app.api.streaming import stream_as_ndjson
from app.schemas.fhir_mapping import (
    DotDependencyFileCreate,
    DotDependencyFileResponse,
    DotDependencyFileUpdate,
    FHIRMappingCreate,
    FHIRMappingResponse,
    FHIRMappingUpdate,
)

router = APIRouter()


# FHIR Mappings (Parent)
@router.post("/", response_model=FHIRMappingResponse, status_code=status.HTTP_201_CREATED)
async def create_fhir_mapping(item_in: FHIRMappingCreate, service: FHIRMappingServiceDep):
    return await service.create(item_in)


@router.patch("/{id:uuid}", response_model=FHIRMappingResponse)
async def update_fhir_mapping(id: UUID, item_in: FHIRMappingUpdate, service: FHIRMappingServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fhir_mapping(id: UUID, service: FHIRMappingServiceDep):
    await service.delete(id)


@router.get("/{id:uuid}", response_model=FHIRMappingResponse)
async def get_fhir_mapping(id: UUID, service: FHIRMappingServiceDep):
    return await service.get(id)


@router.get("/", response_model=CursorPage[FHIRMappingResponse])
async def list_fhir_mappings(
    service: FHIRMappingServiceDep, filters: FHIRMappingFiltersDep, sorting: FHIRMappingSortingDep
):
    return await service.list(filters, sorting)


@router.get("/stream")
async def stream_fhir_mappings(
    service: FHIRMappingServiceDep,
    filters: FHIRMappingFiltersDep,
    sorting: FHIRMappingSortingDep,
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(
        service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=FHIRMappingResponse
    )


# Dot dependency file (Child)
@router.post("/dot_dependency_file", response_model=DotDependencyFileResponse, status_code=status.HTTP_201_CREATED)
async def create_dot_dependency_file(item_in: DotDependencyFileCreate, service: DotDependencyFileServiceDep):
    return await service.create(item_in)


@router.patch("/dot_dependency_file/{id:uuid}", response_model=DotDependencyFileResponse)
async def update_dot_dependency_file(id: UUID, item_in: DotDependencyFileUpdate, service: DotDependencyFileServiceDep):
    return await service.update(id, item_in)


@router.delete("/dot_dependency_file/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dot_dependency_file(id: UUID, service: DotDependencyFileServiceDep):
    await service.delete(id)


@router.get("/dot_dependency_file/{id:uuid}", response_model=DotDependencyFileResponse)
async def get_dot_dependency_file(id: UUID, service: DotDependencyFileServiceDep):
    return await service.get(id)


@router.get("/dot_dependency_file", response_model=CursorPage[DotDependencyFileResponse])
async def list_dot_dependency_files(
    service: DotDependencyFileServiceDep, filters: DotDependencyFileFiltersDep, sorting: DotDependencyFileSortingDep
):
    return await service.list(filters, sorting)


@router.get("/dot_dependency_file/stream")
async def stream_dot_dependency_files(
    service: DotDependencyFileServiceDep,
    filters: DotDependencyFileFiltersDep,
    sorting: DotDependencyFileSortingDep,
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(
        service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=DotDependencyFileResponse
    )
