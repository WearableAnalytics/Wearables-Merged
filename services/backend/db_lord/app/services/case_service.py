from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping

from app.db.postgres.repos.case_repo import CaseRepo
from app.schemas.case import CaseCreate, CaseUpdate


class CaseService:
    def __init__(self, repo: CaseRepo):
        self.repo = repo

    async def get(self, id: UUID, expand: list[str] | None = None) -> RowMapping | None:
        base = await self.repo.get(id)
        if not base:
            raise ValueError("Case not found")
        return base

    async def get_with_relations(self, id: UUID, expand: list[str] | None = None) -> dict[str, Any]:
        expand = [e.strip().lower() for e in (expand or []) if e and e.strip()]
        allowed = {"devices", "wearables", "contexts", "patient"}
        expand_set = {e for e in expand if e in allowed}

        expanded = await self.repo.get_with_relations(id, expand_set)
        if not expanded:
            raise ValueError("Case not found")

        # Normalize shape into a plain dict so callers always see the same keys
        result = {
            "id": expanded["id"],
            "status": expanded["status"],
            "patient_id": expanded["patient_id"],
            "devices": [],
            "wearables": [],
            "contexts": [],
            "patient": None,
        }

        if "devices" in expand_set:
            devices = expanded.get("devices", []) or []
            result["devices"] = [
                {**d, "status": d.get("status").upper() if isinstance(d.get("status"), str) else d.get("status")}
                for d in devices
            ]
        if "wearables" in expand_set:
            wearables = expanded.get("wearables", []) or []
            result["wearables"] = [
                {
                    **w,
                    "status": w.get("status").upper() if isinstance(w.get("status"), str) else w.get("status"),
                }
                for w in wearables
            ]
        if "contexts" in expand_set:
            result["contexts"] = expanded.get("contexts", [])
        if "patient" in expand_set:
            result["patient"] = expanded.get("patient", None)

        return result

    async def create(self, obj_in: CaseCreate) -> RowMapping | None:
        return await self.repo.create(obj_in)

    async def get_all(self) -> list[RowMapping]:
        return await self.repo.get_all()

    async def delete(self, id: UUID) -> RowMapping | None:
        res = await self.repo.delete(id)
        if not res:
            raise ValueError("Case not found")
        return res

    async def update(self, id: UUID, obj_in: CaseUpdate) -> RowMapping | None:
        res = await self.repo.update(id, obj_in)
        if not res:
            raise ValueError("Case not found")
        return res

    async def get_by_patient_id(self, patient_id: UUID) -> list[RowMapping]:
        """Get all cases for a specific patient"""
        return await self.repo.get_by_patient_id(patient_id)
