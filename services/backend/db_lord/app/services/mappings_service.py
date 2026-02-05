from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import RowMapping

from app.db.postgres.repos.mappings_repo import MappingsRepo, MapTreesRepo
from app.schemas.mappings import MappingsCreate, MappingsUpdate, MapTreesCreate, MapTreesUpdate


class MappingsService:
    def __init__(self, repo: MappingsRepo):
        self.repo = repo

    async def get(self, id: UUID) -> RowMapping | None:
        base = await self.repo.get(id)
        if not base:
            raise ValueError("Mapping not found")
        return base

    async def create(self, obj_in: MappingsCreate) -> RowMapping | None:
        return await self.repo.create(obj_in)

    async def get_all(self) -> Sequence[RowMapping]:
        return await self.repo.get_all()

    async def delete(self, id: UUID) -> RowMapping | None:
        res = await self.repo.delete(id)
        if not res:
            raise ValueError("Mapping not found")
        return res

    async def update(self, id: UUID, obj_in: MappingsUpdate) -> RowMapping | None:
        res = await self.repo.update(id, obj_in)
        if not res:
            raise ValueError("Mapping not found")
        return res


class MapTreesService:
    def __init__(self, repo: MapTreesRepo):
        self.repo = repo

    async def get(self, id: UUID) -> RowMapping | None:
        base = await self.repo.get(id)
        if not base:
            raise ValueError("Map Tree not found")
        return base

    async def create(self, obj_in: MapTreesCreate) -> RowMapping | None:
        return await self.repo.create(obj_in)

    async def get_all(self) -> Sequence[RowMapping]:
        return await self.repo.get_all()

    async def delete(self, id: UUID) -> RowMapping | None:
        res = await self.repo.delete(id)
        if not res:
            raise ValueError("Map Tree not found")
        return res

    async def update(self, id: UUID, obj_in: MapTreesUpdate) -> RowMapping | None:
        res = await self.repo.update(id, obj_in)
        if not res:
            raise ValueError("Map Tree not found")
        return res
