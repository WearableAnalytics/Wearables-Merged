from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read, get_current_user
from app.db.postgres.repos.context_repo import ContextRepo
from app.schemas.context import Context, ContextCreate, ContextUpdate
from app.services.context_service import ContextService

router = APIRouter()


def get_context_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ContextService:
    return ContextService(ContextRepo(db))


def get_context_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> ContextService:
    return ContextService(ContextRepo(db))


@router.post("/", response_model=Context, status_code=status.HTTP_201_CREATED)
async def create_context(item_in: ContextCreate, service: Annotated[ContextService, Depends(get_context_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Constraint violation") from exc


@router.get("/", response_model=list[Context])
async def list_contexts(service: Annotated[ContextService, Depends(get_context_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=Context)
async def get_context(id: UUID, service: Annotated[ContextService, Depends(get_context_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Context not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(id: UUID, service: Annotated[ContextService, Depends(get_context_service)]):
    try:
        await service.delete(id)
        return None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Context not found") from exc


@router.put("/{id}", response_model=Context, status_code=status.HTTP_200_OK)
async def update_context(
    id: UUID,
    item_in: ContextUpdate,
    service: Annotated[ContextService, Depends(get_context_service)],
):
    try:
        return await service.update(id, item_in)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Context not found") from exc
