from collections.abc import Collection
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.postgres.orm import Case, CaseDevice, CaseWearable
from app.db.postgres.repos.base import BaseRepo
from app.schemas.case import CaseCreate, CaseUpdate


class CaseRepo(BaseRepo[Case, CaseCreate, CaseUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Case, db)

    # TODO: improve performance (1. Dont build dicts in PYTHON??? 2. Optimize queries)
    async def get_with_relations(self, id: UUID, expand: Collection[str] | None = None) -> dict[str, Any] | None:
        """
        Get a case with optional relationship expansion using ORM.
        """
        expand_set = {e.strip().lower() for e in (expand or []) if e and e.strip()}

        query = select(Case).where(Case.id == id)

        # Add selectinload options for requested expansions
        if "devices" in expand_set:
            query = query.options(selectinload(Case.device_assignments).selectinload(CaseDevice.device))
        if "wearables" in expand_set:
            query = query.options(selectinload(Case.wearable_assignments).selectinload(CaseWearable.wearable))
        if "contexts" in expand_set:
            query = query.options(selectinload(Case.contexts))
        if "patient" in expand_set:
            query = query.options(selectinload(Case.patient))

        result = await self.db.execute(query)
        case = result.scalar_one_or_none()

        if not case:
            return None

        response: dict[str, Any] = {
            "id": case.id,
            "status": case.status.value if hasattr(case.status, "value") else case.status,
            "patient_id": case.patient_id,
        }

        # Add expanded relationships
        if "devices" in expand_set:
            # Expose active assigned device entities only.
            response["devices"] = [
                {
                    "id": da.device.id,
                    "serial_nr": da.device.serial_nr,
                    "model": da.device.model,
                    "manufacturer": da.device.manufacturer,
                    "os_version": da.device.os_version,
                    "status": da.device.status.value if hasattr(da.device.status, "value") else da.device.status,
                }
                for da in case.device_assignments
                if da.assigned_to is None and da.device is not None
            ]
        if "wearables" in expand_set:
            # Expose active assigned wearable entities only.
            response["wearables"] = [
                {
                    "id": wa.wearable.id,
                    "serial_nr": wa.wearable.serial_nr,
                    "model": wa.wearable.model,
                    "manufacturer": wa.wearable.manufacturer,
                    "os_version": wa.wearable.os_version,
                    "status": wa.wearable.status.value if hasattr(wa.wearable.status, "value") else wa.wearable.status,
                }
                for wa in case.wearable_assignments
                if wa.assigned_to is None and wa.wearable is not None
            ]
        if "contexts" in expand_set:
            response["contexts"] = [
                {
                    "id": ctx.id,
                    "group_name": ctx.group_name,
                    "coordinator": ctx.coordinator,
                }
                for ctx in case.contexts
            ]
        if "patient" in expand_set and case.patient:
            response["patient"] = {
                "id": case.patient.id,
                "charite_id": case.patient.charite_id,
                "name": case.patient.name,
                "sex": case.patient.sex,
                "dob": case.patient.dob,
                "weight": case.patient.weight,
                "height": case.patient.height,
            }

        return response

    async def get_by_patient_id(self, patient_id: UUID) -> list[Case]:
        """Get all cases for a specific patient."""
        stmt = select(Case).where(Case.patient_id == patient_id)
        result = await self.db.execute(stmt)
        return list(result.scalars())
