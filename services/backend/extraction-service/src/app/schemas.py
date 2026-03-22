from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TelemetryPoint(BaseModel):
    """Matches db_lord's TelemetryPointResponse."""

    patient_id: UUID
    case_id: UUID
    device_id: UUID
    wearable_id: UUID
    mapping_id: UUID
    dot_dependency_file_id: str
    context_id: UUID | None = None

    measurement: str

    timestamp: datetime
    other_tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class TelemetryPageResponse(BaseModel):
    """Matches db_lord's CursorPageNoTotal response."""

    items: list[TelemetryPoint]
    next_page: str | None = None
    previous_page: str | None = None


class FhirMappingResponse(BaseModel):
    """Matches db_lord's FHIRMappingResponse."""

    id: UUID
    version: str
    full_mapping: dict[str, Any]


class DotDependencyFileResponse(BaseModel):
    """Matches db_lord's DotDependencyFileResponse."""

    id: UUID
    version: str
    category: str
    digraph: dict[str, Any]
    mapping_id: UUID


class ErrorResponse(BaseModel):
    detail: str
