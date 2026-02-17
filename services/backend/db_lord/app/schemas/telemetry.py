from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, Field

from app.pagination import CursorPageNoTotal
from app.schemas.common import TunedBase


class TelemetryCreate(TunedBase):
    patient_id: UUID
    case_id: UUID
    device_id: UUID
    wearable_id: UUID
    mapping_id: UUID
    code: str
    context_id: UUID | None = None

    measurement: str

    timestamp: AwareDatetime | None = None
    other_tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)


class TelemetryPointResponse(TunedBase):
    patient_id: UUID
    case_id: UUID
    device_id: UUID
    wearable_id: UUID
    mapping_id: UUID
    code: str
    context_id: UUID | None = None

    measurement: str

    timestamp: AwareDatetime
    other_tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")


class TelemetryRawPointResponse(TunedBase):
    timestamp: AwareDatetime
    measurement: str
    field: str
    value: Any

    model_config = ConfigDict(extra="allow")


TelemetryPageResponse = CursorPageNoTotal[TelemetryPointResponse]
TelemetryRawPageResponse = CursorPageNoTotal[TelemetryRawPointResponse]


class TelemetrySearchRequest(TunedBase):
    measurement: str
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    tags: dict[str, str | list[str]] = Field(default_factory=dict)
    fields: list[str] | None = None
    cursor: str | None = None
    size: int = Field(default=50, ge=1, le=10000)
