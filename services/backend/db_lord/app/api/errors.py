from asyncpg.exceptions import (
    CheckViolationError,
    ExclusionViolationError,
    ForeignKeyViolationError,
    NotNullViolationError,
    UniqueViolationError,
)
from fastapi import Request, status
from fastapi.responses import JSONResponse
from influxdb_client.rest import ApiException as InfluxApiException
from sqlalchemy.exc import DBAPIError, IntegrityError, InvalidRequestError, OperationalError

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, DuplicateEntityError, EntityNotFoundError
from app.core.json_types import JsonObject, JsonValue

type IntegrityMapping = tuple[int, str, str]

INTEGRITY_BY_EXCEPTION: tuple[tuple[type[Exception], IntegrityMapping], ...] = (
    (
        UniqueViolationError,
        (status.HTTP_409_CONFLICT, "unique_violation", "Conflict: Resource already exists."),
    ),
    (
        ExclusionViolationError,
        (status.HTTP_409_CONFLICT, "exclusion_violation", "Conflict: Data overlaps with an existing record."),
    ),
    (
        ForeignKeyViolationError,
        (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "foreign_key_violation",
            "Invalid reference: The referenced entity does not exist.",
        ),
    ),
    (
        NotNullViolationError,
        (
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "not_null_violation",
            "Missing data: A required field was missing.",
        ),
    ),
    (
        CheckViolationError,
        (status.HTTP_400_BAD_REQUEST, "check_violation", "Invalid data: Database constraint violation."),
    ),
)

DEFAULT_INTEGRITY_ERROR: IntegrityMapping = (
    status.HTTP_400_BAD_REQUEST,
    "integrity_error",
    "Database integrity error.",
)


def _json_error(status_code: int, code: str, detail: str, **extra: JsonValue) -> JSONResponse:
    payload: JsonObject = {"detail": detail, "code": code}
    payload.update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _unwrap_asyncpg_exc(err: DBAPIError) -> Exception:
    """Unwrap SQLAlchemy asyncpg adapter errors to the observed underlying asyncpg exception."""
    orig = getattr(err, "orig", None)
    if not isinstance(orig, Exception):
        return err

    # asyncpg exceptions are wrapped at orig.__cause__.
    cause = getattr(orig, "__cause__", None)
    if isinstance(cause, Exception):
        return cause
    return orig


async def entity_not_found_handler(_: Request, exc: EntityNotFoundError) -> JSONResponse:
    return _json_error(
        status.HTTP_404_NOT_FOUND,
        "not_found",
        str(exc),
        entity_type=exc.entity_type,
    )


async def duplicate_entity_handler(_: Request, exc: DuplicateEntityError) -> JSONResponse:
    return _json_error(
        status.HTTP_409_CONFLICT,
        "duplicate_entity",
        str(exc),
        entity_type=exc.entity_type,
    )


async def bad_request_handler(_: Request, exc: BadRequestError) -> JSONResponse:
    return _json_error(status.HTTP_400_BAD_REQUEST, "bad_request", exc.detail)


async def conflict_error_handler(_: Request, exc: ConflictError) -> JSONResponse:
    return _json_error(status.HTTP_409_CONFLICT, "conflict", exc.detail)


async def postgres_unavailable_handler(_: Request, exc: OperationalError) -> JSONResponse:
    is_disconnect = getattr(exc, "connection_invalidated", False)

    extra: JsonObject = {}
    if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS:
        extra["technical_detail"] = str(_unwrap_asyncpg_exc(exc))

    return _json_error(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="db_unavailable",
        detail="Database service is currently unavailable.",
        disconnected=is_disconnect,
        **extra,
    )


async def postgres_integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
    e = _unwrap_asyncpg_exc(exc)

    http_status, app_code, message = next(
        (mapping for exc_type, mapping in INTEGRITY_BY_EXCEPTION if isinstance(e, exc_type)), DEFAULT_INTEGRITY_ERROR
    )

    extra: JsonObject = {}
    constraint = getattr(e, "constraint_name", None)
    if constraint:
        extra["constraint"] = constraint

    column = getattr(e, "column_name", None)
    if column:
        extra["field"] = column

    if settings.ERRORS_INCLUDE_TECHNICAL_DETAILS:
        extra["technical_detail"] = getattr(e, "detail", None) or str(e)

    return _json_error(http_status, app_code, message, **extra)


# SQLAlchemy InvalidRequestError (lazy='raise')
async def sqlalchemy_invalid_request_handler(_: Request, exc: InvalidRequestError) -> JSONResponse:
    msg = str(exc)
    if "lazy='raise'" in msg or "is not available due to lazy" in msg:
        return _json_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "lazy_load_error",
            "Internal Server Error: Relationship not loaded.",
        )
    raise exc


# InfluxDB handler
async def influx_api_exception_handler(_: Request, exc: InfluxApiException) -> JSONResponse:
    s = getattr(exc, "status", None)
    body = getattr(exc, "body", None)
    reason = getattr(exc, "reason", None)

    # Down/unreachable/unknown -> 503
    if s is None or s == 0 or (isinstance(s, int) and s >= 500):
        extra: JsonObject = {}
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
