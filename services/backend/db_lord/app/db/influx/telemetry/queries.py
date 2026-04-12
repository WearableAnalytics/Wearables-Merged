import json
from datetime import datetime

from app.core.utils import ordered_unique, to_utc
from app.telemetry.types import TelemetryTags

type FluxParams = dict[str, object]


def build_flux_query(
    bucket: str,
    measurement: str | None,
    start: datetime | None,
    end: datetime | None,
    tags: TelemetryTags | None,
    fields: list[str] | None,
    row_limit: int | None,
) -> tuple[str, FluxParams]:
    """Build one row-oriented Flux query + its params."""
    if row_limit is not None and row_limit < 1:
        raise ValueError("row_limit must be at least 1")

    params, range_call = build_range_clause(bucket, start, end)
    flux_parts = ["from(bucket: bucket_param)", range_call]
    if measurement is not None:
        params["measurement_param"] = measurement
        flux_parts.append('|> filter(fn: (r) => r["_measurement"] == measurement_param)')

    tag_filter = build_tag_filter_clause(tags, params)
    if tag_filter is not None:
        flux_parts.append(tag_filter)

    field_filter = build_field_filter_clause(fields, params)
    if field_filter is not None:
        flux_parts.append(field_filter)

    flux_parts.append('|> sort(columns: ["_time"], desc: true)')
    if row_limit is not None:
        flux_parts.append(f"|> limit(n: {row_limit})")

    return "\n".join(flux_parts), params


def build_range_clause(bucket: str, start: datetime | None, end: datetime | None) -> tuple[FluxParams, str]:
    """Returns a tuple of (Flux query parameters, Flux range clause) based on the provided start and end datetimes.
    Defaults to a 24h range if start is not provided.
    """
    start_expr = "start_param" if start is not None else "-24h"
    stop_expr: str | None = None
    stop_utc = None
    if end is not None:
        stop_utc = to_utc(end)
        stop_expr = "stop_param"

    start_utc = to_utc(start) if start is not None else None
    if start_utc is not None and stop_utc is not None and start_utc > stop_utc:
        raise ValueError("start must be <= end")

    params: FluxParams = {"bucket_param": bucket}
    if start_utc is not None:
        params["start_param"] = start_utc
    if stop_utc is not None:
        params["stop_param"] = stop_utc

    range_call = f"|> range(start: {start_expr}"
    if stop_expr is not None:
        range_call = f"{range_call}, stop: {stop_expr}"
    return params, f"{range_call})"


def build_tag_filter_clause(tags: TelemetryTags | None, params: FluxParams) -> str | None:
    """Returns a Flux filter clause for the provided tags, and updates the params dict with any necessary parameters.
    Currently uses magic numbers to decide when to switch from equality to 'contains' for multiple tag values"""
    if not tags:
        return None

    filter_conditions: list[str] = []
    for index, (key, values) in enumerate(tags.items()):
        column = f"r[{json.dumps(key)}]"
        unique_values = ordered_unique(str(item) for item in values)
        if not unique_values:
            filter_conditions.append("false")
            continue
        if len(unique_values) == 1:
            value_param = f"tag_val_{index}"
            params[value_param] = unique_values[0]
            filter_conditions.append(f"{column} == {value_param}")
        elif len(unique_values) <= 8:
            or_conditions: list[str] = []
            for value_index, item in enumerate(unique_values):
                value_param = f"tag_val_{index}_{value_index}"
                params[value_param] = item
                or_conditions.append(f"{column} == {value_param}")
            filter_conditions.append(f"({' or '.join(or_conditions)})")
        else:
            list_param = f"tag_vals_{index}"
            params[list_param] = unique_values
            filter_conditions.append(f"contains(value: {column}, set: {list_param})")

    if not filter_conditions:
        return None
    return f"|> filter(fn: (r) => {' and '.join(filter_conditions)})"


def build_field_filter_clause(fields: list[str] | None, params: FluxParams) -> str | None:
    if not fields:
        return None

    deduped_fields = ordered_unique(str(field) for field in fields if field)
    if not deduped_fields:
        return None

    column = 'r["_field"]'
    if len(deduped_fields) == 1:
        params["field_val_0"] = deduped_fields[0]
        return f"|> filter(fn: (r) => {column} == field_val_0)"
    if len(deduped_fields) <= 8:
        conditions: list[str] = []
        for index, field_name in enumerate(deduped_fields):
            param_name = f"field_val_{index}"
            params[param_name] = field_name
            conditions.append(f"{column} == {param_name}")
        return f"|> filter(fn: (r) => ({' or '.join(conditions)}))"

    params["field_set_param"] = deduped_fields
    return f"|> filter(fn: (r) => contains(value: {column}, set: field_set_param))"
def normalize_measurement(measurement: str | None) -> str | None:
    if measurement is None:
        return None
    normalized = measurement.strip()
    if not normalized:
        raise ValueError("measurement must be a non-empty string when provided")
    return normalized


def resolve_bucket(default_bucket: str, bucket: str | None) -> str:
    normalized = default_bucket if bucket is None else bucket.strip()
    if not normalized:
        raise ValueError("bucket must be a non-empty string when provided")
    return normalized
