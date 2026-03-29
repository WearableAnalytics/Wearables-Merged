from uuid import UUID

from fastapi import APIRouter, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import PatientFiltersDep, PatientServiceDep, PatientSortingDep
from app.api.streaming import STREAM_BATCH_SIZE_DEFAULT, StreamBatchSizeParam, stream_as_ndjson
from app.schemas.case import CaseResponse
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter()


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
async def create_patient(item_in: PatientCreate, service: PatientServiceDep):
    return await service.create(item_in)


@router.patch("/{id:uuid}", response_model=PatientResponse)
async def update_patient(id: UUID, item_in: PatientUpdate, service: PatientServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(id: UUID, service: PatientServiceDep):
    await service.delete(id)
    return None


@router.get("/{id:uuid}", response_model=PatientResponse)
async def get_patient(id: UUID, service: PatientServiceDep):
    return await service.get(id)


@router.get(
    "/{id:uuid}/cases",
    response_model=list[CaseResponse],
    summary="List patient cases",
    description="Return all cases linked to the specified patient.",
)
async def get_patient_cases(id: UUID, service: PatientServiceDep):
    return await service.get_cases(id)


@router.get("/", response_model=CursorPage[PatientResponse])
async def list_patients(service: PatientServiceDep, filters: PatientFiltersDep, sorting: PatientSortingDep):
    return await service.list(filters, sorting)


@router.get("/stream", summary="Stream patients as NDJSON")
async def stream_patients(
    service: PatientServiceDep,
    filters: PatientFiltersDep,
    sorting: PatientSortingDep,
    batch_size: StreamBatchSizeParam = STREAM_BATCH_SIZE_DEFAULT,
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=PatientResponse)
