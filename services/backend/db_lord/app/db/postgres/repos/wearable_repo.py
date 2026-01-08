from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.wearable import wearables
from app.db.postgres.repos.base import BaseRepo
from app.schemas.wearable import WearableCreate, WearableUpdate


class WearableRepo(BaseRepo[wearables, WearableCreate, WearableUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(wearables, db)

    async def update_status(self, id: UUID, status: str) -> bool:
        stmt = update(self.model).where(self.model.c.id == id).values(status=status).returning(self.pk_col)
        result = await self.db.execute(stmt)
        row = result.mappings().first()
        return bool(row)
