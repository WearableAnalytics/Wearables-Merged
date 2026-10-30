"""Named account provisioning and password authority, independent of the web process."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.passwords import hash_password, normalize, verify_password
from app.db.postgres.orm import ControlAuthorityLock, ControlPassword, ControlUser
from app.schemas.control import RequestState, RequestStatus, UserResponse
from app.schemas.passwords import PasswordChange, PasswordLogin, PasswordReset, PasswordResult, StaffCreate
from app.services.case_access import clinical_transaction, current_actor
from app.services.control_service import audit


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class PasswordService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def gate(self) -> None:
        if (
            await self.db.scalar(
                select(ControlAuthorityLock)
                .where(ControlAuthorityLock.id == 1)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            is None
        ):
            raise HTTPException(503, "CONTROL_SCHEMA_NOT_INITIALIZED")

    @staticmethod
    def credential(user_id: UUID, encoded: str, *, temporary: bool) -> ControlPassword:
        now = datetime.now(UTC)
        return ControlPassword(
            user_id=user_id,
            password_hash=encoded,
            must_change=temporary,
            temporary_expires_at=now + timedelta(hours=24) if temporary else None,
            failed_attempts=0,
            locked_until=None,
            changed_at=now,
        )

    async def create_staff(self, item: StaffCreate) -> UserResponse:
        # Check before expensive hashing, then again in the committing transaction.
        async with clinical_transaction(self.db):
            await current_actor(self.db, item.actor_id, item.actor_auth_version, admin=True)
        encoded = await hash_password(item.temporary_password.get_secret_value(), item.email)
        try:
            async with clinical_transaction(self.db):
                await self.gate()
                actor = await current_actor(self.db, item.actor_id, item.actor_auth_version, admin=True)
                if await self.db.scalar(select(ControlUser.id).where(ControlUser.email == item.email)) is not None:
                    raise HTTPException(409, "STAFF_ACCOUNT_EXISTS")
                now = datetime.now(UTC)
                state = RequestState().model_dump(mode="json")
                if item.is_admin:
                    state.update(adminRequestStatus="approved", adminReviewedAt=now.isoformat())
                for role in item.roles:
                    state["roleRequestStatuses"][role] = "approved"
                    state["roleReviewedAt"][role] = now.isoformat()
                user = ControlUser(
                    id=uuid7(),
                    email=item.email,
                    name=item.name,
                    is_admin=item.is_admin,
                    roles=[str(role) for role in item.roles],
                    status="approved",
                    auth_version=1,
                    revision=1,
                    request_state=state,
                    created_at=now,
                    updated_at=now,
                    approved_at=now,
                )
                self.db.add(user)
                await self.db.flush()
                self.db.add(self.credential(user.id, encoded, temporary=True))
                audit(self.db, actor.id, "user.create_staff", user.id, user.revision)
                await self.db.flush()
                return UserResponse.model_validate(user)
        except IntegrityError:
            raise HTTPException(409, "STAFF_ACCOUNT_EXISTS") from None

    async def _check(self, row: ControlPassword | None, password: str) -> bool:
        now = datetime.now(UTC)
        if row and row.locked_until and aware(row.locked_until) > now:
            return False
        if row and row.locked_until:
            row.failed_attempts, row.locked_until = 0, None
        valid = await verify_password(row.password_hash if row else None, password)
        if row is None:
            return False
        if not valid:
            row.failed_attempts += 1
            if row.failed_attempts >= 5:
                row.locked_until = now + timedelta(minutes=15)
            return False
        if row.must_change and (row.temporary_expires_at is None or aware(row.temporary_expires_at) <= now):
            return False
        row.failed_attempts, row.locked_until = 0, None
        return True

    async def login(self, item: PasswordLogin) -> PasswordResult:
        async with clinical_transaction(self.db):
            user = await self.db.scalar(
                select(ControlUser)
                .where(ControlUser.email == item.email)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            row = (
                await self.db.scalar(
                    select(ControlPassword).where(ControlPassword.user_id == user.id).with_for_update()
                )
                if user
                else None
            )
            valid = await self._check(row, item.password.get_secret_value())
            if not valid or row is None or user is None or user.status != "approved":
                return PasswordResult(allowed=False)
            audit(self.db, user.id, "session.password_login", user.id, user.auth_version)
            return PasswordResult(
                allowed=True, user=UserResponse.model_validate(user), password_change_required=row.must_change
            )

    async def reset(self, user_id: UUID, item: PasswordReset) -> UserResponse:
        if user_id == item.actor_id:
            raise HTTPException(403, "USE_OWN_PASSWORD_CHANGE")
        async with clinical_transaction(self.db):
            await current_actor(self.db, item.actor_id, item.actor_auth_version, admin=True)
            target = await self.db.get(ControlUser, user_id)
            if target is None:
                raise HTTPException(404, "STAFF_ACCOUNT_UNKNOWN")
            email = target.email
        encoded = await hash_password(item.temporary_password.get_secret_value(), email)
        async with clinical_transaction(self.db):
            await self.gate()
            actor = await current_actor(self.db, item.actor_id, item.actor_auth_version, admin=True)
            target = await self.db.scalar(
                select(ControlUser)
                .where(ControlUser.id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if target is None or target.status != "approved":
                raise HTTPException(403, "STAFF_ACCOUNT_NOT_ACTIVE")
            if target.revision != item.expected_revision:
                raise HTTPException(409, "STALE_REVISION")
            row = await self.db.get(ControlPassword, target.id)
            now = datetime.now(UTC)
            if row is None:
                self.db.add(self.credential(target.id, encoded, temporary=True))
            else:
                row.password_hash, row.must_change = encoded, True
                row.temporary_expires_at, row.changed_at = now + timedelta(hours=24), now
                row.failed_attempts, row.locked_until = 0, None
            target.auth_version += 1
            target.revision += 1
            target.updated_at = now
            audit(self.db, actor.id, "credential.admin_reset", target.id, target.auth_version)
            await self.db.flush()
            return UserResponse.model_validate(target)

    async def change(self, item: PasswordChange, *, initial: bool) -> PasswordResult:
        if normalize(item.current_password.get_secret_value()) == normalize(item.new_password.get_secret_value()):
            raise HTTPException(422, "CHOOSE_DIFFERENT_PASSWORD")
        async with clinical_transaction(self.db):
            user = await current_actor(self.db, item.actor_id, item.actor_auth_version, allow_setup=initial)
            email = user.email
        encoded = await hash_password(item.new_password.get_secret_value(), email)
        async with clinical_transaction(self.db):
            user = await current_actor(
                self.db, item.actor_id, item.actor_auth_version, exclusive=True, allow_setup=initial
            )
            row = await self.db.scalar(
                select(ControlPassword).where(ControlPassword.user_id == user.id).with_for_update()
            )
            if row is None or row.must_change != initial:
                raise HTTPException(403, "PASSWORD_CHANGE_NOT_ALLOWED")
            if not await self._check(row, item.current_password.get_secret_value()):
                return PasswordResult(allowed=False)
            row.password_hash, row.must_change = encoded, False
            row.temporary_expires_at, row.changed_at = None, datetime.now(UTC)
            user.auth_version += 1
            user.revision += 1
            user.updated_at = row.changed_at
            audit(
                self.db,
                user.id,
                "credential.initial_change" if initial else "credential.change",
                user.id,
                user.auth_version,
            )
            await self.db.flush()
            return PasswordResult(allowed=True, user=UserResponse.model_validate(user))

    async def bootstrap(
        self, email: str, password: str, *, reset: bool = False, reason: str | None = None
    ) -> UserResponse:
        """Local server command only. No HTTP route or normal BFF credential can invoke bootstrap."""
        email = email.strip().lower()
        if email not in {v.strip().lower() for v in settings.CONTROL_BOOTSTRAP_ADMIN_EMAILS.split(",") if v.strip()}:
            raise HTTPException(403, "BOOTSTRAP_EMAIL_NOT_ALLOWED")
        encoded = await hash_password(password, email)
        async with clinical_transaction(self.db):
            await self.gate()
            user = await self.db.scalar(
                select(ControlUser)
                .where(ControlUser.email == email)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            now = datetime.now(UTC)
            if user is None and reset:
                raise HTTPException(409, "ADMIN_ACCOUNT_NOT_INITIALIZED")
            if user is None:
                user = ControlUser(
                    id=uuid7(),
                    email=email,
                    name=None,
                    is_admin=True,
                    roles=[],
                    status="approved",
                    auth_version=1,
                    revision=1,
                    request_state=RequestState(adminRequestStatus=RequestStatus.APPROVED).model_dump(mode="json"),
                    created_at=now,
                    updated_at=now,
                    approved_at=now,
                )
                self.db.add(user)
                await self.db.flush()
            if not user.is_admin or user.status != "approved":
                raise HTTPException(409, "BOOTSTRAP_WILL_NOT_RESTORE_AUTHORITY")
            existing = await self.db.get(ControlPassword, user.id)
            if reset:
                if existing is None or not reason or not 1 <= len(reason.strip()) <= 256:
                    raise HTTPException(409, "OPERATOR_RESET_REQUIRES_EXISTING_PASSWORD_AND_REASON")
                existing.password_hash = encoded
                existing.must_change = True
                existing.temporary_expires_at = now + timedelta(hours=24)
                existing.failed_attempts, existing.locked_until, existing.changed_at = 0, None, now
            else:
                if existing is not None:
                    raise HTTPException(409, "BOOTSTRAP_WILL_NOT_REPLACE_PASSWORD")
                self.db.add(self.credential(user.id, encoded, temporary=False))
            user.auth_version += 1
            user.revision += 1
            user.updated_at = now
            audit(
                self.db,
                None if reset else user.id,
                "credential.operator_reset" if reset else "credential.bootstrap",
                user.id,
                user.auth_version,
                reason=reason if reset else None,
            )
            await self.db.flush()
            return UserResponse.model_validate(user)
