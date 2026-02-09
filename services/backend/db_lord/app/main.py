from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, ORJSONResponse
from fastapi_pagination import add_pagination
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from sqlalchemy import text
from sqlalchemy.exc import InvalidRequestError

from app.api.dependencies import PgSessionDep
from app.api.routers import cases, contexts, devices, fhir_mapping, graphql, patients, telemetry, wearables
from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, DuplicateEntityError, EntityNotFoundError
from app.db.postgres.engine import engine as pg_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    # Start Postgres
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql("SELECT 1")
    # Start InfluxDB
    influx_client = InfluxDBClientAsync(
        url=settings.INFLUX_URL,
        token=settings.INFLUX_TOKEN,
        org=settings.INFLUX_ORG,
    )
    if not await influx_client.ping():
        await influx_client.close()
        raise ConnectionError("Failed to ping to InfluxDB during startup.")
    app.state.influx_client = influx_client
    try:
        yield
    finally:
        # Shutdown InfluxDB client
        with suppress(Exception):
            await app.state.influx_client.close()
        # Dispose Postgres engine
        with suppress(Exception):
            await pg_engine.dispose()


app = FastAPI(title="Wearables Backend", lifespan=lifespan, default_response_class=ORJSONResponse)


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
        influx_client: InfluxDBClientAsync = request.app.state.influx_client
        if await influx_client.ping():
            health_status["influx"] = True
        else:
            health_status["status"] = "unhealthy"
    except Exception:
        health_status["status"] = "unhealthy"

    if health_status["status"] == "unhealthy":
        return ORJSONResponse(status_code=503, content=health_status)
    return ORJSONResponse(status_code=200, content=health_status)


# Centralized exception handlers
@app.exception_handler(InvalidRequestError)
async def lazy_load_handler(request: Request, exc: InvalidRequestError) -> JSONResponse:
    """Handle lazy='raise' exceptions from SQLAlchemy relationships.

    Instead of crashing with a 500, return a proper error message.
    """
    error_msg = str(exc)
    if "lazy='raise'" in error_msg or "is not available due to lazy" in error_msg:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Relationship not loaded.",
                "error_type": "LazyLoadError",
                "technical_details": error_msg,
            },
        )
    # Re-raise other InvalidRequestErrors
    raise exc


@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(BadRequestError)
async def bad_request_handler(request: Request, exc: BadRequestError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.detail})


@app.exception_handler(DuplicateEntityError)
async def duplicate_entity_handler(request: Request, exc: DuplicateEntityError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(ConflictError)
async def conflict_error_handler(request: Request, exc: ConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


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
