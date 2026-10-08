import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from influxdb_client.rest import ApiException as InfluxApiException
from sqlalchemy.exc import IntegrityError, InvalidRequestError, OperationalError, SQLAlchemyError

from app.api.errors import (
    bad_request_handler,
    conflict_error_handler,
    duplicate_entity_handler,
    entity_not_found_handler,
    influx_api_exception_handler,
    postgres_integrity_error_handler,
    postgres_unavailable_handler,
    sqlalchemy_invalid_request_handler,
)
from app.api.routers import api_tokens, cases, contexts, devices, fhir_mapping, graphql, patients, telemetry, wearables
from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, DuplicateEntityError, EntityNotFoundError
from app.core.json_types import JsonObject
from app.db.influx.client import create_influx_client
from app.db.influx.telemetry import TelemetryRepo
from app.db.postgres.engine import engine as pg_engine
from app.services.telemetry_service import TelemetryService

# There currently isnt any real logging implemented
logger = logging.getLogger(__name__)


def _max_graphql_db_concurrency() -> int:
    max_pool_capacity = max(1, settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW)
    return max(1, min(settings.GRAPHQL_DB_MAX_CONCURRENCY, max_pool_capacity))


async def _probe_influx_http() -> bool:
    """custom ping cause InfluxDBClientAsync.ping() spams logs with stack traces
    instead of just returning False when influx is not reachable."""
    try:
        async with httpx.AsyncClient(timeout=settings.HEALTHCHECK_INFLUX_TIMEOUT_MS / 1000) as client:
            response = await client.get(f"{settings.INFLUX_URL.rstrip('/')}/ping")
        return response.is_success
    except httpx.HTTPError, OSError:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    max_conn_per_pod = settings.WEB_CONCURRENCY * (settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW)
    if max_conn_per_pod > settings.DB_POOL_WARN_THRESHOLD:
        logger.warning(
            "Configured DB pool budget is high for a single pod: workers=%s, pool_size=%s, max_overflow=%s, "
            "max_conn_per_pod=%s (warn_threshold=%s).",
            settings.WEB_CONCURRENCY,
            settings.DB_POOL_SIZE,
            settings.DB_MAX_OVERFLOW,
            max_conn_per_pod,
            settings.DB_POOL_WARN_THRESHOLD,
        )

    influx_client = getattr(app.state, "influx_client", None)
    owns_influx = influx_client is None
    if owns_influx:
        async with pg_engine.begin() as conn:
            await conn.exec_driver_sql("SELECT 1")

        influx_client = create_influx_client()
        if not await _probe_influx_http():
            await influx_client.close()
            raise ConnectionError("Failed to ping to InfluxDB during startup.")
        app.state.influx_client = influx_client

    owns_telemetry_service = not hasattr(app.state, "telemetry_service")
    if owns_telemetry_service:
        app.state.telemetry_service = TelemetryService(TelemetryRepo(app.state.influx_client))

    app.state.graphql_db_semaphore = asyncio.Semaphore(_max_graphql_db_concurrency())

    try:
        yield
    finally:
        if hasattr(app.state, "graphql_db_semaphore"):
            del app.state.graphql_db_semaphore
        # TelemetryService is special cause both rest and graphql use it and influx client isn't created per request
        if owns_telemetry_service:
            del app.state.telemetry_service

        if owns_influx:
            await app.state.influx_client.close()

        await pg_engine.dispose()


async def _check_postgres_readiness() -> bool:
    try:
        async with asyncio.timeout(settings.HEALTHCHECK_DB_TIMEOUT_MS / 1000):
            async with pg_engine.connect() as conn:
                await conn.exec_driver_sql("SELECT 1")
        return True
    except TimeoutError, SQLAlchemyError, OSError:
        return False


async def _check_influx_readiness(request: Request) -> bool:
    client = getattr(request.app.state, "influx_client", None)
    if client is None:
        return False
    return await _probe_influx_http()


async def livez() -> JSONResponse:
    return JSONResponse(content={"status": "healthy"})


async def readyz(request: Request) -> JSONResponse:
    postgres_ok, influx_ok = await asyncio.gather(
        _check_postgres_readiness(),
        _check_influx_readiness(request),
    )
    all_ready = postgres_ok and influx_ok
    status_code = 200 if all_ready else 503
    payload: JsonObject = {
        "status": "healthy" if all_ready else "unhealthy",
        "postgres": postgres_ok,
        "influx": influx_ok,
    }
    return JSONResponse(status_code=status_code, content=payload)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Wearables Backend",
        lifespan=lifespan,
    )

    app.add_api_route("/livez", livez, methods=["GET"], tags=["health"])
    app.add_api_route("/readyz", readyz, methods=["GET"], tags=["health"])

    exception_handlers = (
        (EntityNotFoundError, entity_not_found_handler),
        (DuplicateEntityError, duplicate_entity_handler),
        (BadRequestError, bad_request_handler),
        (ConflictError, conflict_error_handler),
        (IntegrityError, postgres_integrity_error_handler),
        (OperationalError, postgres_unavailable_handler),
        (InvalidRequestError, sqlalchemy_invalid_request_handler),
        (InfluxApiException, influx_api_exception_handler),
    )

    # exception handler: Pylance complains, but afaik FastAPI guarantees these are called with matching exception types.
    for exc_type, handler in exception_handlers:
        app.add_exception_handler(exc_type, handler)  # type: ignore[arg-type]

    app.include_router(patients.router, prefix="/patients", tags=["patients"])
    app.include_router(cases.router, prefix="/cases", tags=["cases"])
    app.include_router(devices.router, prefix="/devices", tags=["devices"])
    app.include_router(wearables.router, prefix="/wearables", tags=["wearables"])
    app.include_router(contexts.router, prefix="/contexts", tags=["contexts"])
    app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
    app.include_router(fhir_mapping.router, prefix="/fhir-mappings", tags=["fhir-mappings"])
    app.include_router(api_tokens.router, prefix="/api-tokens", tags=["api-tokens"])
    app.include_router(graphql.router, prefix="/graphql", tags=["graphql"])
    add_pagination(app)
    return app


app = create_app()
