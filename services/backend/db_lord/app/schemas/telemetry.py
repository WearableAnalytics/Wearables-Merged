from uuid import UUID

from pydantic import AwareDatetime, Field

from app.core.json_types import JsonObject, JsonValue
from app.schemas.common import TunedBase


class TelemetryCreate(TunedBase):
    patient_id: UUID = Field(description="Patient tag linked to the telemetry point.")
    case_id: UUID = Field(description="Case tag linked to the telemetry point.")
    device_id: UUID = Field(description="Device tag linked to the telemetry point.")
    wearable_id: UUID = Field(description="Wearable tag linked to the telemetry point.")
    mapping_id: UUID = Field(description="FHIR mapping tag linked to the telemetry point.")
    dot_dependency_file_id: UUID = Field(description="Dot dependency file tag linked to the telemetry point.")
    context_id: UUID | None = Field(default=None, description="Optional context tag linked to the telemetry point.")

    measurement: str = Field(description="Influx measurement name.", examples=["sensor_readings"])

    timestamp: AwareDatetime | None = Field(
        default=None,
        description="Timestamp of the point. If omitted, the write time is used.",
    )
    other_tags: dict[str, str] = Field(
        default_factory=dict,
        description="Additional non-core Influx tags stored with the point.",
        examples=[{"sensor_type": "ecg", "site": "icu"}],
    )
    fields: JsonObject = Field(
        default_factory=dict,
        description="Field values written for the point.",
        examples=[{"heart_rate": 72, "spo2": 98}],
    )


class TelemetryPointResponse(TunedBase):
    measurement: str = Field(description="Influx measurement name.")
    timestamp: AwareDatetime = Field(description="Timestamp of the grouped telemetry item.")
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Influx tags present on the grouped item.",
    )
    fields: JsonObject = Field(
        default_factory=dict,
        description="Field values grouped into one logical telemetry item.",
    )


class TelemetryRawPointResponse(TunedBase):
    timestamp: AwareDatetime = Field(description="Timestamp of the raw telemetry row.")
    measurement: str = Field(description="Influx measurement name.")
    field: str = Field(description="Influx field key for this raw row.")
    value: JsonValue = Field(description="Raw field value.")
    tags: dict[str, str] = Field(default_factory=dict, description="Influx tags present on the raw row.")


class TelemetryWindowResponse(TunedBase):
    items: list[TelemetryPointResponse] = Field(default_factory=list)
    has_more: bool = Field(default=False, description="Whether older matching telemetry exists beyond this window.")
    next_end: AwareDatetime | None = Field(
        default=None,
        description="Exclusive end timestamp to use for the next older window request.",
    )


class TelemetryRawWindowResponse(TunedBase):
    items: list[TelemetryRawPointResponse] = Field(default_factory=list)
    has_more: bool = Field(default=False, description="Whether older matching raw rows exist beyond this window.")
    next_end: AwareDatetime | None = Field(
        default=None,
        description="Exclusive end timestamp to use for the next older window request.",
    )
