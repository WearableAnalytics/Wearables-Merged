from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import CaseContext, CaseDevice, CaseWearable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _active_assignment_window(model: type[CaseDevice] | type[CaseWearable], now_ts: datetime):
    return or_(
        model.assigned_to.is_(None),
        and_(model.assigned_from <= now_ts, model.assigned_to > now_ts),
    )


class AssignmentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    # Devices
    async def get_active_device(self, case_id: UUID, device_id: UUID) -> CaseDevice | None:
        now_ts = _utcnow()
        query = select(CaseDevice).where(
            and_(
                CaseDevice.case_id == case_id,
                CaseDevice.device_id == device_id,
                _active_assignment_window(CaseDevice, now_ts),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_last_device_assignment(self, case_id: UUID) -> CaseDevice | None:
        query = (
            select(CaseDevice).where(CaseDevice.case_id == case_id).order_by(CaseDevice.assigned_from.desc()).limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_device_assignments_by_case_ids(self, case_ids: list[UUID]) -> list[CaseDevice]:
        if not case_ids:
            return []
        query = (
            select(CaseDevice)
            .where(CaseDevice.case_id.in_(case_ids))
            .order_by(CaseDevice.case_id, CaseDevice.assigned_from.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_device_assignments_by_device_ids(self, device_ids: list[UUID]) -> list[CaseDevice]:
        if not device_ids:
            return []
        query = (
            select(CaseDevice)
            .where(CaseDevice.device_id.in_(device_ids))
            .order_by(CaseDevice.device_id, CaseDevice.assigned_from.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_active_device_assignments_by_case_ids(
        self, case_ids: list[UUID], now_ts: datetime | None = None
    ) -> list[CaseDevice]:
        if not case_ids:
            return []
        effective_now = now_ts or _utcnow()
        query = (
            select(CaseDevice)
            .where(CaseDevice.case_id.in_(case_ids), _active_assignment_window(CaseDevice, effective_now))
            .order_by(CaseDevice.case_id, CaseDevice.assigned_from.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def assign_device(
        self, case_id: UUID, device_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> CaseDevice | None:
        assignment = CaseDevice(
            case_id=case_id,
            device_id=device_id,
            assigned_from=start_time or _utcnow(),
            assigned_to=end_time,
        )
        self.db.add(assignment)
        return assignment

    async def unassign_last_device(self, case_id: UUID, end_time: datetime | None = None) -> CaseDevice | None:
        now_ts = _utcnow()
        effective_end_time = end_time or now_ts
        # Subquery to find the device_id of the most recent assignment
        subquery = (
            select(CaseDevice.device_id)
            .where(CaseDevice.case_id == case_id)
            .order_by(CaseDevice.assigned_from.desc())
            .limit(1)
            .scalar_subquery()
        )

        # Only update if its currently active
        query = (
            update(CaseDevice)
            .where(
                and_(
                    CaseDevice.case_id == case_id,
                    CaseDevice.device_id == subquery,
                    _active_assignment_window(CaseDevice, now_ts),
                )
            )
            .values(assigned_to=effective_end_time)
            .returning(CaseDevice)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def unassign_device(
        self, case_id: UUID, device_id: UUID, end_time: datetime | None = None
    ) -> CaseDevice | None:
        now_ts = _utcnow()
        effective_end_time = end_time or now_ts
        query = (
            update(CaseDevice)
            .where(
                and_(
                    CaseDevice.case_id == case_id,
                    CaseDevice.device_id == device_id,
                    _active_assignment_window(CaseDevice, now_ts),
                )
            )
            .values(assigned_to=effective_end_time)
            .returning(CaseDevice)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def delete_device_assignment(
        self, case_id: UUID, device_id: UUID, assigned_from: datetime | None = None
    ) -> CaseDevice | None:
        if assigned_from:
            stmt = (
                delete(CaseDevice)
                .where(
                    and_(
                        CaseDevice.case_id == case_id,
                        CaseDevice.device_id == device_id,
                        CaseDevice.assigned_from == assigned_from,
                    )
                )
                .returning(CaseDevice)
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        candidates_cte = (
            select(CaseDevice.case_id, CaseDevice.device_id, CaseDevice.assigned_from)
            .where(and_(CaseDevice.case_id == case_id, CaseDevice.device_id == device_id))
            .cte("candidates")
        )

        # Check if there is only one record for a given case/device combination and delete it.
        # If there are multiple
        stmt = (
            delete(CaseDevice)
            .where(
                tuple_(CaseDevice.case_id, CaseDevice.device_id, CaseDevice.assigned_from).in_(
                    select(candidates_cte.c.case_id, candidates_cte.c.device_id, candidates_cte.c.assigned_from)
                )
            )
            .where(select(func.count()).select_from(candidates_cte).scalar_subquery() == 1)
            .returning(CaseDevice)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # Wearables
    async def get_active_wearable(self, case_id: UUID, wearable_id: UUID) -> CaseWearable | None:
        now_ts = _utcnow()
        query = select(CaseWearable).where(
            and_(
                CaseWearable.case_id == case_id,
                CaseWearable.wearable_id == wearable_id,
                _active_assignment_window(CaseWearable, now_ts),
            )
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_last_wearable_assignment(self, case_id: UUID) -> CaseWearable | None:
        query = (
            select(CaseWearable)
            .where(CaseWearable.case_id == case_id)
            .order_by(CaseWearable.assigned_from.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def list_wearable_assignments_by_case_ids(self, case_ids: list[UUID]) -> list[CaseWearable]:
        if not case_ids:
            return []
        query = (
            select(CaseWearable)
            .where(CaseWearable.case_id.in_(case_ids))
            .order_by(CaseWearable.case_id, CaseWearable.assigned_from.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_wearable_assignments_by_wearable_ids(self, wearable_ids: list[UUID]) -> list[CaseWearable]:
        if not wearable_ids:
            return []
        query = (
            select(CaseWearable)
            .where(CaseWearable.wearable_id.in_(wearable_ids))
            .order_by(CaseWearable.wearable_id, CaseWearable.assigned_from.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_active_wearable_assignments_by_case_ids(
        self, case_ids: list[UUID], now_ts: datetime | None = None
    ) -> list[CaseWearable]:
        if not case_ids:
            return []
        effective_now = now_ts or _utcnow()
        query = (
            select(CaseWearable)
            .where(CaseWearable.case_id.in_(case_ids), _active_assignment_window(CaseWearable, effective_now))
            .order_by(CaseWearable.case_id, CaseWearable.assigned_from.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def assign_wearable(
        self, case_id: UUID, wearable_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> CaseWearable | None:
        assignment = CaseWearable(
            case_id=case_id,
            wearable_id=wearable_id,
            assigned_from=start_time or _utcnow(),
            assigned_to=end_time,
        )
        self.db.add(assignment)
        return assignment

    async def unassign_last_wearable(self, case_id: UUID, end_time: datetime | None = None) -> CaseWearable | None:
        now_ts = _utcnow()
        effective_end_time = end_time or now_ts
        subquery = (
            select(CaseWearable.wearable_id)
            .where(CaseWearable.case_id == case_id)
            .order_by(CaseWearable.assigned_from.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = (
            update(CaseWearable)
            .where(
                and_(
                    CaseWearable.case_id == case_id,
                    CaseWearable.wearable_id == subquery,
                    _active_assignment_window(CaseWearable, now_ts),
                )
            )
            .values(assigned_to=effective_end_time)
            .returning(CaseWearable)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def unassign_wearable(
        self, case_id: UUID, wearable_id: UUID, end_time: datetime | None = None
    ) -> CaseWearable | None:
        now_ts = _utcnow()
        effective_end_time = end_time or now_ts
        query = (
            update(CaseWearable)
            .where(
                and_(
                    CaseWearable.case_id == case_id,
                    CaseWearable.wearable_id == wearable_id,
                    _active_assignment_window(CaseWearable, now_ts),
                )
            )
            .values(assigned_to=effective_end_time)
            .returning(CaseWearable)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def delete_wearable_assignment(
        self, case_id: UUID, wearable_id: UUID, assigned_from: datetime | None = None
    ) -> CaseWearable | None:
        if assigned_from:
            stmt = (
                delete(CaseWearable)
                .where(
                    and_(
                        CaseWearable.case_id == case_id,
                        CaseWearable.wearable_id == wearable_id,
                        CaseWearable.assigned_from == assigned_from,
                    )
                )
                .returning(CaseWearable)
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        candidates_cte = (
            select(CaseWearable.case_id, CaseWearable.wearable_id, CaseWearable.assigned_from)
            .where(and_(CaseWearable.case_id == case_id, CaseWearable.wearable_id == wearable_id))
            .cte("candidates")
        )

        # Check if there is only one record for a given case/wearable combination and delete it.
        stmt = (
            delete(CaseWearable)
            .where(
                tuple_(CaseWearable.case_id, CaseWearable.wearable_id, CaseWearable.assigned_from).in_(
                    select(candidates_cte.c.case_id, candidates_cte.c.wearable_id, candidates_cte.c.assigned_from)
                )
            )
            .where(select(func.count()).select_from(candidates_cte).scalar_subquery() == 1)
            .returning(CaseWearable)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # Contexts
    async def link_context(self, case_id: UUID, context_id: UUID) -> CaseContext | None:
        query = (
            pg_insert(CaseContext)
            .values(case_id=case_id, context_id=context_id)
            .on_conflict_do_nothing(index_elements=["case_id", "context_id"])
        ).returning(CaseContext)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def unlink_context(self, case_id: UUID, context_id: UUID) -> CaseContext | None:
        query = (
            delete(CaseContext)
            .where(and_(CaseContext.case_id == case_id, CaseContext.context_id == context_id))
            .returning(CaseContext)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
