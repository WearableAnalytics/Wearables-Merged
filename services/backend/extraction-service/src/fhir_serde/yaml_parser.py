from __future__ import annotations
from typing import Any, Literal, Optional, Union
import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

# This model was derived from the YAML using ChatGPT 5.2

class LineProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tag", "field", "measurement", "timestamp"]
    name: Optional[str] = None
    mandatory: Optional[bool] = None


class Transform(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    params: Optional[list[Any]] = None


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    optional: bool
    type: str

    rawSource: Optional[str] = None
    fhirSource: Optional[str] = None
    value: Optional[Union[str, int, float, bool]] = None

    transform: Optional[list[Transform]] = None
    lineProtocol: Optional[LineProtocol] = None


class MapEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    value: str


class MappingDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fieldName: str
    valueType: str
    map: list[MapEntry]


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[FieldDef]


class MeasurementPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    arrayMapAll: bool = False
    fields: list[FieldDef]
    mappings: Optional[list[MappingDef]] = None


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[MeasurementPath]


class FhirYamlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    metadata: Metadata
    measurement: Measurement

def parse_yaml(yaml_string: str, category_name: str) -> tuple[dict[str, FieldDef], dict[str, MappingDef]]:
    try:
        data = yaml.safe_load(yaml_string)
        fhir_yaml = FhirYamlConfig.model_validate(data)

        return extract_relevant_field_and_maps(fhir_yaml, category_name)
    except (FileNotFoundError, yaml.YAMLError, ValidationError) as e:
        raise RuntimeError(f"Failed to load YAML config: {e}") from e

def extract_relevant_field_and_maps(yaml_basis: FhirYamlConfig, category_name: str) -> tuple[dict[str, FieldDef], dict[str, MappingDef]]:

    copy_yaml = yaml_basis.model_copy(deep=True)
    yaml_basis.measurement.paths = [
        p for p in copy_yaml.measurement.paths
        if p.path == category_name
    ]
    if len(yaml_basis.measurement.paths) != 1:
        raise RuntimeError(
            f"there should be exactly one applicable category, but there are {yaml_basis.measurement.paths}")

    field_dict: dict[str, FieldDef] = {}
    mapping_dict: dict[str, MappingDef] = {}

    for field in yaml_basis.measurement.paths[0].fields + yaml_basis.metadata.fields:
        field_dict[field.name] = field

    for mapping in yaml_basis.measurement.paths[0].mappings:
        mapping_dict[mapping.fieldName] = mapping

    return field_dict, mapping_dict