from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse
from fastapi_pagination import add_pagination
from influxdb_client.rest import ApiException as InfluxApiException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InvalidRequestError, OperationalError

from app.api.dependencies import PgSessionDep
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
from app.api.routers import cases, contexts, devices, fhir_mapping, graphql, patients, telemetry, wearables
from app.core.exceptions import BadRequestError, ConflictError, DuplicateEntityError, EntityNotFoundError
from app.db.influx.client import create_influx_client
from app.db.influx.repos.telemetry_repo import TelemetryRepo
from app.db.postgres.engine import engine as pg_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Start Postgres
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql("SELECT 1")
    # Start InfluxDB
    influx_client = create_influx_client()
    if not await influx_client.ping():
        await influx_client.close()
        raise ConnectionError("Failed to ping to InfluxDB during startup.")
    app.state.influx_client = influx_client
    app.state.telemetry_repo = TelemetryRepo(influx_client)
    try:
        yield
    finally:
        # Shutdown InfluxDB client
        with suppress(Exception):
            await app.state.influx_client.close()
        with suppress(Exception):
            del app.state.telemetry_repo
        # Dispose Postgres engine
        with suppress(Exception):
            await pg_engine.dispose()


app = FastAPI(
    title="Wearables Backend",
    lifespan=lifespan,
    default_response_class=ORJSONResponse,
)


@app.get("/health", tags=["health"])
async def health_check(request: Request, db: PgSessionDep) -> ORJSONResponse:
    health_status = {
        "status": "healthy",
        "postgres": False,
        "influx": False,
    }
    # Check Postgres
    try:
        await db.execute(text("SELECT 1"))
        health_status["postgres"] = True
    except Exception:
        health_status["status"] = "unhealthy"
    # Check InfluxDB
    try:
        influx_client = request.app.state.influx_client
        if await influx_client.ping():
            health_status["influx"] = True
        else:
            health_status["status"] = "unhealthy"
    except Exception:
        health_status["status"] = "unhealthy"

    if health_status["status"] == "unhealthy":
        return ORJSONResponse(status_code=503, content=health_status)
    return ORJSONResponse(status_code=200, content=health_status)


# exception handlers
# Pylance complains but afaik FastAPI gurantees these will be called with the correct exception types so should be fine
app.add_exception_handler(EntityNotFoundError, entity_not_found_handler)  # type: ignore
app.add_exception_handler(DuplicateEntityError, duplicate_entity_handler)  # type: ignore
app.add_exception_handler(BadRequestError, bad_request_handler)  # type: ignore
app.add_exception_handler(ConflictError, conflict_error_handler)  # type: ignore
# Pg
app.add_exception_handler(IntegrityError, postgres_integrity_error_handler)  # type: ignore
app.add_exception_handler(OperationalError, postgres_unavailable_handler)  # type: ignore
app.add_exception_handler(InvalidRequestError, sqlalchemy_invalid_request_handler)  # type: ignore
# InfluxDB
app.add_exception_handler(InfluxApiException, influx_api_exception_handler)  # type: ignore


# Router registrations
app.include_router(patients.router, prefix="/patients", tags=["patients"])
app.include_router(cases.router, prefix="/cases", tags=["cases"])
app.include_router(devices.router, prefix="/devices", tags=["devices"])
app.include_router(wearables.router, prefix="/wearables", tags=["wearables"])
app.include_router(contexts.router, prefix="/contexts", tags=["contexts"])
app.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
app.include_router(fhir_mapping.router, prefix="/fhir-mappings", tags=["fhir-mappings"])
app.include_router(graphql.router, prefix="/graphql", tags=["graphql"])
add_pagination(app)
