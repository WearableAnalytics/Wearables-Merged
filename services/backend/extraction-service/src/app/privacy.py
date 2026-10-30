"""Request-scoped pseudonyms and a restricted export projection, not anonymization."""

import math
from pathlib import Path
from uuid import uuid4

from .fhir import build_observation, load_mapping, make_parser
from .schemas import TelemetryPoint


class ExportPrivacy:
    def __init__(self):
        self._patients: dict[str, str] = {}
        self.considered = 0
        self.exported = 0
        self.unsupported = 0
        self.invalid_value = 0
        # Privacy exports must not inherit deployment-specific or per-patient mappings.
        self._config = load_mapping(Path(__file__).with_name("default_fhir_mapping.yaml"))
        self._categories = {
            entry.key: path.path
            for path in self._config.measurement.paths
            for mapping in path.mappings or []
            if mapping.fieldName == "codeCodingCodeZero"
            for entry in mapping.map
        }
        self._parsers = {}

    def project(self, point: TelemetryPoint) -> TelemetryPoint | None:
        self.considered += 1
        value = point.fields.get("value")
        # Free text, arbitrary tags and custom mappings can contain identifying data.
        if point.measurement not in self._categories:
            self.unsupported += 1
            return None
        if type(value) not in (int, float):
            self.invalid_value += 1
            return None
        if isinstance(value, float) and not math.isfinite(value):
            self.invalid_value += 1
            return None
        tags = {}
        if point.patient_id:
            if point.patient_id not in self._patients:
                self._patients[point.patient_id] = str(uuid4())
            tags["device-id"] = self._patients[point.patient_id]
        clean = TelemetryPoint(
            measurement=point.measurement,
            timestamp=point.timestamp,
            fields={"value": value},
            tags=tags,
        )
        clean.tags["category"] = self._categories[point.measurement]
        self.exported += 1
        return clean

    @property
    def omitted(self) -> int:
        return self.unsupported + self.invalid_value

    def response_headers(self) -> dict[str, str]:
        return {
            "X-Export-Considered": str(self.considered),
            "X-Export-Exported": str(self.exported),
            "X-Export-Omitted": str(self.omitted),
            "X-Export-Omitted-Unsupported": str(self.unsupported),
            "X-Export-Omitted-Invalid-Value": str(self.invalid_value),
        }

    def observation(self, point: TelemetryPoint) -> dict:
        """Render an already projected point without consulting external mappings."""
        category = self._categories[point.measurement]
        if category not in self._parsers:
            self._parsers[category] = make_parser(self._config, category)
        result = build_observation(self._parsers[category], point)
        result.pop("device", None)
        return result
