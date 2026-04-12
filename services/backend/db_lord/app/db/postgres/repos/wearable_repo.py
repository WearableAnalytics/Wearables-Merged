from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.orm import Wearable
from app.db.postgres.repos.base import BaseRepo
from app.schemas.wearable import WearableCreate, WearableUpdate


class WearableRepo(BaseRepo[Wearable, WearableCreate, WearableUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Wearable, db)

    async def get_with_assignments(self, id: UUID) -> Wearable | None:
        """Fetch a wearable with assignment rows preloaded for expanded reads."""
        query = select(Wearable).where(Wearable.id == id).options(selectinload(Wearable.case_assignments))
        return await self.db.scalar(query)

    async def update_status(self, id: UUID, status: str, expected_status: str | None = None) -> bool:
        """Update status optionally using optimistic semantics."""
        stmt = update(Wearable).where(Wearable.id == id)
        if expected_status is not None:
            stmt = stmt.where(Wearable.status == expected_status)
        stmt = stmt.values(status=status).returning(Wearable.id)
        row = await self.db.scalar(stmt)
        return row is not None
