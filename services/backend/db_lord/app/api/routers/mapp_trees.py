from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_db_read
from app.db.postgres.repos.mappings_repo import MapTreesRepo
from app.schemas.mappings import MapTrees, MapTreesCreate, MapTreesUpdate
from app.services.mappings_service import MapTreesService

router = APIRouter()


def get_map_trees_service(db: Annotated[AsyncSession, Depends(get_db)]) -> MapTreesService:
    return MapTreesService(MapTreesRepo(db))


def get_map_trees_service_read(db: Annotated[AsyncSession, Depends(get_db_read)]) -> MapTreesService:
    return MapTreesService(MapTreesRepo(db))


@router.post("/", response_model=MapTrees, status_code=status.HTTP_201_CREATED)
async def create_map_tree(item_in: MapTreesCreate, service: Annotated[MapTreesService, Depends(get_map_trees_service)]):
    try:
        return await service.create(item_in)
    except IntegrityError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Constraint violation") from exc


@router.get("/", response_model=list[MapTrees])
async def list_map_trees(service: Annotated[MapTreesService, Depends(get_map_trees_service_read)]):
    return await service.get_all()


@router.get("/{id}", response_model=MapTrees)
async def get_map_tree(id: UUID, service: Annotated[MapTreesService, Depends(get_map_trees_service_read)]):
    try:
        return await service.get(id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Map Tree not found") from exc


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_map_tree(id: UUID, service: Annotated[MapTreesService, Depends(get_map_trees_service)]):
    try:
        await service.delete(id)
        return None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Map Tree not found") from exc


@router.put("/{id}", response_model=MapTrees, status_code=status.HTTP_200_OK)
async def update_map_tree(
    id: UUID,
    item_in: MapTreesUpdate,
    service: Annotated[MapTreesService, Depends(get_map_trees_service)],
):
    try:
        return await service.update(id, item_in)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Map Tree not found") from exc
