from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import StreamingResponse

from .clients import create_db_lord_client
from .db_lord_api import DbLordApi
from .schemas import TelemetryPageResponse, TelemetryPoint

from src.fhir_serde.dot_parser import parse_file, Graph
from src.fhir_serde.fhir_builder import FhirParser
from src.fhir_serde.model import FhirYamlConfig


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
        cursor: str | None = None
        yield "timestamp,measurement,patient_id,case_id,device_id,fields\n"
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
                    ts = item.timestamp.isoformat()
                    pid = str(item.patient_id)
                    cid = str(item.case_id)
                    did = str(item.device_id)
                    fields_s = json.dumps(item.fields, ensure_ascii=False).replace('"', '""')
                    yield f"{ts},{item.measurement},{pid},{cid},{did},\"{fields_s}\"\n"

                cursor = page.next_page
                if not cursor or not page.items:
                    break

    return StreamingResponse(row_iter(), media_type="text/csv")


@app.get("/v1/measurements/export.fhir")
async def export_measurements_fhir(
    measurement: str,
    start: datetime | None = None,
    end: datetime | None = None,
    page_size: int = Query(1000, ge=1, le=5000),
    patient_id: str | None = None,
    device_id: str | None = None,
    case_id: str | None = None,
):
    """Export telemetry data as a FHIR Bundle of Observation resources."""
    async def generate_bundle():
        mapping_cache: dict[str, FhirYamlConfig] = {}
        graph_cache: dict[str, dict[str, Graph]] = {}

        entries: list[dict[str, Any]] = []
        cursor: str | None = None

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
                    fhir_resource = await _telemetry_to_fhir(api, item, mapping_cache, graph_cache)
                    if fhir_resource:
                        entries.append({
                            "fullUrl": f"urn:uuid:{item.patient_id}:{item.timestamp.isoformat()}",
                            "resource": fhir_resource,
                        })

                cursor = page.next_page
                if not cursor or not page.items:
                    break

        return {
            "resourceType": "Bundle",
            "type": "collection",
            "total": len(entries),
            "entry": entries,
        }

    return await generate_bundle()


async def _telemetry_to_fhir(
    api: DbLordApi,
    item: TelemetryPoint,
    mapping_cache: dict[str, FhirYamlConfig],
    graph_cache: dict[str, dict[str, Graph]],
) -> dict | None:
    """Convert a single telemetry point to a FHIR Observation using its linked mapping."""
    mapping_key = str(item.mapping_id)

    if mapping_key not in mapping_cache:
        try:
            mapping_resp = await api.get_fhir_mapping(mapping_key)
            yaml_config = FhirYamlConfig.model_validate(mapping_resp.full_mapping)
            mapping_cache[mapping_key] = yaml_config
        except Exception:
            return None

    dot_key = item.dot_dependency_file_id
    if dot_key not in graph_cache:
        try:
            dot_resp = await api.get_dot_dependency_file(dot_key)
            raw_graph = dot_resp.digraph.get("raw", "")
            if raw_graph:
                graph_cache[dot_key] = parse_file(raw_graph)
            else:
                graph_cache[dot_key] = {}
        except Exception:
            graph_cache[dot_key] = {}

    yaml_config = mapping_cache[mapping_key].model_copy(deep=True)

    category_name = _find_category(yaml_config, item.measurement)
    if not category_name:
        return None

    graphs = graph_cache.get(dot_key, {})
    nodes = graphs[category_name].nodes if category_name in graphs else []

    parser = FhirParser(yaml_config, category_name, nodes)

    tags = {
        "patient_id": str(item.patient_id),
        "case_id": str(item.case_id),
        "device_id": str(item.device_id),
        "wearable_id": str(item.wearable_id),
        **item.other_tags,
    }

    return parser.build_fhir_from_telemetry(
        fields=item.fields,
        tags=tags,
        measurement=item.measurement,
        timestamp=item.timestamp.isoformat(),
    )


def _find_category(yaml_config: FhirYamlConfig, measurement: str) -> str | None:
    """Find the category path name that matches the measurement.

    Measurement names like 'heart-rate' map to categories like 'measurements.instantaneous'.
    We check all paths; the YAML config determines which category a measurement belongs to.
    For now, return the first path that exists (the caller's FhirParser will validate).
    """
    paths = yaml_config.measurement.paths
    for p in paths:
        return p.path

    return None
