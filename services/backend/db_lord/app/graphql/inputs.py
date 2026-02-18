"""
GraphQL input types for filtering.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

import strawberry


@strawberry.enum
class FilterOperator(Enum):
    """Supported filter operators."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    ILIKE = "ilike"
    CONTAINS = "contains"


@strawberry.input(one_of=True)
class FilterValue:
    """
    Typed filter value - use exactly **ONE** field based on the column type.
    GraphQL will validate the types at parse time.
    """

    string: strawberry.Maybe[str]
    integer: strawberry.Maybe[int]
    float_val: strawberry.Maybe[float] = strawberry.field(name="float")
    boolean: strawberry.Maybe[bool]
    uuid: strawberry.Maybe[UUID]
    date: strawberry.Maybe[date]
    datetime: strawberry.Maybe[datetime]
    decimal: strawberry.Maybe[Decimal]

    # List variants for IN/NOT_IN operators
    string_list: strawberry.Maybe[list[str]]
    integer_list: strawberry.Maybe[list[int]]
    uuid_list: strawberry.Maybe[list[UUID]]


@strawberry.input
class FilterCondition:
    """
    A single filter condition (leaf node in the filter tree).
    """

    field: str = strawberry.field(description="Column name to filter on.")
    op: FilterOperator = strawberry.field(description="Comparison operator.")
    value: FilterValue | None = strawberry.field(
        default=None, description="Value to compare against (omit for IS_NULL check)."
    )


@strawberry.input
class FilterInput:
    """
    Recursive filter input supporting AND/OR/NOT boolean logic.

    Use exactly ONE of: condition, and_, or_, not_

    Examples:
        Simple: { condition: { field: "status", op: EQ, value: { string: "ONGOING" } } }
        AND: { and: [{ condition: ... }, { condition: ... }] }
        OR: { or: [{ condition: ... }, { condition: ... }] }
        NOT: { not: { condition: ... } }
        Nested: { and: [{ condition: ... }, { or: [{ condition: ... }, { not: { condition: ... } }] }] }
    """

    condition: FilterCondition | None = strawberry.field(
        default=None, description="A single filter condition (leaf node)."
    )
    and_: list[FilterInput] | None = strawberry.field(
        default=None, name="and", description="All conditions must match."
    )
    or_: list[FilterInput] | None = strawberry.field(
        default=None, name="or", description="At least one condition must match."
    )
    not_: FilterInput | None = strawberry.field(default=None, name="not", description="Negate the nested condition.")


@strawberry.input(one_of=True)
class TelemetryTagMatchInput:
    """Tag matcher with strategy: value OR values."""

    value: strawberry.Maybe[str] = strawberry.field(description="Single tag value (equality match).")
    values: strawberry.Maybe[list[str]] = strawberry.field(description="Multiple tag values (IN match).")


@strawberry.input
class TelemetryTagInput:
    """Telemetry tag filter supporting exact match and IN-list matching."""

    key: str = strawberry.field(description="Tag key.")
    match: TelemetryTagMatchInput = strawberry.field(description="One of matcher for tag value(s).")


@strawberry.input
class TelemetryQueryInput:
    """Input for direct telemetry (InfluxDB) queries."""

    measurement: str = strawberry.field(description="InfluxDB measurement name.")
    start: datetime | None = strawberry.field(default=None, description="Start of time range.")
    end: datetime | None = strawberry.field(default=None, description="End of time range.")
    tags: list[TelemetryTagInput] | None = strawberry.field(
        default=None, description="Direct Influx tag filters as key/value entries."
    )
    patient_filter: FilterInput | None = strawberry.field(
        default=None,
        description="Optional PostgreSQL patient filter resolved to telemetry patient_id IN.",
    )
    case_filter: FilterInput | None = strawberry.field(
        default=None,
        description="Optional PostgreSQL case filter resolved to telemetry case_id IN.",
    )
    device_filter: FilterInput | None = strawberry.field(
        default=None,
        description="Optional PostgreSQL device filter resolved to telemetry device_id IN.",
    )
    wearable_filter: FilterInput | None = strawberry.field(
        default=None,
        description="Optional PostgreSQL wearable filter resolved to telemetry wearable_id IN.",
    )
    context_filter: FilterInput | None = strawberry.field(
        default=None,
        description="Optional PostgreSQL context filter resolved to telemetry context_id IN.",
    )
    mapping_filter: FilterInput | None = strawberry.field(
        default=None,
        description="Optional PostgreSQL mapping filter resolved to telemetry mapping_id IN.",
    )
    include_resolved_metadata: bool = strawberry.field(
        default=False,
        description="When true, include PostgreSQL entities resolved from cross-db filters.",
    )
    codes: list[str] | None = strawberry.field(default=None, description="Telemetry code tags (OR logic).")
    fields: list[str] | None = strawberry.field(default=None, description="Specific fields to return (None = all).")
    page_size: int = strawberry.field(default=100, description="Number of points to return (max 10000).")
    cursor: str | None = strawberry.field(default=None, description="Opaque telemetry cursor for pagination.")
