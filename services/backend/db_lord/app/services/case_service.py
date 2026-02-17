from collections.abc import Sequence
from uuid import UUID

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import Case
from app.db.postgres.repos.case_repo import CaseRepo
from app.schemas.case import (
    CaseCreate,
    CaseDeviceAssignmentExpandedResponse,
    CaseExpandableFields,
    CaseExpanded,
    CaseResponse,
    CaseUpdate,
    CaseWearableAssignmentExpandedResponse,
)
from app.schemas.context import ContextResponse
from app.schemas.patient import PatientResponse
from app.services.base import BaseService


class CaseService(BaseService[Case, CaseCreate, CaseUpdate, CaseRepo]):
    def __init__(self, repo: CaseRepo):
        super().__init__(repo)

    async def get_with_relations(self, id: UUID, expand: list[CaseExpandableFields]) -> CaseExpanded:
        res = await self.repo.get_with_relations(id, expand)
        if not res:
            raise EntityNotFoundError("Case", id)

        base = CaseResponse.model_validate(res)
        extra = {}

        if CaseExpandableFields.DEVICES in expand:
            extra["devices"] = [
                CaseDeviceAssignmentExpandedResponse.model_validate(d_a) for d_a in res.device_assignments
            ]

        if CaseExpandableFields.WEARABLES in expand:
            extra["wearables"] = [
                CaseWearableAssignmentExpandedResponse.model_validate(w_a) for w_a in res.wearable_assignments
            ]

        if CaseExpandableFields.CONTEXTS in expand:
            extra["contexts"] = [ContextResponse.model_validate(c) for c in res.contexts]

        if CaseExpandableFields.PATIENT in expand:
            extra["patient"] = PatientResponse.model_validate(res.patient) if res.patient else None

        return CaseExpanded(**base.model_dump(), **extra)

    async def get_by_patient_id(self, patient_id: UUID) -> Sequence[Case]:
        """Get all cases for a specific patient"""
        return await self.repo.get_by_patient_id(patient_id)
