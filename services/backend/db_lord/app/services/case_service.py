from collections.abc import Sequence
from uuid import UUID

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import Case
from app.db.postgres.repos.case_repo import CaseRepo
from app.schemas.case import CaseCreate, CaseExpanded, CaseUpdate
from app.services.base import BaseService


class CaseService(BaseService[Case, CaseCreate, CaseUpdate, CaseRepo]):
    def __init__(self, repo: CaseRepo):
        super().__init__(repo)

    async def get_with_relations(self, id: UUID, expand: list[str] | None = None) -> CaseExpanded:
        allowed = {"devices", "wearables", "contexts", "patient"}
        expand_set = {e.strip().lower() for e in (expand or []) if e and e.strip().lower() in allowed}
        res = await self.repo.get_with_relations(id, expand_set)
        if not res:
            raise EntityNotFoundError("Case", id)

        for key in ["devices", "wearables", "contexts"]:
            if key in expand_set:
                val = res.get(key)
                if val is None:
                    res[key] = []

        if "patient" in expand_set and res.get("patient") is None:
            res["patient"] = None

        return CaseExpanded.model_validate(res)

    async def get_by_patient_id(self, patient_id: UUID) -> Sequence[Case]:
        """Get all cases for a specific patient"""
        return await self.repo.get_by_patient_id(patient_id)
