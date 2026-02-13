from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .schemas import TelemetryPageResponse


class DbLordApi:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def read_telemetry(
        self,
        *,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        page_size: int = 100,
        cursor: str | None = None,
        patient_id: str | None = None,
        device_id: str | None = None,
        case_id: str | None = None,
    ) -> TelemetryPageResponse:
        params: dict[str, Any] = {
            "measurement": measurement,
            "page_size": page_size,
        }
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()
        if cursor:
            params["cursor"] = cursor
        if patient_id:
            params["patient_id"] = patient_id
        if device_id:
            params["device_id"] = device_id
        if case_id:
            params["case_id"] = case_id

        r = await self._client.get("/telemetry/", params=params)
        r.raise_for_status()
        return TelemetryPageResponse.model_validate(r.json())
