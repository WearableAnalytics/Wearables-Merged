from __future__ import annotations

from typing import Any, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

class LineProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tag", "field", "measurement", "timestamp"]
    name: Optional[str] = None
    mandatory: Optional[bool] = None


class Transform(BaseModel):
    """
    Examples in your YAML:
      - {type: toLowerCase}
      - {type: replace, params: ['_', '-']}
      - {type: append, params: ['Z']}
      - {type: map}
    """
    model_config = ConfigDict(extra="forbid")

    type: str
    params: Optional[list[Any]] = None


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    optional: bool
    type: str

    # exactly one (or none) of these is typically present
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


# --------- top-level sections ---------

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
    """
    Root object representing your YAML.
    """
    model_config = ConfigDict(extra="forbid")

    version: str
    metadata: Metadata
    measurement: Measurement