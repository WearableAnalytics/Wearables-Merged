from __future__ import annotations

import base64
import csv
import io
import json
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, StreamingResponse

from .auth import Principal, must_pseudonymize, require_export_access
from .clients import create_db_lord_client
from .db_lord_api import DbLordApi
from .export_response import EXPORT_HEADERS, prepare_export
from .fhir import ObservationBuilder
from .points import iter_readings, read_page, reading_key
from .privacy import ExportPrivacy
from .reconciliation import Mode, bounded_readings, reconcile
from .schemas import MeasurementPage, MeasurementPoint, MeasurementType, TelemetryPoint
from .settings import settings

PLATFORM_NAME = "Charité Wearables platform"
DOCS_TITLE = f"Extraction API | {PLATFORM_NAME}"
# Inlined so the docs pages show the platform's W mark without another authenticated request.
FAVICON_URL = (
    "data:image/png;base64,"
    + base64.b64encode((Path(__file__).parent / "static" / "favicon-32.png").read_bytes()).decode()
)

DESCRIPTION = """
Export wearable measurements stored on the Charité Wearables platform.

**Authentication.** The API is served by the platform at `/api/extraction`.
Either be logged in to the web app as an admin, practitioner or researcher (the session cookie
is sent automatically, also from this page), or, as a researcher or admin, create a personal API
token on the web app's *API Access* page and send it as `Authorization: Bearer <token>`.

**Pseudonymization.** Researchers always get pseudonymized data: fresh patient pseudonyms per
response, only known numeric measurements, no extra fields. Admins and practitioners get the
original data unless they pass `pseudonymize=true`.

**Time range.** `start` defaults to 2020-01-01, so omitting it exports all data.
`end` is exclusive. Times without a timezone are read as UTC.

**Patients.** `patient_id` is the db-lord patient id (the id the app syncs with).
Repeated copies of the same reading are removed from every response.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = create_db_lord_client()
    app.state.db_lord_client = client
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(
    title=DOCS_TITLE,
    version="0.2.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    root_path=settings.root_path,
    docs_url=None,
    redoc_url=None,
)


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    # Documents the BFF's auth so Swagger UI offers an "Authorize" button for the token.
    schema.setdefault("components", {})["securitySchemes"] = {
        "researcherToken": {
            "type": "http",
            "scheme": "bearer",
            "description": "Personal API token from the web app's API Access page (starts with wrt_).",
        },
        "session": {"type": "apiKey", "in": "cookie", "name": "jwt", "description": "Web app login session."},
    }
    schema["security"] = [{"researcherToken": []}, {"session": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


def openapi_url(request: Request) -> str:
    return request.scope.get("root_path", "").rstrip("/") + app.openapi_url


@app.get("/docs", include_in_schema=False)
async def swagger_ui(request: Request) -> HTMLResponse:
    return get_swagger_ui_html(openapi_url=openapi_url(request), title=DOCS_TITLE, swagger_favicon_url=FAVICON_URL)


@app.get("/redoc", include_in_schema=False)
async def redoc(request: Request) -> HTMLResponse:
    return get_redoc_html(openapi_url=openapi_url(request), title=DOCS_TITLE, redoc_favicon_url=FAVICON_URL)


def get_db_lord_api(request: Request) -> DbLordApi:
    return DbLordApi(request.app.state.db_lord_client)


DbLordDep = Annotated[DbLordApi, Depends(get_db_lord_api)]
# Added to every /v1 route: only callers the BFF signed with an export role get data.
EXPORT_ACCESS = [Depends(require_export_access)]
ExportCaller = Annotated[Principal, Depends(require_export_access)]


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


Pseudonymize = Annotated[
    bool,
    Query(
        description="Use fresh patient pseudonyms per response. Only known numeric measurements are included; "
        "extra fields and custom FHIR mappings are excluded. Timestamps are preserved. Not anonymization. "
        "Always on for researchers, whatever is passed here."
    ),
]


async def pseudonymized(readings: AsyncIterator[TelemetryPoint], privacy: ExportPrivacy):
    async with aclosing(readings):
        async for point in readings:
            if (clean := privacy.project(point)) is not None:
                yield clean


class ReadingFilter:
    def __init__(
        self,
        measurement: Annotated[
            str | None,
            Query(description="Measurement type, see `/v1/measurements/types`. Omit for all types."),
        ] = None,
        patient_id: Annotated[str | None, Query(description="db-lord patient id. Omit for all patients.")] = None,
        start: Annotated[
            datetime | None, Query(description="Inclusive start. Defaults to 2020-01-01T00:00:00Z.")
        ] = None,
        end: Annotated[datetime | None, Query(description="Exclusive end. Defaults to now.")] = None,
        source_key: Annotated[
            str | None, Query(min_length=1, max_length=64, description="One source-key from the source policy view.")
        ] = None,
    ):
        self.measurement = measurement or None
        self.patient_id = patient_id or None
        self.start = as_utc(start) or settings.default_start
        self.end = as_utc(end)
        self.source_key = source_key
        if self.end is not None and self.start >= self.end:
            raise HTTPException(status_code=422, detail="start must be before end")

    def readings(self, api: DbLordApi):
        return iter_readings(
            api, measurement=self.measurement, start=self.start, end=self.end, patient_id=self.patient_id,
            source_key=self.source_key,
        )


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get("/v1/measurements/reconciled", tags=["measurements"], dependencies=EXPORT_ACCESS,
         summary="Compare sources or select one source for a measurement",
         description="Admins and practitioners only: the source details (writer, name, device) can identify a "
         "patient, and the request needs the real patient id, so researchers get 403.")
async def get_reconciled_measurements(
    api: DbLordDep,
    caller: ExportCaller,
    patient_id: Annotated[str, Query(min_length=1, max_length=128)],
    measurement: Annotated[str, Query(min_length=1, max_length=128)],
    start: datetime,
    end: datetime,
    mode: Mode = "separate",
    source_key: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    source_priority: Annotated[list[str] | None, Query(max_length=32)] = None,
):
    if must_pseudonymize(caller):
        raise HTTPException(status_code=403, detail="Source reconciliation is not available with pseudonymized access")
    points = await bounded_readings(api, patient_id=patient_id, measurement=measurement, start=start, end=end)
    return reconcile(points, measurement=measurement, start=start, end=end, mode=mode,
                     source_key=source_key, priorities=source_priority)


@app.get(
    "/v1/measurements/types",
    response_model=list[MeasurementType],
    tags=["measurements"],
    dependencies=EXPORT_ACCESS,
    summary="List measurement types",
)
async def list_measurement_types(api: DbLordDep):
    measurements = await api.list_measurements()
    return [
        MeasurementType(
            measurement=m["measurement"],
            field_keys=[f for f in m.get("fieldKeys", []) if f != "t_ingested"],
        )
        for m in measurements
    ]


@app.get(
    "/v1/measurements",
    response_model=MeasurementPage,
    tags=["measurements"],
    dependencies=EXPORT_ACCESS,
    summary="Read measurements page by page",
    description="Newest readings first. Pass `next_end` as `end` to get the next page until `has_more` is false. "
    "A page can hold slightly more than `limit` readings so that no timestamp is split across pages. "
    "Pseudonymized pages (always for researchers) use fresh pseudonyms per page, so pages cannot be joined "
    "by patient.",
)
async def get_measurements(
    filters: Annotated[ReadingFilter, Depends()],
    api: DbLordDep,
    caller: ExportCaller,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
    pseudonymize: Pseudonymize = False,
):
    readings = filters.readings(api)
    if pseudonymize or must_pseudonymize(caller):
        readings = pseudonymized(readings, ExportPrivacy())
    async with aclosing(readings):
        return await read_page(readings, limit)


CSV_COLUMNS = ["timestamp", "measurement", "patient_id", "category", "value", "fields"]


def csv_line(values: list) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(values)
    return buffer.getvalue()


@app.get(
    "/v1/measurements/export.csv",
    tags=["export"],
    dependencies=EXPORT_ACCESS,
    summary="Export measurements as CSV",
    description="Streams all matching readings, newest first. `fields` holds any extra fields as JSON.",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file", "headers": EXPORT_HEADERS}},
)
async def export_measurements_csv(
    filters: Annotated[ReadingFilter, Depends()],
    api: DbLordDep,
    caller: ExportCaller,
    pseudonymize: Pseudonymize = False,
):
    pseudonymize = pseudonymize or must_pseudonymize(caller)
    privacy = ExportPrivacy() if pseudonymize else None

    async def rows() -> AsyncIterator[str]:
        yield csv_line(CSV_COLUMNS)
        async with aclosing(filters.readings(api)) as readings:
            async for point in readings:
                if privacy is not None:
                    point = privacy.project(point)
                    if point is None:
                        continue
                row = MeasurementPoint.from_telemetry(point)
                yield csv_line(
                    [
                        row.timestamp.isoformat(),
                        row.measurement,
                        row.patient_id or "",
                        row.category or "",
                        "" if row.value is None else row.value,
                        ""
                        if privacy is not None
                        else (json.dumps(row.fields, ensure_ascii=False) if row.fields else ""),
                    ]
                )

    if privacy is not None:
        return await prepare_export(rows(), privacy, media_type="text/csv", suffix="csv")

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="measurements-pseudonymized.csv"'
            if pseudonymize
            else 'attachment; filename="measurements.csv"',
            "Cache-Control": "no-store",
        },
    )


@app.get(
    "/v1/measurements/export.fhir",
    tags=["export"],
    dependencies=EXPORT_ACCESS,
    summary="Export measurements as a FHIR Bundle",
    description="Streams a FHIR R4 `collection` Bundle with one Observation per reading. Readings whose type has "
    "no FHIR mapping are left out.",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"application/fhir+json": {}},
            "description": "FHIR Bundle",
            "headers": EXPORT_HEADERS,
        }
    },
)
async def export_measurements_fhir(
    filters: Annotated[ReadingFilter, Depends()],
    api: DbLordDep,
    caller: ExportCaller,
    pseudonymize: Pseudonymize = False,
):
    pseudonymize = pseudonymize or must_pseudonymize(caller)
    builder = ObservationBuilder(api)
    privacy = ExportPrivacy() if pseudonymize else None

    async def bundle() -> AsyncIterator[str]:
        yield '{"resourceType":"Bundle","type":"collection","entry":['
        first = True
        async with aclosing(filters.readings(api)) as readings:
            async for point in readings:
                if privacy is not None:
                    point = privacy.project(point)
                    if point is None:
                        continue
                observation = privacy.observation(point) if privacy is not None else await builder.build(point)
                if observation is None:
                    continue
                if pseudonymize:
                    # Fresh ids: stable ones would let downloads be joined.
                    resource_id = str(uuid4())
                    observation.pop("device", None)
                else:
                    reading = json.dumps(
                        [point.timestamp.isoformat(), reading_key(point)], sort_keys=True, default=str
                    )
                    resource_id = str(uuid5(NAMESPACE_URL, reading))
                observation["id"] = resource_id
                entry = {"fullUrl": f"urn:uuid:{resource_id}", "resource": observation}
                yield ("" if first else ",") + json.dumps(entry, ensure_ascii=False)
                first = False
        yield "]}"

    if privacy is not None:
        return await prepare_export(bundle(), privacy, media_type="application/fhir+json", suffix="fhir.json")

    return StreamingResponse(
        bundle(),
        media_type="application/fhir+json",
        headers={
            "Content-Disposition": 'attachment; filename="measurements-pseudonymized.fhir.json"'
            if pseudonymize
            else 'attachment; filename="measurements.fhir.json"',
            "Cache-Control": "no-store",
        },
    )
