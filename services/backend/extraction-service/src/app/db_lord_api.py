from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from .schemas import DotDependencyFileResponse, FhirMappingResponse, TelemetryPageResponse


class DbLordApi:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def read_telemetry(
        self,
        *,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 100,
        patient_id: str | None = None,
        device_id: str | None = None,
        case_id: str | None = None,
    ) -> TelemetryPageResponse:
        params: dict[str, Any] = {
            "measurement": measurement,
            "limit": limit,
        }
        if start:
            params["start"] = start.isoformat()
        if end:
            params["end"] = end.isoformat()
        if patient_id:
            params["patient_id"] = patient_id
        if device_id:
            params["device_id"] = device_id
        if case_id:
            params["case_id"] = case_id

        r = await self._client.get("/telemetry/", params=params)
        r.raise_for_status()
        return TelemetryPageResponse.model_validate(r.json())

    async def get_fhir_mapping(self, mapping_id: str) -> FhirMappingResponse:
        r = await self._client.get(f"/fhir-mappings/{mapping_id}")
        r.raise_for_status()
        return FhirMappingResponse.model_validate(r.json())

    async def get_dot_dependency_file(self, file_id: str) -> DotDependencyFileResponse:
        r = await self._client.get(f"/fhir-mappings/dot_dependency_file/{file_id}")
        r.raise_for_status()
        return DotDependencyFileResponse.model_validate(r.json())
