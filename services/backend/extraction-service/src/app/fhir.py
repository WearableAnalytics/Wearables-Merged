"""Turning telemetry points into FHIR Observations."""

from __future__ import annotations

from datetime import UTC
from functools import lru_cache
from pathlib import Path

import yaml

from src.fhir_serde.dot_parser import Graph, parse_file
from src.fhir_serde.fhir_builder import FhirParser
from src.fhir_serde.model import FhirYamlConfig

from .db_lord_api import DbLordApi
from .schemas import PATIENT_REFERENCE_PREFIX, TelemetryPoint
from .settings import settings


@lru_cache(maxsize=4)
def load_mapping(path: Path) -> FhirYamlConfig:
    return FhirYamlConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def default_mapping() -> FhirYamlConfig:
    return load_mapping(settings.fhir_default_mapping_path)


def builtin_mapping(point: TelemetryPoint) -> FhirYamlConfig:
    if point.tags.get("version", "1.0.0").startswith("2."):
        return default_mapping()
    return load_mapping(Path(__file__).with_name("legacy_fhir_mapping.yaml"))


def category_for(config: FhirYamlConfig, point: TelemetryPoint) -> str | None:
    """The mapping path (category) to build the point with.

    Points carry their category as a tag (e.g. `measurements.cumulative`). That category is
    used unless another one's code mapping knows the measurement and it does not.
    """
    knowing = [
        path.path
        for path in config.measurement.paths
        if any(entry.key == point.measurement for mapping in path.mappings or [] for entry in mapping.map)
    ]
    tagged = point.tags.get("category")
    if tagged in knowing or (not knowing and tagged in {p.path for p in config.measurement.paths}):
        return tagged
    return knowing[0] if knowing else None


def make_parser(config: FhirYamlConfig, category: str, graphs: dict[str, Graph] | None = None) -> FhirParser:
    nodes = graphs[category].nodes if graphs and category in graphs else []
    # FhirParser narrows the config it is given to one category, so hand it a copy.
    return FhirParser(config.model_copy(deep=True), category, nodes)


def build_observation(parser: FhirParser, point: TelemetryPoint) -> dict:
    timestamp = point.timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    observation = parser.build_fhir_from_telemetry(
        fields=point.fields,
        tags=point.tags,
        measurement=point.measurement,
        timestamp=timestamp,
    )
    # The mapping derives the subject from tags written in the ingest direction
    # (it would prepend "Patient/" to an existing reference), so set it from the patient id.
    if point.patient_id:
        observation["subject"] = {"reference": f"{PATIENT_REFERENCE_PREFIX}{point.patient_id}"}
    # Stored units and codes describe the accepted point. A later mapping must
    # not change them while reconstructing an export.
    quantity = observation.setdefault("valueQuantity", {})
    if "valueUnit" in point.tags:
        quantity.update(unit=point.tags["valueUnit"], code=point.tags.get("valueCode", point.tags["valueUnit"]))
    if "valueSystem" in point.tags:
        quantity["system"] = point.tags["valueSystem"]
    if "codeCodingCodeZero" in point.tags:
        observation.setdefault("code", {})["coding"] = [
            {
                "code": point.tags["codeCodingCodeZero"],
                "system": point.tags.get("codeCodingSystemZero", "http://loinc.org"),
                "display": point.tags.get("codeCodingDisplayZero", point.measurement),
            }
        ]
    if "period_end" in point.fields:
        observation.pop("effectiveDateTime", None)
        observation["effectivePeriod"] = {
            "start": point.fields.get("period_start", timestamp),
            "end": point.fields["period_end"],
        }
    source = point.tags.get("source-key")
    record_id = point.fields.get("source_record_id")
    if source and source != "legacy" and record_id:
        observation["identifier"] = [{"system": f"urn:wearables:source:{source}", "value": str(record_id)}]
    for extension in observation.get("extension", []):
        if extension is not None and set(extension) == {"url"}:
            extension["extension"] = [{
                "url": "http://hl7.org/fhir/StructureDefinition/data-absent-reason", "valueCode": "unknown",
            }]
    return observation


class ObservationBuilder:
    """Builds Observations, using the point's own mapping from db_lord when it has one."""

    def __init__(self, api: DbLordApi):
        self._api = api
        self._mappings: dict[str, FhirYamlConfig | None] = {}
        self._graphs: dict[str, dict[str, Graph]] = {}
        self._parsers: dict[tuple[str | None, str | None, str], FhirParser] = {}

    async def build(self, point: TelemetryPoint) -> dict | None:
        config = await self._mapping_for(point)
        category = category_for(config, point)
        if category is None:
            return None
        key = (point.mapping_id, point.dot_dependency_file_id, category)
        if key not in self._parsers:
            self._parsers[key] = make_parser(config, category, await self._graphs_for(point))
        return build_observation(self._parsers[key], point)

    async def _mapping_for(self, point: TelemetryPoint) -> FhirYamlConfig:
        mapping_id = point.mapping_id
        if mapping_id is None:
            return builtin_mapping(point)
        if mapping_id not in self._mappings:
            response = await self._api.get_fhir_mapping(mapping_id)
            self._mappings[mapping_id] = FhirYamlConfig.model_validate(response.full_mapping)
        return self._mappings[mapping_id]

    async def _graphs_for(self, point: TelemetryPoint) -> dict[str, Graph]:
        dot_id = point.dot_dependency_file_id
        if dot_id is None:
            return {}
        if dot_id not in self._graphs:
            try:
                response = await self._api.get_dot_dependency_file(dot_id)
                raw = response.digraph.get("raw", "")
                self._graphs[dot_id] = parse_file(raw) if raw else {}
            except Exception:
                self._graphs[dot_id] = {}
        return self._graphs[dot_id]
