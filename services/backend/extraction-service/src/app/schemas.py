from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TelemetryPoint(BaseModel):
    """Matches db_lord's TelemetryPointResponse."""

    measurement: str

    timestamp: datetime
    tags: dict[str, str] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")

    @property
    def patient_id(self) -> str | None:
        return self.tags.get("patient_id")

    @property
    def case_id(self) -> str | None:
        return self.tags.get("case_id")

    @property
    def device_id(self) -> str | None:
        return self.tags.get("device_id")

    @property
    def mapping_id(self) -> str | None:
        return self.tags.get("mapping_id")

    @property
    def dot_dependency_file_id(self) -> str | None:
        return self.tags.get("dot_dependency_file_id")


class TelemetryPageResponse(BaseModel):
    """Matches db_lord's TelemetryWindowResponse."""

    items: list[TelemetryPoint]
    has_more: bool = False
    next_end: datetime | None = None


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
