from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read
from app.db.postgres.repos.device_repo import DeviceRepo
from app.schemas.device import Device, DeviceCreate, DeviceUpdate
from app.services.device_service import DeviceService

router = APIRouter()


def get_device_service(db: Annotated[AsyncSession, Depends(get_db)]) -> DeviceService:
    return DeviceService(DeviceRepo(db))


def get_device_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> DeviceService:
    return DeviceService(DeviceRepo(db))


@router.post("/", response_model=Device, status_code=status.HTTP_201_CREATED)
async def create_device(item_in: DeviceCreate, service: Annotated[DeviceService, Depends(get_device_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Constraint violation") from exc


@router.get("/", response_model=list[Device])
async def list_devices(service: Annotated[DeviceService, Depends(get_device_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=Device)
async def get_device(id: UUID, service: Annotated[DeviceService, Depends(get_device_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Device not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(id: UUID, service: Annotated[DeviceService, Depends(get_device_service)]):
    try:
        await service.delete(id)
        return None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Device not found") from exc


@router.put("/{id}", response_model=Device, status_code=status.HTTP_200_OK)
async def update_device(
    id: UUID,
    item_in: DeviceUpdate,
    service: Annotated[DeviceService, Depends(get_device_service)],
):
    try:
        return await service.update(id, item_in)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Device not found") from exc
