from collections.abc import Collection
from typing import Any
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import lateral, true

from app.db.postgres.models import (
    case_contexts,
    case_devices,
    case_wearables,
    cases,
    contexts,
    devices,
    patients,
    wearables,
)
from app.db.postgres.repos.base import BaseRepo
from app.schemas.case import CaseCreate, CaseUpdate


class CaseRepo(BaseRepo[cases, CaseCreate, CaseUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(cases, db)

    async def get_with_relations(self, id: UUID, expand: Collection[str] | None = None) -> dict[str, Any] | None:
        # Probably dumb to do this again here, but whatever
        expand_set = {e.strip().lower() for e in (expand or []) if e and e.strip()}

        c_alias = cases.alias("c")

        cols = [
            c_alias.c.id.label("id"),
            c_alias.c.status.label("status"),
            c_alias.c.patient_id.label("patient_id"),
        ]

        stmt = select(*cols).select_from(c_alias)

        if "devices" in expand_set:
            dev_sub = (
                select(func.jsonb_agg(func.to_jsonb(literal_column("devices"))).label("devices"))
                .select_from(case_devices.join(devices, devices.c.id == case_devices.c.device_id))
                .where(case_devices.c.case_id == c_alias.c.id)
            )
            dev_lat = lateral(dev_sub).alias("dev")
            stmt = stmt.outerjoin(dev_lat, true()).add_columns(dev_lat.c.devices)

        if "wearables" in expand_set:
            wr_sub = (
                select(func.jsonb_agg(func.to_jsonb(literal_column("wearables"))).label("wearables"))
                .select_from(case_wearables.join(wearables, wearables.c.id == case_wearables.c.wearable_id))
                .where(case_wearables.c.case_id == c_alias.c.id)
            )
            wr_lat = lateral(wr_sub).alias("wr")
            stmt = stmt.outerjoin(wr_lat, true()).add_columns(wr_lat.c.wearables)

        if "contexts" in expand_set:
            ctx_sub = (
                select(func.jsonb_agg(func.to_jsonb(literal_column("contexts"))).label("contexts"))
                .select_from(case_contexts.join(contexts, contexts.c.id == case_contexts.c.context_id))
                .where(case_contexts.c.case_id == c_alias.c.id)
            )
            ctx_lat = lateral(ctx_sub).alias("ctx")
            stmt = stmt.outerjoin(ctx_lat, true()).add_columns(ctx_lat.c.contexts)

        if "patient" in expand_set:
            stmt = stmt.outerjoin(patients, patients.c.id == c_alias.c.patient_id).add_columns(
                func.to_jsonb(literal_column("patients")).label("patient")
            )

        stmt = stmt.where(c_alias.c.id == id)

        result = await self.db.execute(stmt)
        row = result.mappings().first()

        return dict(row) if row else None

    async def get_by_patient_id(self, patient_id: UUID) -> list:
        """Get all cases for a specific patient"""
        stmt = select(cases).where(cases.c.patient_id == patient_id)
        result = await self.db.execute(stmt)
        return list(result.mappings().all())
