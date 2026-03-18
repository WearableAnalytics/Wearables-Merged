from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from fastapi.params import Depends as FastAPIDepends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenPayload, decode_token
from app.db.influx.client import client as global_influx_client
from app.db.influx.repos.telemetry_repo import TelemetryRepo
from app.db.postgres.engine import AsyncSessionLocal
from app.services.telemetry_service import TelemetryService

_bearer = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> TokenPayload:
    """Validate the Bearer JWT. Used as a dependency on all protected endpoints."""
    return decode_token(credentials.credentials)


# Convenience alias: add `_current_user: CurrentUser` to any endpoint to require auth
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


# Postgres
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


# InfluxDB
async def get_influx_client() -> InfluxDBClientAsync:
    return global_influx_client


async def get_telemetry_repo(client: Annotated[InfluxDBClientAsync, Depends(get_influx_client)]) -> TelemetryRepo:
    return TelemetryRepo(client=client)


async def get_telemetry_service(repo: Annotated[TelemetryRepo, Depends(get_telemetry_repo)]) -> TelemetryService:
    return TelemetryService(repo=repo)
