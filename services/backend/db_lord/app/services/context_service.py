from uuid import UUID

from app.db.postgres.repos.context_repo import ContextRepo
from app.schemas.context import ContextCreate, ContextUpdate


class ContextService:
    def __init__(self, repo: ContextRepo):
        self.repo = repo

    async def get(self, id: UUID):
        res = await self.repo.get(id)
        if not res:
            raise ValueError("Context not found")
        return res

    async def create(self, obj_in: ContextCreate):
        return await self.repo.create(obj_in)

    async def delete(self, id: UUID):
        res = await self.repo.delete(id)
        if not res:
            raise ValueError("Context not found")
        return res

    async def update(self, id: UUID, obj_in: ContextUpdate):
        res = await self.repo.update(id, obj_in)
        if not res:
            raise ValueError("Context not found")
        return res

    async def upsert(self, id: UUID, obj_in: ContextCreate):
        return await self.repo.upsert(id, obj_in)

    async def get_all(self) -> list:
        return await self.repo.get_all()
