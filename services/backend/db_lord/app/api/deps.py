from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import AsyncSessionLocal


async def get_db_read() -> AsyncGenerator[AsyncSession]:
    """Read-only DB session for GET endpoints (no commit/rollback)."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Transactional DB session for write endpoints (commits on success, rollbacks on error)."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
