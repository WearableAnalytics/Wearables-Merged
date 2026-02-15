from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx
import yaml

from .schemas import TelemetryPageResponse
from ..fhir_serde.dot_parser import Graph
from ..fhir_serde.yaml_parser import parse_yaml, FieldDef, MappingDef


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

    async def read_yaml_for_version_and_category(self, version: str, category: str) -> tuple[dict[str, FieldDef], dict[str, MappingDef]]:

        #TODO this probably wont work but need to wait for impl in db_lord

        params: dict[str, Any] = {
            "version": version
        }

        r = await self._client.get("/fhir-mappings", params=params)

        resp = r.json()["full_mapping"]

        yaml_string = yaml.dump(json.load(resp))

        return parse_yaml(yaml_string, category)

    async def read_graph_for_version_and_category(self, version: str, category: str) -> Graph:

        params: dict[str, Any] = {
            "version": version,
            "category": category
        }

        r = await self._client.get("/dot-dependency-file", params=params)



