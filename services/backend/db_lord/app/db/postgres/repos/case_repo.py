from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.postgres.orm import Case, CaseDevice, CaseWearable
from app.db.postgres.repos.base import BaseRepo
from app.schemas.case import CaseCreate, CaseExpandableFields, CaseUpdate


class CaseRepo(BaseRepo[Case, CaseCreate, CaseUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Case, db)

    # TODO: improve performance (1. Dont build dicts in PYTHON??? 2. Optimize queries)
    async def get_with_relations(self, id: UUID, expand: list[CaseExpandableFields]) -> Case | None:
        """
        Get a case with optional relationship expansion using ORM.
        """
        query = select(Case).where(Case.id == id)

        if CaseExpandableFields.DEVICES in expand:
            query = query.options(selectinload(Case.device_assignments).selectinload(CaseDevice.device))
        if CaseExpandableFields.WEARABLES in expand:
            query = query.options(selectinload(Case.wearable_assignments).selectinload(CaseWearable.wearable))
        if CaseExpandableFields.CONTEXTS in expand:
            query = query.options(selectinload(Case.contexts))
        if CaseExpandableFields.PATIENT in expand:
            query = query.options(joinedload(Case.patient))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_patient_id(self, patient_id: UUID) -> list[Case]:
        """Get all cases for a specific patient."""
        stmt = select(Case).where(Case.patient_id == patient_id)
        result = await self.db.execute(stmt)
        return list(result.scalars())
