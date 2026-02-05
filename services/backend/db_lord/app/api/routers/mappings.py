from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read
from app.db.postgres.repos.mappings_repo import MappingsRepo
from app.schemas.mappings import Mappings, MappingsCreate, MappingsUpdate
from app.services.mappings_service import MappingsService

router = APIRouter()


def get_mappings_service(db: Annotated[AsyncSession, Depends(get_db)]) -> MappingsService:
    return MappingsService(MappingsRepo(db))


def get_mappings_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> MappingsService:
    return MappingsService(MappingsRepo(db))


@router.post("/", response_model=Mappings, status_code=status.HTTP_201_CREATED)
async def create_mappings(item_in: MappingsCreate, service: Annotated[MappingsService, Depends(get_mappings_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Constraint violation") from exc


@router.get("/", response_model=list[Mappings])
async def list_mappings(service: Annotated[MappingsService, Depends(get_mappings_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=Mappings)
async def get_mappings(id: UUID, service: Annotated[MappingsService, Depends(get_mappings_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Mappings not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mappings(id: UUID, service: Annotated[MappingsService, Depends(get_mappings_service)]):
    try:
        await service.delete(id)
        return None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Mappings not found") from exc


@router.put("/{id}", response_model=Mappings, status_code=status.HTTP_200_OK)
async def update_mappings(
    id: UUID,
    item_in: MappingsUpdate,
    service: Annotated[MappingsService, Depends(get_mappings_service)],
):
    try:
        return await service.update(id, item_in)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Mappings not found") from exc
