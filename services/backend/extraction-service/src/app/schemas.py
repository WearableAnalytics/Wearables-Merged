from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PATIENT_REFERENCE_PREFIX = "Patient/"

# Tags that only describe how a point was ingested. They differ between otherwise
# identical copies of a reading and are dropped from the export.
INGESTION_TAGS = frozenset({"host"})
INGESTION_FIELDS = frozenset({"t_ingested"})


class TelemetryPoint(BaseModel):
    """Matches db_lord's TelemetryPointResponse."""

    measurement: str

    timestamp: datetime
    tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @property
    def patient_id(self) -> str | None:
        """The patient the point belongs to.

        The ingestion pipeline stores the patient as the `device-id` tag and as
        `device-id-reference=Patient/<id>`; older points only carry one of the two.
        """
        if self.tags.get("patient_id"):
            return self.tags["patient_id"]
        if self.tags.get("device-id"):
            return self.tags["device-id"]
        ref = self.tags.get("device-id-reference", "")
        if ref.startswith(PATIENT_REFERENCE_PREFIX):
            return ref[len(PATIENT_REFERENCE_PREFIX) :]
        return None

    @property
    def mapping_id(self) -> str | None:
        return self.tags.get("mapping_id")

    @property
    def dot_dependency_file_id(self) -> str | None:
        return self.tags.get("dot_dependency_file_id")


class MeasurementPoint(BaseModel):
    """One exported reading."""

    timestamp: datetime = Field(description="Time of the reading (UTC).")
    measurement: str = Field(description="Measurement type, e.g. `heart-rate` or `steps`.", examples=["heart-rate"])
    patient_id: str | None = Field(description="db-lord patient id the reading belongs to.")
    category: str | None = Field(
        default=None,
        description="Mapping category, e.g. `measurements.instantaneous`, `measurements.cumulative`.",
    )
    value: Any = Field(default=None, description="The reading's `value` field.")
    fields: dict[str, Any] = Field(default_factory=dict, description="All other fields of the reading.")
    tags: dict[str, str] = Field(default_factory=dict, description="Remaining Influx tags of the reading.")

    @classmethod
    def from_telemetry(cls, point: TelemetryPoint) -> MeasurementPoint:
        fields = {k: v for k, v in point.fields.items() if k not in INGESTION_FIELDS}
        return cls(
            timestamp=point.timestamp,
            measurement=point.measurement,
            patient_id=point.patient_id,
            category=point.tags.get("category"),
            value=fields.pop("value", None),
            fields=fields,
            tags={k: v for k, v in point.tags.items() if k not in INGESTION_TAGS},
        )


class MeasurementPage(BaseModel):
    items: list[MeasurementPoint]
    has_more: bool = Field(default=False, description="Whether older readings exist beyond this page.")
    next_end: datetime | None = Field(
        default=None,
        description="Pass as `end` to fetch the next (older) page. Readings at exactly this time are already included.",
    )


class MeasurementType(BaseModel):
    measurement: str = Field(examples=["heart-rate"])
    field_keys: list[str] = Field(description="Fields stored for this measurement.", examples=[["value"]])


class FhirMappingResponse(BaseModel):
    """Matches db_lord's FHIRMappingResponse."""

    id: str
    version: str
    full_mapping: dict[str, Any]


class DotDependencyFileResponse(BaseModel):
    """Matches db_lord's DotDependencyFileResponse."""

    id: str
    version: str
    category: str
    digraph: dict[str, Any]
    mapping_id: str


class ErrorResponse(BaseModel):
    detail: str
