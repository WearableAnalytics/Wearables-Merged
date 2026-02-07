from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import TunedBase


class TelemetryCreate(TunedBase):
    patient_id: UUID
    case_id: UUID
    device_id: UUID
    measurement: str

    timestamp: datetime | None = None
    tags: dict[str, str] | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class TelemetryPoint(TunedBase):
    timestamp: datetime
    measurement: str

    patient_id: UUID | None = None
    case_id: UUID | None = None
    device_id: UUID | None = None

    model_config = ConfigDict(extra="allow")


class TelemetryPageResponse(BaseModel):
    items: list[TelemetryPoint]
    next_cursor: str | None
