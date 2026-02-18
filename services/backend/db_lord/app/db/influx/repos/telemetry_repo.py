import asyncio
import base64
import json
from collections import OrderedDict
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi_pagination.types import Cursor
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write.point import Point

from app.core.config import settings
from app.schemas.telemetry import TelemetryCreate

SYSTEM_COLUMNS = frozenset(
    ("result", "table", "_start", "_stop", "_time", "_measurement", "_field", "_value", "_cursor_key")
)
CORE_TAG_KEYS = frozenset(("patient_id", "device_id", "wearable_id", "case_id", "context_id", "mapping_id", "code"))
CURSOR_VERSION = 1
CURSOR_SEPARATOR = "|"


@dataclass(frozen=True)
class TelemetryPage:
    items: list[Any]
    next_cursor: str | None


@dataclass(frozen=True)
class MeasurementSchema:
    tag_keys: tuple[str, ...]
    field_keys: frozenset[str]


@dataclass(frozen=True)
class MeasurementSchemaCacheEntry:
    schema: MeasurementSchema
    expires_at: datetime


@dataclass(frozen=True)
class CursorToken:
    timestamp: datetime
    key: str
    stop: datetime


class TelemetryRepo:
    """Repository for InfluxDB telemetry data."""

    MAX_PAGE_SIZE = 10_000

    def __init__(self, client: InfluxDBClientAsync):
        self._client = client
        self._write_api = self._client.write_api()
        self._query_api = self._client.query_api()
        self._schema_cache_ttl = timedelta(seconds=max(1, settings.INFLUX_SCHEMA_CACHE_TTL_SECONDS))
        self._schema_cache_max_measurements = max(1, settings.INFLUX_SCHEMA_CACHE_MAX_MEASUREMENTS)
        self._schema_lookback = settings.INFLUX_SCHEMA_LOOKBACK
        self._schema_cache: OrderedDict[str, MeasurementSchemaCacheEntry] = OrderedDict()
        self._schema_cache_lock = asyncio.Lock()

    async def write_point(self, point: TelemetryCreate) -> None:
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=self._build_point(point))

    async def write_batch(self, points: Iterable[TelemetryCreate]) -> None:
        batch = [self._build_point(point) for point in points]
        if not batch:
            return
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=batch)

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
        schema = await self._get_measurement_schema(measurement)
        cursor_token = self._decode_cursor(cursor)

        flux, params, stop_utc = self._build_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor_token,
            schema=schema,
            pivot=True,
            include_cursor_extra=True,
            include_field_in_cursor=False,
        )

        stream = await self._query_api.query_stream(flux, params=params)

        rows: list[tuple[dict[str, Any], datetime | None, str]] = []
        async for record in stream:
            values = record.values
            field_values, other_tags = self._split_structured_values(values, fields, schema)

            rows.append(
                (
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
                    },
                    values.get("_time"),
                    self._cursor_key_from_values(values),
                )
            )

        return self._finalize_page(rows, page_size, stop_utc)

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
        schema = await self._get_measurement_schema(measurement)
        cursor_token = self._decode_cursor(cursor)

        flux, params, stop_utc = self._build_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor_token,
            schema=schema,
            pivot=False,
            include_cursor_extra=True,
            include_field_in_cursor=True,
        )

        stream = await self._query_api.query_stream(flux, params=params)

        rows: list[tuple[dict[str, Any], datetime | None, str]] = []
        async for record in stream:
            values = record.values
            rows.append(
                (
                    {
                        "timestamp": values.get("_time"),
                        "measurement": values.get("_measurement"),
                        "field": values.get("_field"),
                        "value": values.get("_value"),
                        **{
                            key: value
                            for key, value in values.items()
                            if key not in SYSTEM_COLUMNS and value is not None
                        },
                    },
                    values.get("_time"),
                    self._cursor_key_from_values(values),
                )
            )

        return self._finalize_page(rows, page_size, stop_utc)

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
        schema = await self._get_measurement_schema(measurement)
        cursor_token = self._decode_cursor(cursor)

        flux, params, _ = self._build_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor_token,
            schema=schema,
            pivot=True,
            include_cursor_extra=False,
            include_field_in_cursor=False,
        )

        stream = await self._query_api.query_stream(flux, params=params)
        emitted = 0
        async for record in stream:
            values = record.values
            field_values, other_tags = self._split_structured_values(values, fields, schema)

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
        schema = await self._get_measurement_schema(measurement)
        cursor_token = self._decode_cursor(cursor)

        flux, params, _ = self._build_flux_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            page_size=page_size,
            cursor=cursor_token,
            schema=schema,
            pivot=False,
            include_cursor_extra=False,
            include_field_in_cursor=True,
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

    def _build_flux_query(
        self,
        measurement: str,
        start: datetime | None,
        end: datetime | None,
        tags: dict[str, str | list[str]] | None,
        fields: list[str] | None,
        page_size: int | None,
        cursor: CursorToken | None,
        schema: MeasurementSchema,
        *,
        pivot: bool,
        include_cursor_extra: bool,
        include_field_in_cursor: bool,
    ) -> tuple[str, dict[str, Any], datetime]:
        if not measurement:
            raise ValueError("measurement must be a non-empty string")

        if page_size is not None:
            if page_size < 1:
                raise ValueError("page_size must be at least 1")
            if page_size > self.MAX_PAGE_SIZE:
                raise ValueError(f"page_size cannot exceed {self.MAX_PAGE_SIZE}")

        start_utc = self._to_utc(start) if start else datetime.now(UTC) - timedelta(hours=24)
        stop_utc = cursor.stop if cursor else (self._to_utc(end) if end else datetime.now(UTC))

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
                column = f"r[{json.dumps(key)}]"
                if isinstance(value, list):
                    normalized_values = [str(item) for item in value]
                    unique_values = list(dict.fromkeys(normalized_values))
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
                else:
                    value_param = f"tag_val_{index}"
                    params[value_param] = str(value)
                    filter_conditions.append(f"{column} == {value_param}")

            if filter_conditions:
                flux_parts.append(f"|> filter(fn: (r) => {' and '.join(filter_conditions)})")

        if fields:
            deduped_fields = list(dict.fromkeys(str(field) for field in fields if field))
            if deduped_fields:
                params["field_set_param"] = deduped_fields
                flux_parts.append('|> filter(fn: (r) => contains(value: r["_field"], set: field_set_param))')

        keep_columns = ["_time", "_measurement", "_field", "_value", *schema.tag_keys]
        if tags:
            keep_columns.extend(str(tag_key) for tag_key in tags)
        deduped_keep_columns = list(dict.fromkeys(keep_columns))
        flux_parts.append(f"|> keep(columns: [{', '.join(json.dumps(column) for column in deduped_keep_columns)}])")

        if pivot:
            flux_parts.append('|> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")')

        flux_parts.append("|> group(columns: [])")

        key_columns = [*schema.tag_keys]
        if include_field_in_cursor:
            key_columns.append("_field")

        flux_parts.append(
            f"|> map(fn: (r) => ({{ r with _cursor_key: {self._build_cursor_key_expression(key_columns)} }}))"
        )

        if cursor:
            params["cursor_time_param"] = cursor.timestamp
            params["cursor_key_param"] = cursor.key
            flux_parts.append(
                '|> filter(fn: (r) => r["_time"] < cursor_time_param or '
                '(r["_time"] == cursor_time_param and r["_cursor_key"] < cursor_key_param))'
            )

        flux_parts.append('|> sort(columns: ["_time", "_cursor_key"], desc: true)')
        if page_size is not None:
            limit_n = page_size + 1 if include_cursor_extra else page_size
            flux_parts.append(f"|> limit(n: {limit_n})")

        return "\n".join(['import "strings"', *flux_parts]), params, stop_utc

    async def _get_measurement_schema(self, measurement: str) -> MeasurementSchema:
        cached = self._schema_cache.get(measurement)
        if cached and cached.expires_at > datetime.now(UTC):
            self._schema_cache.move_to_end(measurement)
            return cached.schema

        async with self._schema_cache_lock:
            now = datetime.now(UTC)
            cached = self._schema_cache.get(measurement)
            if cached and cached.expires_at > now:
                self._schema_cache.move_to_end(measurement)
                return cached.schema

            schema_start = self._schema_start_time(now)
            tag_keys = await self._get_measurement_tag_keys(measurement, schema_start)
            field_keys = await self._get_measurement_field_keys(measurement, schema_start)

            schema = MeasurementSchema(
                tag_keys=tuple(sorted(tag_keys)),
                field_keys=frozenset(field_keys),
            )

            self._schema_cache[measurement] = MeasurementSchemaCacheEntry(
                schema=schema,
                expires_at=now + self._schema_cache_ttl,
            )
            self._schema_cache.move_to_end(measurement)
            while len(self._schema_cache) > self._schema_cache_max_measurements:
                self._schema_cache.popitem(last=False)

            return schema

    async def _get_measurement_tag_keys(self, measurement: str, schema_start: datetime) -> set[str]:
        flux = "\n".join(
            [
                'import "influxdata/influxdb/schema"',
                "schema.measurementTagKeys(",
                "  bucket: bucket_param,",
                "  measurement: measurement_param,",
                "  start: schema_start_param,",
                ")",
            ]
        )
        params = {
            "bucket_param": settings.INFLUX_BUCKET,
            "measurement_param": measurement,
            "schema_start_param": schema_start,
        }

        stream = await self._query_api.query_stream(flux, params=params)
        keys: set[str] = set()
        async for record in stream:
            value = record.values.get("_value")
            if isinstance(value, str) and value and not value.startswith("_"):
                keys.add(value)

        return keys

    async def _get_measurement_field_keys(self, measurement: str, schema_start: datetime) -> set[str]:
        flux = "\n".join(
            [
                'import "influxdata/influxdb/schema"',
                "schema.measurementFieldKeys(",
                "  bucket: bucket_param,",
                "  measurement: measurement_param,",
                "  start: schema_start_param,",
                ")",
            ]
        )
        params = {
            "bucket_param": settings.INFLUX_BUCKET,
            "measurement_param": measurement,
            "schema_start_param": schema_start,
        }

        stream = await self._query_api.query_stream(flux, params=params)
        keys: set[str] = set()
        async for record in stream:
            value = record.values.get("_value")
            if isinstance(value, str) and value and not value.startswith("_"):
                keys.add(value)

        return keys

    @staticmethod
    def _split_structured_values(
        values: dict[str, Any],
        fields: list[str] | None,
        schema: MeasurementSchema,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        other_tags: dict[str, Any] = {}
        for key in schema.tag_keys:
            if key in CORE_TAG_KEYS:
                continue
            value = values.get(key)
            if value is not None:
                other_tags[key] = value

        if fields:
            selected_fields = [field for field in fields if field in schema.field_keys]
        else:
            selected_fields = sorted(schema.field_keys)

        field_values: dict[str, Any] = {}
        for field_key in selected_fields:
            value = values.get(field_key)
            if value is not None:
                field_values[field_key] = value

        return field_values, other_tags

    @staticmethod
    def _build_cursor_key_expression(columns: list[str]) -> str:
        if not columns:
            return '""'

        backslash = json.dumps("\\")
        escaped_backslash = json.dumps("\\\\")
        separator = json.dumps(CURSOR_SEPARATOR)
        escaped_separator = json.dumps(f"\\{CURSOR_SEPARATOR}")
        components = []
        for column in columns:
            col_ref = f"r[{json.dumps(column)}]"
            value_expr = f'if exists {col_ref} then string(v: {col_ref}) else ""'
            escaped_value_expr = (
                "strings.replaceAll("
                f"v: strings.replaceAll(v: {value_expr}, t: {backslash}, u: {escaped_backslash}), "
                f"t: {separator}, u: {escaped_separator}"
                ")"
            )
            components.append(escaped_value_expr)
        return f"strings.joinStr(arr: [{', '.join(components)}], v: {json.dumps(CURSOR_SEPARATOR)})"

    @staticmethod
    def _cursor_key_from_values(values: dict[str, Any]) -> str:
        key = values.get("_cursor_key")
        if key is None:
            return ""
        return str(key)

    @classmethod
    def _finalize_page(
        cls,
        rows: list[tuple[dict[str, Any], datetime | None, str]],
        page_size: int,
        stop: datetime,
    ) -> TelemetryPage:
        has_more = len(rows) > page_size
        if has_more:
            rows = rows[:page_size]

        next_cursor = None
        if has_more and rows:
            last_ts = rows[-1][1]
            last_key = rows[-1][2]
            if isinstance(last_ts, datetime):
                next_cursor = cls._encode_cursor(last_ts, last_key, stop)

        return TelemetryPage(items=[item for item, _, _ in rows], next_cursor=next_cursor)

    @staticmethod
    def _encode_cursor(timestamp: datetime, key: str, stop: datetime) -> str:
        payload = {
            "v": CURSOR_VERSION,
            "t": TelemetryRepo._to_utc(timestamp).isoformat(),
            "k": key,
            "s": TelemetryRepo._to_utc(stop).isoformat(),
        }
        encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
        return encoded.rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: Cursor | None) -> CursorToken | None:
        if cursor is None:
            return None

        raw_cursor = cursor.decode("utf-8") if isinstance(cursor, bytes) else str(cursor)
        if not raw_cursor:
            return None

        padded = raw_cursor + "=" * (-len(raw_cursor) % 4)
        try:
            payload_raw = base64.urlsafe_b64decode(padded.encode("ascii"))
            payload = json.loads(payload_raw)
        except Exception as exc:
            raise ValueError("Invalid telemetry cursor.") from exc

        if not isinstance(payload, dict):
            raise ValueError("Invalid telemetry cursor.")

        if payload.get("v") != CURSOR_VERSION:
            raise ValueError("Unsupported telemetry cursor version.")

        ts_raw = payload.get("t")
        key_raw = payload.get("k")
        stop_raw = payload.get("s")
        if not isinstance(ts_raw, str) or not isinstance(key_raw, str) or not isinstance(stop_raw, str):
            raise ValueError("Invalid telemetry cursor.")

        try:
            timestamp = datetime.fromisoformat(ts_raw)
            stop = datetime.fromisoformat(stop_raw)
        except ValueError as exc:
            raise ValueError("Invalid telemetry cursor timestamp.") from exc

        return CursorToken(
            timestamp=TelemetryRepo._to_utc(timestamp),
            key=key_raw,
            stop=TelemetryRepo._to_utc(stop),
        )

    def _build_point(self, item: TelemetryCreate) -> Point:
        timestamp = item.timestamp or datetime.now(UTC)
        point = Point(item.measurement).time(self._to_utc(timestamp))

        point.tag("patient_id", str(item.patient_id))
        point.tag("case_id", str(item.case_id))
        point.tag("device_id", str(item.device_id))
        point.tag("wearable_id", str(item.wearable_id))
        point.tag("mapping_id", str(item.mapping_id))
        point.tag("code", str(item.code))

        if item.context_id is not None:
            point.tag("context_id", str(item.context_id))

        for key, value in item.other_tags.items():
            point.tag(str(key), str(value))

        field_count = 0
        for key, value in item.fields.items():
            if value is None:
                continue
            point.field(str(key), value)
            field_count += 1

        if field_count == 0:
            raise ValueError("Point must contain at least one non-None field")

        return point

    def _schema_start_time(self, now: datetime) -> datetime:
        if self._schema_lookback <= 0:
            return datetime.fromtimestamp(0, UTC)
        return now - timedelta(seconds=self._schema_lookback)

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
