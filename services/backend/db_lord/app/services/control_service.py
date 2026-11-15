from datetime import UTC, datetime
from typing import Never
from uuid import UUID, uuid7

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ConflictError, EntityNotFoundError
from app.db.postgres.orm import ControlAudit, ControlAuthorityLock, ControlUser
from app.schemas.control import (
    RequestState,
    RequestStatus,
    RevokeSessions,
    UserCreate,
    UserDecision,
    UserDecisionResponse,
    UserPage,
    UserPatch,
    UserResponse,
)
from app.services.control_authority import authority_transaction


def _forbidden() -> Never:
    raise HTTPException(403, "CONTROL_FORBIDDEN")


def audit(
    db: AsyncSession,
    actor: UUID | None,
    operation: str,
    target: object,
    version: int | None,
    *,
    reason: str | None = None,
) -> None:
    db.add(
        ControlAudit(
            id=uuid7(),
            actor_id=actor,
            operation=operation,
            target_id=str(target),
            version=version,
            outcome="committed",
            occurred_at=datetime.now(UTC),
            reason=reason,
        )
    )


class ControlService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _authority_lock(self) -> None:
        gate = await self.db.scalar(select(ControlAuthorityLock).where(ControlAuthorityLock.id == 1).with_for_update())
        if gate is None:
            raise HTTPException(503, "CONTROL_SCHEMA_NOT_INITIALIZED")

    async def _actor(
        self, actor_id: UUID, auth_version: int, *, admin: bool = False, allow_pending: bool = False
    ) -> ControlUser:
        actor = await self.db.scalar(
            select(ControlUser)
            .where(ControlUser.id == actor_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if (
            actor is None
            or actor.auth_version != auth_version
            or (actor.status != "approved" and not (allow_pending and actor.status == "pending"))
        ):
            _forbidden()
        if admin and not actor.is_admin:
            _forbidden()
        return actor

    async def users(
        self, email: str | None, status: str | None, limit: int = 100, after: UUID | None = None
    ) -> UserPage:
        async with authority_transaction(self.db):
            query = select(ControlUser).order_by(ControlUser.id)
            if email is not None:
                query = query.where(ControlUser.email == email.strip().lower())
            if status is not None:
                query = query.where(ControlUser.status == status)
            if after is not None:
                query = query.where(ControlUser.id > after)
            rows = list(await self.db.scalars(query.limit(limit + 1)))
            return UserPage(
                items=[UserResponse.model_validate(row) for row in rows[:limit]],
                next_cursor=rows[limit - 1].id if len(rows) > limit else None,
            )

    async def user(self, user_id: UUID) -> ControlUser:
        async with authority_transaction(self.db):
            user = await self.db.get(ControlUser, user_id)
            if user is None:
                raise EntityNotFoundError("ControlUser", user_id)
            return user

    async def create_user(self, item: UserCreate, *, bootstrap: bool = False) -> ControlUser:
        if bootstrap and item.email not in {
            email.strip().lower() for email in settings.CONTROL_BOOTSTRAP_ADMIN_EMAILS.split(",") if email.strip()
        }:
            _forbidden()
        try:
            async with authority_transaction(self.db):
                if bootstrap:
                    await self._authority_lock()
                existing = await self.db.scalar(select(ControlUser).where(ControlUser.email == item.email))
                if existing is not None:
                    return existing  # Insert-only; login must never restore denied/admin authority.
                now = datetime.now(UTC)
                state = item.request_state.model_dump(mode="json")
                if bootstrap:
                    state = RequestState(
                        adminRequestStatus=RequestStatus.APPROVED, adminRequestedAt=now, adminReviewedAt=now
                    ).model_dump(mode="json")
                else:
                    self._check_self_request_state(RequestState().model_dump(mode="json"), state)
                    for role in item.roles:
                        state["roleRequestStatuses"][role] = "pending"
                        state["roleRequestedAt"][role] = now.isoformat()
                user = ControlUser(
                    id=uuid7(),
                    email=item.email,
                    name=item.name,
                    is_admin=bootstrap,
                    roles=[],
                    status="approved" if bootstrap else "pending",
                    auth_version=1,
                    revision=1,
                    request_state=state,
                    created_at=now,
                    updated_at=now,
                    approved_at=now if bootstrap else None,
                    denied_at=None,
                )
                self.db.add(user)
                audit(
                    self.db,
                    user.id if bootstrap else None,
                    "user.bootstrap" if bootstrap else "user.register",
                    user.id,
                    1,
                )
                await self.db.flush()
                return user
        except IntegrityError:
            # Concurrent create-if-absent resolves to the stored identity, without updating access.
            async with authority_transaction(self.db):
                existing = await self.db.scalar(select(ControlUser).where(ControlUser.email == item.email))
                if existing is None:
                    raise
                return existing

    @staticmethod
    def _check_self_request_state(old: dict, new: dict) -> None:
        old = RequestState.model_validate(old).model_dump(mode="json")
        new = RequestState.model_validate(new).model_dump(mode="json")
        for key in ("adminReviewedAt", "roleReviewedAt"):
            if new.get(key) != old.get(key):
                _forbidden()
        old_status = old.get("adminRequestStatus", "none")
        if new.get("adminRequestStatus") != old_status and new.get("adminRequestStatus") not in ("none", "pending"):
            _forbidden()
        for role in ("practitioner", "researcher"):
            before = old.get("roleRequestStatuses", {}).get(role, "none")
            after = new.get("roleRequestStatuses", {}).get(role, "none")
            if after != before and after not in ("none", "pending"):
                _forbidden()

    async def patch_user(self, user_id: UUID, item: UserPatch) -> ControlUser:
        async with authority_transaction(self.db):
            current = await self.db.get(ControlUser, user_id)
            if current is None:
                raise EntityNotFoundError("ControlUser", user_id)
            next_admin = item.is_admin if item.is_admin is not None else current.is_admin
            next_roles = sorted({str(role) for role in item.roles}) if item.roles is not None else sorted(current.roles)
            if next_admin:
                next_roles = []
            next_status = str(item.status) if item.status is not None else current.status
            authority_changed = (next_admin, next_roles, next_status) != (
                current.is_admin,
                sorted(current.roles),
                current.status,
            )
            privileged = authority_changed or user_id != item.actor_id
            if privileged:
                await self._authority_lock()
            # Lock order: authority gate (privileged only), actor, target.
            actor = await self._actor(item.actor_id, item.actor_auth_version, admin=True) if privileged else None
            user = await self.db.scalar(
                select(ControlUser)
                .where(ControlUser.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if user is None:
                raise EntityNotFoundError("ControlUser", user_id)
            if actor is None:
                actor = user
                if actor.status not in ("approved", "pending") or actor.auth_version != item.actor_auth_version:
                    _forbidden()
            if user.revision != item.expected_revision:
                raise ConflictError("STALE_REVISION")
            if user.is_admin and user.status == "approved" and not (next_admin and next_status == "approved"):
                others = await self.db.scalar(
                    select(func.count())
                    .select_from(ControlUser)
                    .where(ControlUser.id != user_id, ControlUser.is_admin.is_(True), ControlUser.status == "approved")
                )
                if not others:
                    raise ConflictError("LAST_ACTIVE_ADMIN")
            if item.request_state is not None:
                state = item.request_state.model_dump(mode="json")
                if not actor.is_admin:
                    self._check_self_request_state(user.request_state, state)
                user.request_state = state
            if "name" in item.model_fields_set:
                user.name = item.name
            now = datetime.now(UTC)
            if next_status != user.status:
                user.approved_at = now if next_status == "approved" else None
                user.denied_at = now if next_status == "denied" else None
            user.is_admin, user.roles, user.status = next_admin, next_roles, next_status
            user.revision += 1
            if authority_changed:
                user.auth_version += 1
            user.updated_at = now
            audit(
                self.db,
                actor.id,
                "user.authority" if authority_changed else "user.profile_request",
                user.id,
                user.revision,
            )
            await self.db.flush()
            return user

    async def revoke_sessions(self, user_id: UUID, item: RevokeSessions) -> ControlUser:
        async with authority_transaction(self.db):
            if user_id != item.actor_id:
                await self._authority_lock()
            actor = (
                await self._actor(item.actor_id, item.actor_auth_version, admin=True)
                if user_id != item.actor_id
                else None
            )
            user = await self.db.scalar(
                select(ControlUser)
                .where(ControlUser.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if user is None:
                raise EntityNotFoundError("ControlUser", user_id)
            if actor is None:
                actor = user
                if actor.status not in ("approved", "pending") or actor.auth_version != item.actor_auth_version:
                    _forbidden()
            if user.auth_version != item.expected_auth_version:
                raise ConflictError("STALE_AUTH_VERSION")
            user.auth_version += 1
            user.revision += 1
            user.updated_at = datetime.now(UTC)
            audit(self.db, actor.id, "user.revoke_sessions", user.id, user.auth_version)
            await self.db.flush()
            return user

    async def decide_user(self, item: UserDecision) -> UserDecisionResponse:
        async with authority_transaction(self.db):
            user = await self.db.get(ControlUser, item.user_id)
            reason = "allowed"
            if user is None:
                reason = "user_unknown"
            elif user.status != "approved":
                reason = "user_unapproved"
            elif user.auth_version != item.auth_version:
                reason = "session_revoked"
            elif item.require_admin and not user.is_admin:
                reason = "admin_required"
            elif item.required_roles and not (user.is_admin or set(item.required_roles).intersection(user.roles)):
                reason = "role_required"
            return UserDecisionResponse(
                allowed=reason == "allowed",
                reason=reason,
                user=UserResponse.model_validate(user) if user else None,
                current_auth_version=user.auth_version if user else None,
            )
