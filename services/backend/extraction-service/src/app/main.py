from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import NAMESPACE_URL, uuid5

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse

from .clients import create_db_lord_client
from .db_lord_api import DbLordApi
from .fhir import ObservationBuilder
from .points import iter_readings, read_page
from .schemas import MeasurementPage, MeasurementPoint, MeasurementType
from .settings import settings

DESCRIPTION = """
Export wearable measurements stored on the Wearables platform.

**Authentication.** The API is served through the Wearables BFF at `/api/extraction`.
Either be logged in to the web app as a researcher or admin (the session cookie is sent
automatically, also from this page), or send the researcher API token from the web app's
*API Access* page as `Authorization: Bearer <token>`.

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
    title="Wearables Extraction API",
    version="0.2.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    root_path=settings.root_path,
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
            "description": "Researcher API token from the web app's API Access page.",
        },
        "session": {"type": "apiKey", "in": "cookie", "name": "jwt", "description": "Web app login session."},
    }
    schema["security"] = [{"researcherToken": []}, {"session": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


def get_db_lord_api(request: Request) -> DbLordApi:
    return DbLordApi(request.app.state.db_lord_client)


DbLordDep = Annotated[DbLordApi, Depends(get_db_lord_api)]


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


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
    ):
        self.measurement = measurement or None
        self.patient_id = patient_id or None
        self.start = as_utc(start) or settings.default_start
        self.end = as_utc(end)
        if self.end is not None and self.start >= self.end:
            raise HTTPException(status_code=422, detail="start must be before end")

    def readings(self, api: DbLordApi):
        return iter_readings(
            api, measurement=self.measurement, start=self.start, end=self.end, patient_id=self.patient_id
        )


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.get(
    "/v1/measurements/types",
    response_model=list[MeasurementType],
    tags=["measurements"],
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
    summary="Read measurements page by page",
    description="Newest readings first. Pass `next_end` as `end` to get the next page until `has_more` is false. "
    "A page can hold slightly more than `limit` readings so that no timestamp is split across pages.",
)
async def get_measurements(
    filters: Annotated[ReadingFilter, Depends()],
    api: DbLordDep,
    limit: Annotated[int, Query(ge=1, le=10_000)] = 1000,
):
    async with aclosing(filters.readings(api)) as readings:
        return await read_page(readings, limit)


CSV_COLUMNS = ["timestamp", "measurement", "patient_id", "category", "value", "fields"]


def csv_line(values: list) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(values)
    return buffer.getvalue()


@app.get(
    "/v1/measurements/export.csv",
    tags=["export"],
    summary="Export measurements as CSV",
    description="Streams all matching readings, newest first. `fields` holds any extra fields as JSON.",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}, "description": "CSV file"}},
)
async def export_measurements_csv(
    filters: Annotated[ReadingFilter, Depends()],
    api: DbLordDep,
):

    async def rows() -> AsyncIterator[str]:
        yield csv_line(CSV_COLUMNS)
        async with aclosing(filters.readings(api)) as readings:
            async for point in readings:
                row = MeasurementPoint.from_telemetry(point)
                yield csv_line(
                    [
                        row.timestamp.isoformat(),
                        row.measurement,
                        row.patient_id or "",
                        row.category or "",
                        "" if row.value is None else row.value,
                        json.dumps(row.fields, ensure_ascii=False) if row.fields else "",
                    ]
                )

    return StreamingResponse(
        rows(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="measurements.csv"'},
    )


@app.get(
    "/v1/measurements/export.fhir",
    tags=["export"],
    summary="Export measurements as a FHIR Bundle",
    description="Streams a FHIR R4 `collection` Bundle with one Observation per reading. Readings whose type has "
    "no FHIR mapping are left out.",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/fhir+json": {}}, "description": "FHIR Bundle"}},
)
async def export_measurements_fhir(
    filters: Annotated[ReadingFilter, Depends()],
    api: DbLordDep,
):
    builder = ObservationBuilder(api)

    async def bundle() -> AsyncIterator[str]:
        yield '{"resourceType":"Bundle","type":"collection","entry":['
        first = True
        async with aclosing(filters.readings(api)) as readings:
            async for point in readings:
                observation = await builder.build(point)
                if observation is None:
                    continue
                reading = f"{point.patient_id}/{point.measurement}/{point.timestamp.isoformat()}"
                entry = {"fullUrl": f"urn:uuid:{uuid5(NAMESPACE_URL, reading)}", "resource": observation}
                yield ("" if first else ",") + json.dumps(entry, ensure_ascii=False)
                first = False
        yield "]}"

    return StreamingResponse(
        bundle(),
        media_type="application/fhir+json",
        headers={"Content-Disposition": 'attachment; filename="measurements.fhir.json"'},
    )
