from collections.abc import Sequence
from uuid import UUID

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import Case, Patient
from app.db.postgres.repos.patient_repo import PatientRepo
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services.base import BaseService


class PatientService(BaseService[Patient, PatientCreate, PatientUpdate, PatientRepo]):
    def __init__(self, repo: PatientRepo):
        super().__init__(repo)

    async def get_cases(self, id: UUID) -> Sequence[Case]:
        patient = await self.repo.get_with_cases(id)
        if not patient:
            raise EntityNotFoundError("Patient", id)
        return list(patient.cases)
