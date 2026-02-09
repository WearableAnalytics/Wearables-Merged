from typing import Any
from uuid import UUID

from pydantic import Field

from app.model_constants import FHIR_CATEGORY_MAX_LEN, FHIR_VERSION_MAX_LEN

from .common import TunedBase


class FHIRMappingBase(TunedBase):
    version: str = Field(
        ...,
        min_length=1,
        max_length=FHIR_VERSION_MAX_LEN,
        title="Mapping Version",
        description="The version of the mapping that can be used to convert telemetry data to FHIR resources. "
        "This can be used to manage different versions of mappings as they evolve over time.",
        examples=["v1.0", "1.3.5"],
    )
    full_mapping: dict[str, Any] = Field(
        ...,
        title="Full Mapping Definition",
        description="The complete mapping definition that includes all necessary "
        "information to convert telemetry data to FHIR resources.",
    )


class FHIRMappingCreate(FHIRMappingBase):
    pass


class FHIRMappingUpdate(TunedBase):
    version: str | None = Field(
        None,
        min_length=1,
        max_length=FHIR_VERSION_MAX_LEN,
        title="Mapping Version",
        description="The version of the mapping that can be used to convert telemetry data to FHIR resources. "
        "This can be used to manage different versions of mappings as they evolve over time.",
        examples=["v1.0", "1.3.5"],
    )
    full_mapping: dict[str, Any] | None = Field(
        None,
        title="Full Mapping Definition",
        description="The complete mapping definition that includes all necessary "
        "information to convert telemetry data to FHIR resources.",
    )


class FHIRMappingResponse(FHIRMappingBase):
    id: UUID


class FHIRMappingTreeBase(TunedBase):
    version: str = Field(
        ...,
        min_length=1,
        max_length=FHIR_VERSION_MAX_LEN,
        title="Mapping Version",
        description="The version of the mapping that can be used to convert telemetry data to FHIR resources. "
        "This can be used to manage different versions of mappings as they evolve over time.",
        examples=["v1.0", "1.3.5"],
    )
    category: str = Field(
        ...,
        min_length=1,
        max_length=FHIR_CATEGORY_MAX_LEN,
        title="Mapping Category",
        description="The category of data that this mapping applies to.",
        examples=["continuous", "incremental"],
    )
    map_tree: dict[str, Any] = Field(
        ...,
        title="Mapping Tree",
        description="The mapping tree that defines how this category of telemetry data should "
        "be transformed into FHIR resources.",
    )
    mapping_id: UUID = Field(
        ...,
        title="Mapping ID",
        description="The ID of the complete FHIR mapping that this tree belongs to.",
    )


class FHIRMappingTreeCreate(FHIRMappingTreeBase):
    pass


class FHIRMappingTreeUpdate(TunedBase):
    version: str | None = Field(
        None,
        min_length=1,
        max_length=FHIR_VERSION_MAX_LEN,
        title="Mapping Version",
        description="The version of the mapping that can be used to convert telemetry data to FHIR resources. "
        "This can be used to manage different versions of mappings as they evolve over time.",
        examples=["v1.0", "1.3.5"],
    )
    category: str | None = Field(
        None,
        min_length=1,
        max_length=FHIR_CATEGORY_MAX_LEN,
        title="Mapping Category",
        description="The category of data that this mapping applies to.",
        examples=["continuous", "incremental"],
    )
    map_tree: dict[str, Any] | None = Field(
        None,
        title="Mapping Tree",
        description="The mapping tree that defines how this category of telemetry data should "
        "be transformed into FHIR resources.",
    )
    mapping_id: UUID | None = Field(
        None,
        title="Mapping ID",
        description="The ID of the complete FHIR mapping that this tree belongs to.",
    )


class FHIRMappingTreeResponse(FHIRMappingTreeBase):
    id: UUID
