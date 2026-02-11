from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TelemetryPoint(BaseModel):
    timestamp: datetime
    measurement: str

    patient_id: UUID | None = None
    case_id: UUID | None = None
    device_id: UUID | None = None

    model_config = ConfigDict(extra="allow")


class TelemetryPageResponse(BaseModel):
    items: list[TelemetryPoint]
    next_cursor: str | None


class ErrorResponse(BaseModel):
    detail: str
