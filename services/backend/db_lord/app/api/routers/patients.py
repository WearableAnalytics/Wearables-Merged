from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi_filters import FilterSet
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import get_case_service, get_patient_service
from app.api.streaming import stream_as_ndjson
from app.filters import PatientFilters, PatientSorting, SortingValues
from app.schemas.case import CaseResponse
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate
from app.services.case_service import CaseService
from app.services.patient_service import PatientService

router = APIRouter()


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(item_in: PatientCreate, service: Annotated[PatientService, Depends(get_patient_service)]):
    return await service.create(item_in)


@router.get("/", response_model=CursorPage[PatientResponse])
async def list_patients(
    service: Annotated[PatientService, Depends(get_patient_service)],
    filters: Annotated[FilterSet, Depends(PatientFilters)],
    sorting: Annotated[SortingValues, Depends(PatientSorting)],
):
    return await service.list(filters=filters, sorting=sorting)


@router.get("/stream")
async def stream_patients(
    service: Annotated[PatientService, Depends(get_patient_service)],
    filters: Annotated[FilterSet, Depends(PatientFilters)],
    sorting: Annotated[SortingValues, Depends(PatientSorting)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(filters=filters, sorting=sorting, batch_size=batch_size))


@router.get("/{id}", response_model=PatientResponse)
async def get_patient(id: UUID, service: Annotated[PatientService, Depends(get_patient_service)]):
    return await service.get(id)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(id: UUID, service: Annotated[PatientService, Depends(get_patient_service)]):
    await service.delete(id)
    return None


@router.put("/{id}", response_model=PatientResponse, status_code=status.HTTP_200_OK)
async def update_patient(
    id: UUID, item_in: PatientUpdate, service: Annotated[PatientService, Depends(get_patient_service)]
):
    return await service.update(id, item_in)


@router.get("/{id}/cases", response_model=list[CaseResponse])
async def get_patient_cases(id: UUID, service: Annotated[CaseService, Depends(get_case_service)]):
    """Get all cases for a specific patient"""
    return await service.get_by_patient_id(id)
