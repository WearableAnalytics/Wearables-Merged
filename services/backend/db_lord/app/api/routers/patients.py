from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read
from app.db.postgres.repos.patient_repo import PatientRepo
from app.db.postgres.repos.case_repo import CaseRepo
from app.schemas.patient import Patient, PatientCreate, PatientUpdate
from app.schemas.case import Case
from app.services.patient_service import PatientService
from app.services.case_service import CaseService

router = APIRouter()


def get_patient_service(db: Annotated[AsyncSession, Depends(get_db)]) -> PatientService:
    return PatientService(PatientRepo(db))


def get_patient_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> PatientService:
    return PatientService(PatientRepo(db))


def get_case_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> CaseService:
    return CaseService(CaseRepo(db))


@router.post("/", response_model=Patient, status_code=status.HTTP_201_CREATED)
async def create_patient(item_in: PatientCreate, service: Annotated[PatientService, Depends(get_patient_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Patient already exists") from exc


@router.get("/", response_model=list[Patient])
async def list_patients(service: Annotated[PatientService, Depends(get_patient_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=Patient)
async def get_patient(id: UUID, service: Annotated[PatientService, Depends(get_patient_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Patient not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(id: UUID, service: Annotated[PatientService, Depends(get_patient_service)]):
    try:
        await service.delete(id)
        return None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Patient not found") from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Cannot delete patient due to conflict") from exc


@router.put("/{id}", response_model=Patient, status_code=status.HTTP_200_OK)
async def update_patient(
    id: UUID,
    item_in: PatientUpdate,
    service: Annotated[PatientService, Depends(get_patient_service)],
):
    try:
        return await service.update(id, item_in)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Patient not found") from exc
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Conflict during update")


@router.get("/{id}/cases", response_model=list[Case])
async def get_patient_cases(
    id: UUID,
    service: Annotated[CaseService, Depends(get_case_service_read)],
):
    """Get all cases for a specific patient"""
    return await service.get_by_patient_id(id)
