from uuid import UUID

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.links import case_contexts, case_devices, case_wearables


class AssignmentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Devices
    async def find_active_assignment(self, case_id: UUID, device_id: UUID) -> dict | None:
        query = select(case_devices).where(
            and_(
                case_devices.c.case_id == case_id,
                case_devices.c.device_id == device_id,
                case_devices.c.assigned_to.is_(None),
            )
        )
        result = await self.db.execute(query)
        return result.mappings().first()

    async def close_assignment(self, case_id: UUID, device_id: UUID) -> None:
        stmt = (
            update(case_devices)
            .where(
                and_(
                    case_devices.c.case_id == case_id,
                    case_devices.c.device_id == device_id,
                    case_devices.c.assigned_to.is_(None),
                )
            )
            .values(assigned_to=func.now())
        )
        await self.db.execute(stmt)

    async def create_assignment(self, case_id: UUID, device_id: UUID) -> None:
        stmt = insert(case_devices).values(
            case_id=case_id, device_id=device_id, assigned_from=func.now(), assigned_to=None
        )
        await self.db.execute(stmt)

    # Wearables
    async def find_active_wearable_assignment(self, case_id: UUID, wearable_id: UUID) -> dict | None:
        query = select(case_wearables).where(
            and_(
                case_wearables.c.case_id == case_id,
                case_wearables.c.wearable_id == wearable_id,
                case_wearables.c.assigned_to.is_(None),
            )
        )
        result = await self.db.execute(query)
        return result.mappings().first()

    async def close_wearable_assignment(self, case_id: UUID, wearable_id: UUID) -> None:
        stmt = (
            update(case_wearables)
            .where(
                and_(
                    case_wearables.c.case_id == case_id,
                    case_wearables.c.wearable_id == wearable_id,
                    case_wearables.c.assigned_to.is_(None),
                )
            )
            .values(assigned_to=func.now())
        )
        await self.db.execute(stmt)

    async def create_wearable_assignment(self, case_id: UUID, wearable_id: UUID) -> None:
        stmt = insert(case_wearables).values(
            case_id=case_id, wearable_id=wearable_id, assigned_from=func.now(), assigned_to=None
        )
        await self.db.execute(stmt)

    # Contexts
    async def link_context(self, case_id: UUID, context_id: UUID) -> None:
        stmt = (
            pg_insert(case_contexts)
            .values(case_id=case_id, context_id=context_id)
            .on_conflict_do_nothing(index_elements=["case_id", "context_id"])
        )
        await self.db.execute(stmt)

    async def unlink_context(self, case_id: UUID, context_id: UUID) -> None:
        stmt = delete(case_contexts).where(
            and_(case_contexts.c.case_id == case_id, case_contexts.c.context_id == context_id)
        )
        await self.db.execute(stmt)
