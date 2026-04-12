from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from app.core.json_types import JsonObject, JsonValue

type TelemetryTagValues = list[str]
type TelemetryTagInput = str | TelemetryTagValues
type TelemetryTags = dict[str, TelemetryTagValues]
type TelemetryRecordTags = dict[str, str]


class StructuredTelemetryItem(TypedDict):
    timestamp: datetime
    measurement: str
    tags: TelemetryRecordTags
    fields: JsonObject


class RawTelemetryItem(TypedDict):
    timestamp: datetime | None
    measurement: str | None
    field: str | None
    value: JsonValue
    tags: TelemetryRecordTags


@dataclass(frozen=True)
class TelemetryWindowResult[TItem]:
    items: list[TItem]
    has_more: bool
    next_end: datetime | None


@dataclass(frozen=True)
class MeasurementSchema:
    tag_keys: tuple[str, ...]
    field_keys: frozenset[str]
