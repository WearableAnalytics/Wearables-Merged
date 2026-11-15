from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class LineProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["tag", "field", "measurement", "timestamp"]
    name: str | None = None
    mandatory: bool | None = None


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
    params: list[Any] | None = None


class FieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    target: str
    optional: bool
    type: str

    # exactly one (or none) of these is typically present
    rawSource: str | None = None
    fhirSource: str | None = None
    value: str | int | float | bool | None = None

    transform: list[Transform] | None = None
    lineProtocol: LineProtocol | None = None


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
    mappings: list[MappingDef] | None = None


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[MeasurementPath]


class FhirYamlConfig(BaseModel):
    """
    Root object representing your YAML.
    """

    model_config = ConfigDict(extra="forbid")

    version: str
    numericContract: str | None = None
    metadata: Metadata
    measurement: Measurement
