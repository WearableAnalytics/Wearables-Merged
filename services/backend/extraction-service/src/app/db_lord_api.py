from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime

import httpx

from .schemas import DotDependencyFileResponse, FhirMappingResponse, TelemetryPoint

MEASUREMENTS_QUERY = "{ influxDbIntrospection(includeTagValues: false) { measurements { measurement fieldKeys } } }"


class DbLordApi:
    def __init__(self, client: httpx.AsyncClient):
        self._client = client

    async def stream_telemetry(
        self,
        *,
        measurement: str | None,
        start: datetime,
        end: datetime | None = None,
        tags: dict[str, str] | None = None,
    ) -> AsyncIterator[TelemetryPoint]:
        """Stream structured telemetry from db_lord, newest first, for the whole time range."""
        params: dict[str, str] = {"start": start.isoformat()}
        if measurement:
            params["measurement"] = measurement
        if end:
            params["end"] = end.isoformat()
        # db_lord treats unknown query params as Influx tag filters (e.g. ?device-id=...).
        params.update(tags or {})

        async with self._client.stream("GET", "/telemetry/stream", params=params) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.strip():
                    yield TelemetryPoint.model_validate(json.loads(line))

    async def list_measurements(self) -> list[dict]:
        r = await self._client.post("/graphql", json={"query": MEASUREMENTS_QUERY})
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"db_lord GraphQL error: {body['errors']}")
        return body["data"]["influxDbIntrospection"]["measurements"]

    async def get_fhir_mapping(self, mapping_id: str) -> FhirMappingResponse:
        r = await self._client.get(f"/fhir-mappings/{mapping_id}")
        r.raise_for_status()
        return FhirMappingResponse.model_validate(r.json())

    async def get_dot_dependency_file(self, file_id: str) -> DotDependencyFileResponse:
        r = await self._client.get(f"/fhir-mappings/dot_dependency_file/{file_id}")
        r.raise_for_status()
        return DotDependencyFileResponse.model_validate(r.json())
