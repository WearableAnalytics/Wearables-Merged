from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping

from app.db.postgres.repos.case_repo import CaseRepo
from app.schemas.case import CaseCreate, CaseUpdate


class CaseService:
    def __init__(self, repo: CaseRepo):
        self.repo = repo

    async def get(self, id: UUID, expand: Sequence[str] | None = None) -> RowMapping | None:
        base = await self.repo.get(id)
        if not base:
            raise ValueError("Case not found")
        return base

    async def get_with_relations(self, id: UUID, expand: list[str] | None = None) -> dict[str, Any]:
        allowed = {"devices", "wearables", "contexts", "patient"}
        expand_set = {e.strip().lower() for e in (expand or []) if e and e.strip().lower() in allowed}

        res = await self.repo.get_with_relations(id, expand_set)
        if not res:
            raise ValueError("Case not found")

        for key in ["devices", "wearables", "contexts"]:
            if key in expand_set:
                val = res.get(key)
                if val is None:
                    res[key] = []

        if "patient" in expand_set and res.get("patient") is None:
            res["patient"] = None

        return res

    async def create(self, obj_in: CaseCreate) -> RowMapping | None:
        return await self.repo.create(obj_in)

    async def get_all(self) -> Sequence[RowMapping]:
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
