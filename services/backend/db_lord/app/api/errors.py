from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.responses import ORJSONResponse
from influxdb_client.rest import ApiException as InfluxApiException
from sqlalchemy.exc import DBAPIError, IntegrityError, InvalidRequestError, OperationalError

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, DuplicateEntityError, EntityNotFoundError


def _json_error(status_code: int, code: str, detail: str, **extra: Any) -> ORJSONResponse:
    payload: dict[str, Any] = {"detail": detail, "code": code}
    payload.update(extra)
    return ORJSONResponse(status_code=status_code, content=payload)


# Domain handlers
async def entity_not_found_handler(_: Request, exc: EntityNotFoundError) -> ORJSONResponse:
    return _json_error(
        status.HTTP_404_NOT_FOUND,
        "not_found",
        str(exc),
        entity_type=exc.entity_type,
    )


async def duplicate_entity_handler(_: Request, exc: DuplicateEntityError) -> ORJSONResponse:
    return _json_error(
        status.HTTP_409_CONFLICT,
        "duplicate_entity",
        str(exc),
        entity_type=exc.entity_type,
    )


async def bad_request_handler(_: Request, exc: BadRequestError) -> ORJSONResponse:
    return _json_error(status.HTTP_400_BAD_REQUEST, "bad_request", exc.detail)


async def conflict_error_handler(_: Request, exc: ConflictError) -> ORJSONResponse:
    return _json_error(status.HTTP_409_CONFLICT, "conflict", exc.detail)


# SQLAlchemy/asyncpg IntegrityError handling
# Postgres SQLSTATE codes
PG_UNIQUE = "23505"
PG_FK = "23503"
PG_NOT_NULL = "23502"
PG_CHECK = "23514"
PG_EXCLUSION = "23P01"

PG_INTEGRITY_MAP: dict[str, tuple[int, str, str]] = {
    PG_UNIQUE: (status.HTTP_409_CONFLICT, "unique_violation", "Conflict: Resource already exists."),
    PG_EXCLUSION: (status.HTTP_409_CONFLICT, "exclusion_violation", "Conflict: Data overlaps with an existing record."),
    PG_FK: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "foreign_key_violation",
        "Invalid reference: The referenced entity does not exist.",
    ),
    PG_NOT_NULL: (
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "not_null_violation",
        "Missing data: A required field was missing.",
    ),
    PG_CHECK: (status.HTTP_400_BAD_REQUEST, "check_violation", "Invalid data: Database constraint violation."),
}


def _unwrap_asyncpg_exc(err: DBAPIError) -> Exception:
    """
    SQLAlchemy wraps driver exceptions. should just be driver_exception for asyncpg but check just in case
    """
    orig = getattr(err, "orig", None)
    driver_exc = getattr(orig, "driver_exception", None) if orig is not None else None

    if isinstance(driver_exc, Exception):
        return driver_exc
    if isinstance(orig, Exception):
        return orig
    return err


def _sqlstate(e: Exception) -> str | None:
    return getattr(e, "sqlstate", None)


def _constraint(e: Exception) -> str | None:
    return getattr(e, "constraint_name", None)


def _column(e: Exception) -> str | None:
    return getattr(e, "column_name", None)


def _detail(e: Exception) -> str | None:
    # asyncpg provides .detail for constraint violations
    return getattr(e, "detail", None)


async def postgres_unavailable_handler(_: Request, exc: OperationalError) -> ORJSONResponse:
    is_disconnect = getattr(exc, "connection_invalidated", False)

    extra: dict[str, Any] = {}
    if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS:
        extra["technical_detail"] = str(_unwrap_asyncpg_exc(exc))

    return _json_error(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="db_unavailable",
        detail="Database service is currently unavailable.",
        disconnected=is_disconnect,
        **extra,
    )


async def postgres_integrity_error_handler(_: Request, exc: IntegrityError) -> ORJSONResponse:
    e = _unwrap_asyncpg_exc(exc)

    code = _sqlstate(e)
    constraint = _constraint(e)
    column = _column(e)

    http_status, app_code, message = PG_INTEGRITY_MAP.get(
        code or "",
        (status.HTTP_400_BAD_REQUEST, "integrity_error", "Database integrity error."),
    )

    extra: dict[str, Any] = {}
    # Often useful without leaking too much technical detail
    if constraint:
        extra["constraint"] = constraint
    if column:
        extra["field"] = column

    if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS:
        extra["sqlstate"] = code
        extra["technical_detail"] = _detail(e) or str(e)

    return _json_error(http_status, app_code, message, **extra)


# SQLAlchemy InvalidRequestError (lazy='raise')
async def sqlalchemy_invalid_request_handler(_: Request, exc: InvalidRequestError) -> ORJSONResponse:
    msg = str(exc)
    if "lazy='raise'" in msg or "is not available due to lazy" in msg:
        return _json_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "lazy_load_error",
            "Internal Server Error: Relationship not loaded.",
        )
    raise exc


# InfluxDB handler
async def influx_api_exception_handler(_: Request, exc: InfluxApiException) -> ORJSONResponse:
    s = getattr(exc, "status", None)
    body = getattr(exc, "body", None)
    reason = getattr(exc, "reason", None)

    # Down/unreachable/unknown -> 503
    if s is None or s == 0 or (isinstance(s, int) and s >= 500):
        extra: dict[str, Any] = {}
        if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS:
            extra["message"] = str(reason) if reason else None
            extra["technical_detail"] = str(body) if body is not None else None

        return _json_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "influx_unavailable",
            "Telemetry storage service is currently unavailable.",
            **extra,
        )

    if s == 400:
        extra = {}
        if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS and body is not None:
            extra["technical_detail"] = str(body)

        return _json_error(
            status.HTTP_400_BAD_REQUEST,
            "influx_bad_request",
            "Invalid telemetry query.",
            **extra,
        )

    # Fallback
    status_code = s if isinstance(s, int) and 100 <= s <= 599 else status.HTTP_502_BAD_GATEWAY
    extra = {"message": str(reason) if reason else None}
    if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS and body is not None:
        extra["technical_detail"] = str(body)

    return _json_error(status_code, "influx_error", "Telemetry service error.", **extra)
