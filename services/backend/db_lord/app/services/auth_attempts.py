"""Shared fixed-window limits; keys are HMAC digests, never email addresses."""

from datetime import UTC, datetime

from sqlalchemy import case, delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import AuthAttempt
from app.services.control_authority import authority_transaction

LIMITS = {"client": 100, "login": 10, "register": 5, "verify": 30}
WINDOW = 900


class AuthAttempts:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def admit(self, kind: str, key_hash: str) -> dict:
        now = int(datetime.now(UTC).timestamp())
        bucket = now - now % WINDOW
        insert = pg_insert if self.db.get_bind().dialect.name == "postgresql" else sqlite_insert
        async with authority_transaction(self.db):
            row = insert(AuthAttempt).values(kind=kind, key_hash=key_hash, window_start=bucket, attempts=1)
            statement = row.on_conflict_do_update(
                index_elements=[AuthAttempt.kind, AuthAttempt.key_hash, AuthAttempt.window_start],
                set_={
                    "attempts": case(
                        (AuthAttempt.attempts <= LIMITS[kind], AuthAttempt.attempts + 1), else_=LIMITS[kind] + 1
                    )
                },
            ).returning(AuthAttempt.attempts)
            attempts = await self.db.scalar(statement)
            assert isinstance(attempts, int)
            old = (
                select(AuthAttempt.kind, AuthAttempt.key_hash, AuthAttempt.window_start)
                .where(AuthAttempt.window_start < bucket - WINDOW)
                .order_by(AuthAttempt.kind, AuthAttempt.key_hash, AuthAttempt.window_start)
                .limit(100)
                .with_for_update(skip_locked=True)
            )
            await self.db.execute(
                delete(AuthAttempt).where(
                    tuple_(AuthAttempt.kind, AuthAttempt.key_hash, AuthAttempt.window_start).in_(old)
                )
            )
            return {"allowed": attempts <= LIMITS[kind], "retry_after": WINDOW - now % WINDOW}
