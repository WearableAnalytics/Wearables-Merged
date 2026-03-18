from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read, get_current_user
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.schemas.wearable import Wearable, WearableCreate, WearableUpdate
from app.services.wearable_service import WearableService

router = APIRouter()


def get_wearable_service(db: Annotated[AsyncSession, Depends(get_db)]) -> WearableService:
    return WearableService(WearableRepo(db))


def get_wearable_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> WearableService:
    return WearableService(WearableRepo(db))


@router.post("/", response_model=Wearable, status_code=status.HTTP_201_CREATED)
async def create_wearable(item_in: WearableCreate, service: Annotated[WearableService, Depends(get_wearable_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Constraint violation") from exc


@router.get("/", response_model=list[Wearable])
async def list_wearables(service: Annotated[WearableService, Depends(get_wearable_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=Wearable)
async def get_wearable(id: UUID, service: Annotated[WearableService, Depends(get_wearable_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Wearable not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wearable(id: UUID, service: Annotated[WearableService, Depends(get_wearable_service)]):
    try:
        await service.delete(id)
        return None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Wearable not found") from exc


@router.put("/{id}", response_model=Wearable, status_code=status.HTTP_200_OK)
async def update_wearable(
    id: UUID, item_in: WearableUpdate, service: Annotated[WearableService, Depends(get_wearable_service)]
):
    try:
        return await service.update(id, item_in)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Wearable not found") from exc
