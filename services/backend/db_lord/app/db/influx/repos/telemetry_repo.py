from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi_pagination.types import Cursor
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write.point import Point

from app.core.config import settings

SYSTEM_COLUMNS = frozenset(("result", "table", "_start", "_stop", "_time", "_measurement", "_field", "_value"))
CORE_TAG_KEYS = frozenset(("patient_id", "device_id", "wearable_id", "case_id", "context_id", "mapping_id", "code"))


@dataclass(frozen=True)
class TelemetryPage:
    items: list[Any]
    next_cursor: str | None


class TelemetryRepo:
    """Repository for InfluxDB telemetry data."""

    MAX_PAGE_SIZE = 10_000
    BATCH_CHUNK_SIZE = 5_000

    def __init__(self, client: InfluxDBClientAsync):
        self._client = client

    @property
    def _write_api(self):
        return self._client.write_api()

    @property
    def _query_api(self):
        return self._client.query_api()

    async def write_point(self, point: dict[str, Any]) -> None:
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=self._build_point(point))

    async def write_batch(self, points: Iterable[dict[str, Any]]) -> None:
        chunk: list[Point] = []
        for point in points:
            chunk.append(self._build_point(point))
            if len(chunk) >= self.BATCH_CHUNK_SIZE:
                await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=chunk)
                chunk = []

        if chunk:
            await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=chunk)

    def _build_base_flux_query(
        self,
        measurement: str,
        start: datetime | None,
        end: datetime | None,
        tags: dict[str, str | list[str]] | None,
        fields: list[str] | None,
        page_size: int | None,
        cursor: Cursor | None,
        *,
        pivot: bool,
        include_cursor_extra: bool,
    ) -> tuple[str, dict[str, Any]]:
        if not measurement:
            raise ValueError("measurement must be a non-empty string")

        if page_size is not None:
            if page_size < 1:
                raise ValueError("page_size must be at least 1")
            if page_size > self.MAX_PAGE_SIZE:
                raise ValueError(f"page_size cannot exceed {self.MAX_PAGE_SIZE}")

        start_utc = self._to_utc(start) if start else datetime.now(UTC) - timedelta(hours=24)
        stop_utc = self._to_utc(end) if end else datetime.now(UTC)

        if start_utc > stop_utc:
            raise ValueError("start must be <= end")

        params: dict[str, Any] = {
            "bucket_param": settings.INFLUX_BUCKET,
            "measurement_param": measurement,
            "start_param": start_utc,
            "stop_param": stop_utc,
        }

        flux_parts = [
            "from(bucket: bucket_param)",
            "|> range(start: start_param, stop: stop_param)",
            '|> filter(fn: (r) => r["_measurement"] == measurement_param)',
        ]

        if tags:
            filter_conditions: list[str] = []
            for index, (key, value) in enumerate(tags.items()):
                if isinstance(value, list):
                    normalized_values = [str(item) for item in value]
                    # Preserve order while de-duplicating.
                    unique_values = list(dict.fromkeys(normalized_values))
                    if not unique_values:
                        filter_conditions.append("false")
                        continue

                    if len(unique_values) == 1:
                        value_param = f"tag_val_{index}"
                        params[value_param] = unique_values[0]
                        filter_conditions.append(f'r["{key}"] == {value_param}')
                    elif len(unique_values) <= 8:
                        # For small IN lists OR checks are generally cheaper for Flux than contains
                        or_conditions: list[str] = []
                        for value_index, item in enumerate(unique_values):
                            value_param = f"tag_val_{index}_{value_index}"
                            params[value_param] = item
                            or_conditions.append(f'r["{key}"] == {value_param}')
                        filter_conditions.append(f"({' or '.join(or_conditions)})")
                    else:
                        list_param = f"tag_vals_{index}"
                        params[list_param] = unique_values
                        filter_conditions.append(f'contains(value: r["{key}"], set: {list_param})')
                else:
                    value_param = f"tag_val_{index}"
                    params[value_param] = str(value)
                    filter_conditions.append(f'r["{key}"] == {value_param}')

            if filter_conditions:
                flux_parts.append(f"|> filter(fn: (r) => {' and '.join(filter_conditions)})")

        if fields:
            params["field_set_param"] = fields
            flux_parts.append('|> filter(fn: (r) => contains(value: r["_field"], set: field_set_param))')

        if isinstance(cursor, bytes):
            cursor = cursor.decode("utf-8")

        if cursor:
            params["cursor_param"] = cursor
            flux_parts.append('|> filter(fn: (r) => r["_time"] < time(v: cursor_param))')

        if pivot:
            flux_parts.append('|> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")')
        else:  # when not pivoting we need to convert to string in case meassurements have mixed type fields
            flux_parts.append("|> toString()")

        # Collapse tag-grouped tables so sort/limit apply globally
        # required for stable cursor pagination
        flux_parts.append("|> group(columns: [])")
        flux_parts.append('|> sort(columns: ["_time"], desc: true)')
        if page_size is not None:
            limit_n = page_size + 1 if include_cursor_extra else page_size
            flux_parts.append(f"|> limit(n: {limit_n})")

        return "\n".join(flux_parts), params

    async def get_points(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> TelemetryPage:
        flux, params = self._build_base_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor,
            pivot=True,
            include_cursor_extra=True,
        )

        stream = await self._query_api.query_stream(flux, params=params)
        extra_tag_keys = {k for k in tags or {} if k not in CORE_TAG_KEYS}

        items: list[dict[str, Any]] = []
        async for record in stream:
            values = record.values

            if fields:
                field_values = {field: values[field] for field in fields if values.get(field) is not None}
            else:
                field_values = {
                    key: value
                    for key, value in values.items()
                    if key not in SYSTEM_COLUMNS
                    and key not in CORE_TAG_KEYS
                    and key not in extra_tag_keys
                    and value is not None
                }

            other_tags = {key: value for key in extra_tag_keys if (value := values.get(key)) is not None}

            items.append(
                {
                    "timestamp": values.get("_time"),
                    "measurement": values.get("_measurement"),
                    "patient_id": values.get("patient_id"),
                    "device_id": values.get("device_id"),
                    "wearable_id": values.get("wearable_id"),
                    "case_id": values.get("case_id"),
                    "context_id": values.get("context_id"),
                    "mapping_id": values.get("mapping_id"),
                    "code": values.get("code"),
                    "other_tags": other_tags,
                    "fields": field_values,
                }
            )

        return self._finalize_page(items, page_size)

    async def get_points_raw(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> TelemetryPage:
        flux, params = self._build_base_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor,
            pivot=False,
            include_cursor_extra=True,
        )

        stream = await self._query_api.query_stream(flux, params=params)

        items: list[dict[str, Any]] = []
        async for record in stream:
            values = record.values
            items.append(
                {
                    "timestamp": values.get("_time"),
                    "measurement": values.get("_measurement"),
                    "field": values.get("_field"),
                    "value": values.get("_value"),
                    **{key: value for key, value in values.items() if key not in SYSTEM_COLUMNS and value is not None},
                }
            )

        return self._finalize_page(items, page_size)

    async def stream_points(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        flux, params = self._build_base_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor,
            pivot=True,
            include_cursor_extra=False,
        )

        stream = await self._query_api.query_stream(flux, params=params)
        extra_tag_keys = {k for k in tags or {} if k not in CORE_TAG_KEYS}

        emitted = 0
        async for record in stream:
            values = record.values

            if fields:
                field_values = {field: values[field] for field in fields if values.get(field) is not None}
            else:
                field_values = {
                    key: value
                    for key, value in values.items()
                    if key not in SYSTEM_COLUMNS
                    and key not in CORE_TAG_KEYS
                    and key not in extra_tag_keys
                    and value is not None
                }

            other_tags = {key: value for key in extra_tag_keys if (value := values.get(key)) is not None}

            yield {
                "timestamp": values.get("_time"),
                "measurement": values.get("_measurement"),
                "patient_id": values.get("patient_id"),
                "device_id": values.get("device_id"),
                "wearable_id": values.get("wearable_id"),
                "case_id": values.get("case_id"),
                "context_id": values.get("context_id"),
                "mapping_id": values.get("mapping_id"),
                "code": values.get("code"),
                "other_tags": other_tags,
                "fields": field_values,
            }
            emitted += 1
            if emitted >= page_size:
                break

    async def stream_points_raw(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        flux, params = self._build_base_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor,
            pivot=False,
            include_cursor_extra=False,
        )

        stream = await self._query_api.query_stream(flux, params=params)

        emitted = 0
        async for record in stream:
            values = record.values
            yield {
                "timestamp": values.get("_time"),
                "measurement": values.get("_measurement"),
                "field": values.get("_field"),
                "value": values.get("_value"),
                **{key: value for key, value in values.items() if key not in SYSTEM_COLUMNS and value is not None},
            }
            emitted += 1
            if emitted >= page_size:
                break

    @staticmethod
    def _finalize_page(items: list[Any], page_size: int) -> TelemetryPage:
        has_more = len(items) > page_size
        if has_more:
            items = items[:page_size]

        next_cursor = None
        if has_more and items:
            last_ts = items[-1].get("timestamp")
            if isinstance(last_ts, datetime):
                next_cursor = last_ts.isoformat()

        return TelemetryPage(items=items, next_cursor=next_cursor)

    def _build_point(self, data: dict[str, Any]) -> Point:
        measurement = data["measurement"]
        timestamp = self._to_utc(data["timestamp"])

        point = Point(measurement).time(timestamp)

        for key, value in data.get("tags", {}).items():
            point.tag(str(key), str(value))

        field_count = 0
        for key, value in data.get("fields", {}).items():
            if value is None:
                continue
            point.field(str(key), value)
            field_count += 1

        if field_count == 0:
            raise ValueError("Point must contain at least one non-None field")

        return point

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
