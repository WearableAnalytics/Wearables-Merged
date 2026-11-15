"""Atomic, one-use login proof shared by BFF replicas. No bearer is stored."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import ControlUser, LoginChallenge
from app.schemas.control import UserResponse
from app.services.control_authority import authority_transaction
from app.services.control_service import audit


class LoginChallengeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def issue(self, item) -> None:
        async with authority_transaction(self.db):
            user = await self.db.scalar(select(ControlUser).where(ControlUser.id == item.user_id).with_for_update())
            if user is None or user.status != "approved" or user.auth_version != item.auth_version:
                raise HTTPException(403, "LOGIN_NOT_ALLOWED")
            # One live challenge per account. Reissue invalidates the previous email link.
            await self.db.execute(delete(LoginChallenge).where(LoginChallenge.user_id == user.id))
            self.db.add(
                LoginChallenge(
                    token_hash=item.token_hash,
                    user_id=user.id,
                    auth_version=user.auth_version,
                    expires_at=datetime.now(UTC) + timedelta(seconds=item.ttl_seconds),
                )
            )

    async def consume(self, token_hash: str) -> UserResponse:
        async with authority_transaction(self.db):
            found = await self.db.get(LoginChallenge, token_hash)
            if found is None:
                raise HTTPException(403, "LOGIN_LINK_INVALID")
            # Same lock order as issue: user, then challenge.
            user = await self.db.scalar(
                select(ControlUser).where(ControlUser.id == found.user_id).with_for_update(read=True)
            )
            challenge = await self.db.scalar(
                select(LoginChallenge)
                .where(LoginChallenge.token_hash == token_hash)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            now = datetime.now(UTC)
            expiry = (
                challenge.expires_at
                if challenge and challenge.expires_at.tzinfo
                else (challenge.expires_at.replace(tzinfo=UTC) if challenge else now)
            )
            if (
                challenge is None
                or user is None
                or challenge.consumed_at is not None
                or expiry <= now
                or user.status != "approved"
                or user.auth_version != challenge.auth_version
            ):
                raise HTTPException(403, "LOGIN_LINK_INVALID")
            challenge.consumed_at = now
            audit(self.db, user.id, "session.login", user.id, user.auth_version)
            return UserResponse.model_validate(user)
