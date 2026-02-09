from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.orm import Device
from app.db.postgres.repos.base import BaseRepo
from app.schemas.device import DeviceCreate, DeviceUpdate


class DeviceRepo(BaseRepo[Device, DeviceCreate, DeviceUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Device, db)

    async def get_with_assignments(self, id: UUID) -> Device | None:
        query = select(Device).where(Device.id == id).options(selectinload(Device.case_assignments))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_status(self, id: UUID, status: str, expected_status: str | None = None) -> bool:
        stmt = update(Device).where(Device.id == id)
        if expected_status is not None:
            stmt = stmt.where(Device.status == expected_status)
        stmt = stmt.values(status=status).returning(Device.id)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return row is not None
