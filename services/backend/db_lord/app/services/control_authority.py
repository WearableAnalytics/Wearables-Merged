"""Bounded transactions for persistent account authority."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def authority_transaction(db: AsyncSession) -> AsyncIterator[None]:
    try:
        async with asyncio.timeout(5), db.begin():
            if db.get_bind().dialect.name == "postgresql":
                await db.execute(text("SET LOCAL lock_timeout = '1500ms'"))
                await db.execute(text("SET LOCAL statement_timeout = '4000ms'"))
            yield
    except TimeoutError:
        raise HTTPException(503, "CONTROL_COMMAND_UNAVAILABLE") from None
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) in {"55P03", "57014", "40001"}:
            raise HTTPException(503, "CONTROL_COMMAND_UNAVAILABLE") from None
        raise
