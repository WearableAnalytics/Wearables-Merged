"""Staff case assignments. No ingestion or measurement storage dependencies."""

from datetime import UTC, datetime
from typing import Never
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import Case, CaseAccess, ControlUser
from app.schemas.case_access import (
    AccessDecision,
    AccessDecisionResponse,
    AccessPage,
    AccessPut,
    AccessResponse,
    Actor,
    Scope,
)
from app.services.case_access import clinical_transaction, current_actor, require_case_access
from app.services.control_service import audit


def fail(code: str, status: int = 409) -> Never:
    raise HTTPException(status, code)


async def lock_case(db: AsyncSession, case_id: UUID, *, read: bool = False) -> Case:
    row = await db.scalar(
        select(Case).where(Case.id == case_id).with_for_update(read=read).execution_options(populate_existing=True)
    )
    if row is None:
        raise EntityNotFoundError("Case", case_id)
    return row


class CaseAccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def actor(self, item: Actor, *, admin: bool = False):
        return await current_actor(self.db, item.actor_id, item.actor_auth_version, admin=admin)

    async def access(self, actor: ControlUser, case: Case, scope: str):
        return await require_case_access(self.db, actor, case, scope)

    async def put_access(self, case_id: UUID, user_id: UUID, item: AccessPut) -> AccessResponse:
        async with clinical_transaction(self.db):
            actor = await self.actor(item, admin=True)
            target = await self.db.scalar(
                select(ControlUser).where(ControlUser.id == user_id).with_for_update(read=True)
            )
            case = await lock_case(self.db, case_id)
            if target is None:
                fail("ACCESS_TARGET_UNKNOWN", 404)
            eligible = target.is_admin or (
                "practitioner" in target.roles if item.purpose == "clinical-reference" else "researcher" in target.roles
            )
            if item.active and (target.status != "approved" or not eligible):
                fail("ACCESS_TARGET_INELIGIBLE", 403)
            assignment = await self.db.scalar(
                select(CaseAccess)
                .where(
                    CaseAccess.case_id == case_id,
                    CaseAccess.user_id == user_id,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            # Case row serializes creation without a global authority lock.
            if assignment is None:
                if item.expected_revision != 0:
                    fail("STALE_ACCESS_REVISION")
                now = datetime.now(UTC)
                assignment = CaseAccess(
                    case_id=case_id,
                    user_id=user_id,
                    patient_id=case.patient_id,
                    active=item.active,
                    purpose=item.purpose,
                    scopes=list(item.scopes),
                    revision=1,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(assignment)
            else:
                if assignment.revision != item.expected_revision:
                    fail("STALE_ACCESS_REVISION")
                assignment.patient_id = case.patient_id  # Explicit audited re-grant, never a background relink.
                assignment.active = item.active
                assignment.purpose = item.purpose
                assignment.scopes = list(item.scopes)
                assignment.revision += 1
                assignment.updated_at = datetime.now(UTC)
            audit(self.db, actor.id, "case.access", case_id, assignment.revision, reason=item.reason)
            await self.db.flush()
            return AccessResponse.model_validate(assignment)

    async def get_access(self, case_id: UUID, user_id: UUID, item: Actor) -> AccessResponse:
        async with clinical_transaction(self.db):
            actor = await self.actor(item)
            if actor.id != user_id and not actor.is_admin:
                fail("CASE_ACCESS_DENIED", 403)
            await lock_case(self.db, case_id, read=True)
            assignment = await self.db.get(CaseAccess, (case_id, user_id))
            if assignment is None:
                fail("CASE_ASSIGNMENT_NOT_FOUND", 404)
            return AccessResponse.model_validate(assignment)

    async def decide_access(self, item: AccessDecision) -> AccessDecisionResponse:
        try:
            async with clinical_transaction(self.db):
                actor = await self.actor(item)
                case = await lock_case(self.db, item.case_id, read=True)
                assignment = await self.access(actor, case, item.scope)
                capabilities: list[Scope] = [scope for scope in ("read", "export") if scope in assignment.scopes]
                return AccessDecisionResponse(
                    allowed=True,
                    reason="allowed",
                    capabilities=capabilities,
                    case_id=item.case_id,
                    patient_id=case.patient_id,
                )
        except EntityNotFoundError:
            return AccessDecisionResponse(
                allowed=False, reason="CASE_ACCESS_DENIED", capabilities=[], case_id=item.case_id, patient_id=None
            )
        except HTTPException as exc:
            if exc.status_code in {403, 404}:
                return AccessDecisionResponse(
                    allowed=False, reason="CASE_ACCESS_DENIED", capabilities=[], case_id=item.case_id, patient_id=None
                )
            raise

    async def list_access(self, item: Actor, limit: int, after: UUID | None) -> AccessPage:
        async with clinical_transaction(self.db):
            actor = await self.actor(item)
            eligible = []
            if actor.is_admin or "practitioner" in actor.roles:
                eligible.append("clinical-reference")
            if actor.is_admin or "researcher" in actor.roles:
                eligible.append("synthetic-research")
            query = (
                select(CaseAccess)
                .join(Case, Case.id == CaseAccess.case_id)
                .where(
                    CaseAccess.user_id == actor.id,
                    CaseAccess.active.is_(True),
                    CaseAccess.patient_id == Case.patient_id,
                    CaseAccess.purpose.in_(eligible),
                    CaseAccess.scopes != [],
                )
            )
            if after is not None:
                query = query.where(CaseAccess.case_id > after)
            rows = list((await self.db.scalars(query.order_by(CaseAccess.case_id).limit(limit + 1))).all())
            items = [AccessResponse.model_validate(row) for row in rows[:limit]]
            return AccessPage(items=items, next_cursor=items[-1].case_id if len(rows) > limit else None)
