"""Read identifying metadata under current staff and case authority."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import Case, CaseAccess, Patient
from app.schemas.case_access import Actor
from app.schemas.clinical_metadata import ClinicalCaseMetadata, ClinicalMetadataPage, ClinicalPatientMetadata
from app.services.case_access import clinical_transaction, current_actor, validate_case_access


class ClinicalMetadata:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def page(
        self,
        item: Actor,
        limit: int,
        after: UUID | None = None,
        *,
        case_id: UUID | None = None,
        patient_id: UUID | None = None,
    ) -> ClinicalMetadataPage:
        async with clinical_transaction(self.db):
            actor = await current_actor(self.db, item.actor_id, item.actor_auth_version, clinical=True)
            query = (
                select(Case, Patient, CaseAccess)
                .join(Patient, Patient.id == Case.patient_id)
                .join(CaseAccess, CaseAccess.case_id == Case.id)
                .where(
                    CaseAccess.user_id == actor.id,
                    CaseAccess.active.is_(True),
                    CaseAccess.purpose == "clinical-reference",
                    CaseAccess.patient_id == Case.patient_id,
                    CaseAccess.scopes != [],
                )
            )
            if after is not None:
                query = query.where(Case.id > after)
            if case_id is not None:
                query = query.where(Case.id == case_id)
            if patient_id is not None:
                query = query.where(Case.patient_id == patient_id)
            rows = list(
                (
                    await self.db.execute(
                        query.order_by(Case.id)
                        .limit(limit + 1)
                        .with_for_update(read=True, of=(Case, CaseAccess))
                        .execution_options(populate_existing=True)
                    )
                ).all()
            )
            items = []
            for case, patient, assignment in rows[:limit]:
                if "read" not in assignment.scopes:
                    continue
                validate_case_access(actor, case, assignment, "read", clinical_command=True)
                items.append(
                    ClinicalCaseMetadata(
                        id=case.id,
                        patient_id=case.patient_id,
                        status=case.status,
                        patient=ClinicalPatientMetadata(id=patient.id, name=patient.name, dob=patient.dob),
                    )
                )
            return ClinicalMetadataPage(items=items, next_cursor=rows[limit - 1][0].id if len(rows) > limit else None)

    async def one(self, case_id: UUID, item: Actor) -> ClinicalCaseMetadata:
        page = await self.page(item, 1, case_id=case_id)
        if not page.items:
            raise HTTPException(403, "CASE_ACCESS_DENIED")
        return page.items[0]
