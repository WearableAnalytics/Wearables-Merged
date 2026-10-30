"""Shared current actor and case-purpose authorization; no service-layer cycle."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import Case, CaseAccess, ControlPassword, ControlUser


@asynccontextmanager
async def clinical_transaction(db: AsyncSession) -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(5), db.begin():
            if db.get_bind().dialect.name == "postgresql":
                await db.execute(text("SET LOCAL lock_timeout = '1500ms'"))
                await db.execute(text("SET LOCAL statement_timeout = '4000ms'"))
            yield
    except TimeoutError:
        raise HTTPException(503, "CASE_COMMAND_UNAVAILABLE") from None
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) in {"55P03", "57014", "40001"}:
            raise HTTPException(503, "CASE_COMMAND_UNAVAILABLE") from None
        raise


async def current_actor(
    db: AsyncSession,
    actor_id: UUID,
    auth_version: int,
    *,
    admin: bool = False,
    clinical: bool = False,
    exclusive: bool = False,
    allow_setup: bool = False,
) -> ControlUser:
    actor = await db.scalar(
        select(ControlUser)
        .where(ControlUser.id == actor_id)
        .with_for_update(read=not exclusive)
        .execution_options(populate_existing=True)
    )
    if (
        actor is None
        or actor.status != "approved"
        or actor.auth_version != auth_version
        or (admin and not actor.is_admin)
        or (clinical and not (actor.is_admin or "practitioner" in actor.roles))
    ):
        raise HTTPException(403, "CASE_ACCESS_DENIED")
    credential = await db.scalar(
        select(ControlPassword).where(ControlPassword.user_id == actor.id).with_for_update(read=True)
    )
    if credential is None or (credential.must_change and not allow_setup):
        raise HTTPException(403, "PASSWORD_SETUP_REQUIRED")
    return actor


async def require_case_access(
    db: AsyncSession, actor: ControlUser, case: Case, scope: str, *, clinical_command: bool = False
) -> CaseAccess:
    assignment = await db.scalar(
        select(CaseAccess)
        .where(CaseAccess.case_id == case.id, CaseAccess.user_id == actor.id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return validate_case_access(actor, case, assignment, scope, clinical_command=clinical_command)


def validate_case_access(
    actor: ControlUser, case: Case, assignment: CaseAccess | None, scope: str, *, clinical_command: bool = False
) -> CaseAccess:
    """Apply shared policy to records read under the caller's transaction locks."""
    if (
        assignment is None
        or not assignment.active
        or assignment.patient_id != case.patient_id
        or "read" not in assignment.scopes
        or scope not in assignment.scopes
        or (clinical_command and assignment.purpose != "clinical-reference")
    ):
        raise HTTPException(403, "CASE_ACCESS_DENIED")
    eligible = actor.is_admin or (
        "practitioner" in actor.roles if assignment.purpose == "clinical-reference" else "researcher" in actor.roles
    )
    if not eligible:
        raise HTTPException(403, "CASE_ACCESS_DENIED")
    return assignment
