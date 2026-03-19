from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.orm import Patient
from app.db.postgres.repos.base import BaseRepo
from app.schemas.patient import PatientCreate, PatientUpdate


class PatientRepo(BaseRepo[Patient, PatientCreate, PatientUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Patient, db)

    async def get_with_cases(self, id: UUID) -> Patient | None:
        query = select(Patient).where(Patient.id == id).options(selectinload(Patient.cases))
        return await self.db.scalar(query)
