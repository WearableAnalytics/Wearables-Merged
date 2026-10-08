from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import ApiToken
from app.schemas.api_token import ApiTokenCreate

# last_used_at is informational; don't write it on every request.
LAST_USED_RESOLUTION = timedelta(minutes=5)


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class ApiTokenService:
    """Researcher export API tokens. Tokens are revoked, never deleted, so admins keep an audit trail."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, obj_in: ApiTokenCreate) -> ApiToken:
        async with self.db.begin():
            token = ApiToken(
                id=uuid7(),
                token_hash=obj_in.token_hash,
                token_hint=obj_in.token_hint,
                owner_email=_normalize_email(obj_in.owner_email),
                name=obj_in.name,
                created_at=datetime.now(UTC),
            )
            self.db.add(token)
            await self.db.flush()
            return token

    async def list(self, owner_email: str | None, include_revoked: bool) -> Sequence[ApiToken]:
        stmt = select(ApiToken).order_by(ApiToken.created_at.desc())
        if owner_email is not None:
            stmt = stmt.where(ApiToken.owner_email == _normalize_email(owner_email))
        if not include_revoked:
            stmt = stmt.where(ApiToken.revoked_at.is_(None))
        return (await self.db.scalars(stmt)).all()

    async def verify(self, token_hash: str) -> ApiToken:
        """Return the active token with this hash and record its use."""
        async with self.db.begin():
            token = await self.db.scalar(
                select(ApiToken).where(ApiToken.token_hash == token_hash, ApiToken.revoked_at.is_(None))
            )
            if token is None:
                raise EntityNotFoundError("ApiToken", "<hash>")
            now = datetime.now(UTC)
            last_used = token.last_used_at
            if last_used is not None and last_used.tzinfo is None:
                last_used = last_used.replace(tzinfo=UTC)
            if last_used is None or now - last_used > LAST_USED_RESOLUTION:
                token.last_used_at = now
            return token

    async def revoke(self, id: UUID, revoked_by: str) -> ApiToken:
        async with self.db.begin():
            token = await self.db.get(ApiToken, id)
            if token is None:
                raise EntityNotFoundError("ApiToken", id)
            if token.revoked_at is None:
                token.revoked_at = datetime.now(UTC)
                token.revoked_by = _normalize_email(revoked_by)
            return token
