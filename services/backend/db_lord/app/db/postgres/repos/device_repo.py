from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.device import devices
from app.db.postgres.repos.base import BaseRepo
from app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceRepo(BaseRepo[devices, DeviceCreate, DeviceUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(devices, db)

    async def update_status(self, id: UUID, status: str) -> bool:
        stmt = update(self.model).where(self.model.c.id == id).values(status=status).returning(self.pk_col)
        result = await self.db.execute(stmt)
        row = result.mappings().first()
        return bool(row)
