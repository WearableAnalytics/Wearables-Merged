from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import StreamingResponse

from .clients import create_db_lord_client
from .db_lord_api import DbLordApi
from .schemas import TelemetryPageResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = create_db_lord_client()
    app.state.db_lord_client = client
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="Extraction Service", version="0.1.0", lifespan=lifespan)


def get_db_lord_api(request: Request) -> DbLordApi:
    return DbLordApi(request.app.state.db_lord_client)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/measurements", response_model=TelemetryPageResponse)
async def get_measurements(
    measurement: str,
    start: datetime | None = None,
    end: datetime | None = None,
    page_size: int = Query(100, ge=1, le=5000),
    cursor: str | None = None,
    patient_id: str | None = None,
    device_id: str | None = None,
    case_id: str | None = None,
    api: DbLordApi = Depends(get_db_lord_api),
):
    return await api.read_telemetry(
        measurement=measurement,
        start=start,
        end=end,
        page_size=page_size,
        cursor=cursor,
        patient_id=patient_id,
        device_id=device_id,
        case_id=case_id,
    )


@app.get("/v1/measurements/export.csv")
async def export_measurements_csv(
    measurement: str,
    start: datetime | None = None,
    end: datetime | None = None,
    page_size: int = Query(5000, ge=1, le=5000),
    patient_id: str | None = None,
    device_id: str | None = None,
    case_id: str | None = None,
):
    async def row_iter():
        # CSV header includes minimal known columns; unknown field/tag values are serialized as JSON per-row.
        import json

        cursor: str | None = None
        yield "timestamp,measurement,patient_id,case_id,device_id,extra\n"
        async with create_db_lord_client() as client:
            api = DbLordApi(client)
            while True:
                page = await api.read_telemetry(
                    measurement=measurement,
                    start=start,
                    end=end,
                    page_size=page_size,
                    cursor=cursor,
                    patient_id=patient_id,
                    device_id=device_id,
                    case_id=case_id,
                )

                for item in page.items:
                    known = {
                        "timestamp": item.timestamp.isoformat(),
                        "measurement": item.measurement,
                        "patient_id": str(item.patient_id) if item.patient_id else "",
                        "case_id": str(item.case_id) if item.case_id else "",
                        "device_id": str(item.device_id) if item.device_id else "",
                    }
                    extra = item.model_dump(exclude=set(known.keys()), exclude_none=True)
                    # basic CSV escaping (quotes with double-quotes)
                    extra_s = json.dumps(extra, ensure_ascii=False).replace('"', '""')
                    yield (
                        f"{known['timestamp']},{known['measurement']},{known['patient_id']},"
                        f"{known['case_id']},{known['device_id']},\"{extra_s}\"\n"
                    )

                cursor = page.next_cursor
                if not cursor or not page.items:
                    break

    return StreamingResponse(row_iter(), media_type="text/csv")
