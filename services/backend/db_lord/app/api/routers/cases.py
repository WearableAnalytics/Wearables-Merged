from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read, get_current_user
from app.db.postgres.repos.case_repo import CaseRepo
from app.schemas.case import Case, CaseCreate, CaseExpanded
from app.services.assignment_service import AssignmentService
from app.services.case_service import CaseService

router = APIRouter()


def get_case_service(db: Annotated[AsyncSession, Depends(get_db)]) -> CaseService:
    return CaseService(CaseRepo(db))


def get_case_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> CaseService:
    return CaseService(CaseRepo(db))


def get_assignment_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AssignmentService:
    return AssignmentService(db)


@router.post("/", response_model=Case, status_code=status.HTTP_201_CREATED)
async def create_case(item_in: CaseCreate, service: Annotated[CaseService, Depends(get_case_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Constraint violation") from exc


@router.get("/", response_model=list[Case])
async def list_cases(service: Annotated[CaseService, Depends(get_case_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=Case)
async def get_case(id: UUID, service: Annotated[CaseService, Depends(get_case_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


@router.get("/{id}/expanded", response_model=CaseExpanded)
async def get_case_expanded(
    id: UUID,
    service: Annotated[CaseService, Depends(get_case_service_read)],
    expand: Annotated[list[str] | None, Query()] = None,
):
    try:
        return await service.get_with_relations(id, expand=expand)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Case not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(id: UUID, service: Annotated[CaseService, Depends(get_case_service)]):
    await service.delete(id)
    return None


# Assignment Endpoints
@router.post("/{case_id}/devices/{device_id}", status_code=status.HTTP_201_CREATED)
async def assign_device(
    case_id: UUID,
    device_id: UUID,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
):
    try:
        await service.assign_device(case_id, device_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Constraint violation") from exc


@router.post("/{case_id}/wearables/{wearable_id}", status_code=status.HTTP_201_CREATED)
async def assign_wearable(
    case_id: UUID,
    wearable_id: UUID,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
):
    try:
        await service.assign_wearable(case_id, wearable_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Constraint violation") from exc


@router.post("/{case_id}/contexts/{context_id}", status_code=status.HTTP_201_CREATED)
async def link_context(
    case_id: UUID,
    context_id: UUID,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
):
    try:
        await service.link_context(case_id, context_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Constraint violation") from exc


@router.delete("/{case_id}/contexts/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_context(
    case_id: UUID,
    context_id: UUID,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
):
    try:
        await service.unlink_context(case_id, context_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Constraint violation") from exc


@router.delete("/{case_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_device(
    case_id: UUID,
    device_id: UUID,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
):
    try:
        await service.unassign_device(case_id, device_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{case_id}/wearables/{wearable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_wearable(
    case_id: UUID,
    wearable_id: UUID,
    service: Annotated[AssignmentService, Depends(get_assignment_service)],
):
    try:
        await service.unassign_wearable(case_id, wearable_id)
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
