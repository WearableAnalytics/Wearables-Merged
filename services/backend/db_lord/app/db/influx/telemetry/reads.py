"""Telemetry reads for InfluxDB.

Window reads expand backward over time so pages can stay complete and structured items can be grouped.
"""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from influxdb_client.client.query_api_async import QueryApiAsync

from app.core.config import settings
from app.core.utils import ordered_unique, to_utc
from app.db.influx.telemetry.queries import build_flux_query, normalize_measurement, resolve_bucket
from app.telemetry.constants import TELEMETRY_MAX_LIMIT
from app.telemetry.types import (
    RawTelemetryItem,
    StructuredTelemetryItem,
    TelemetryRecordTags,
    TelemetryTags,
    TelemetryWindowResult,
)

RESERVED_RESULT_COLUMNS: frozenset[str] = frozenset(
    ("result", "table", "_start", "_stop", "_time", "_measurement", "_field", "_value")
)

type RecordValues = dict[str, Any]
type TimestampedRow[TItem] = tuple[TItem, datetime | None]
type StructuredGroupKey = tuple[datetime, str, tuple[tuple[str, str], ...]]


class TelemetryReader:
    """Read raw and structured telemetry from InfluxDB."""

    def __init__(
        self,
        query_api: QueryApiAsync,
        default_bucket: str,
        max_limit: int = TELEMETRY_MAX_LIMIT,
    ):
        self._query_api = query_api
        self._default_bucket = default_bucket
        self._max_limit = max_limit

    async def read_window(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        limit: int,
        bucket: str | None,
    ) -> TelemetryWindowResult[StructuredTelemetryItem]:
        """Return one page of grouped telemetry items."""
        rows = await self._load_structured_window_rows(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            limit=limit,
            bucket=bucket,
        )
        return self._finalize_window_result(rows, limit)

    async def read_raw_window(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        limit: int,
        bucket: str | None,
    ) -> TelemetryWindowResult[RawTelemetryItem]:
        """Return one page of raw telemetry rows."""
        rows = await self._load_raw_window_rows(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            limit=limit,
            bucket=bucket,
        )
        return self._finalize_window_result(rows, limit)

    async def stream_structured(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        limit: int | None,
        bucket: str | None,
    ) -> AsyncIterator[StructuredTelemetryItem]:
        if limit is not None:
            limit = self._validate_limit(limit)

        yielded = 0
        async for item in self._iter_structured_stream_items(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            bucket=bucket,
        ):
            yield item
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    async def stream_raw(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        limit: int | None,
        bucket: str | None,
    ) -> AsyncIterator[RawTelemetryItem]:
        if limit is not None:
            limit = self._validate_limit(limit)
        flux, params = await self._prepare_query(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            bucket=bucket,
            row_limit=limit,
        )
        yielded = 0
        async for values in self._iter_query_values(flux, params):
            yield self._raw_item_from_values(values)
            yielded += 1
            if limit is not None and yielded >= limit:
                return

    async def _prepare_query(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        bucket: str | None,
        row_limit: int | None,
    ) -> tuple[str, dict[str, object]]:
        bucket_name = resolve_bucket(self._default_bucket, bucket)
        normalized_measurement = normalize_measurement(measurement)
        flux, params = build_flux_query(
            bucket=bucket_name,
            measurement=normalized_measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            row_limit=row_limit,
        )
        return flux, params

    async def _iter_query_values(self, flux: str, params: dict[str, object]) -> AsyncIterator[RecordValues]:
        stream = await self._query_api.query_stream(flux, params=params)
        async for record in stream:
            yield record.values

    async def _load_raw_window_rows(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        limit: int,
        bucket: str | None,
    ) -> list[TimestampedRow[RawTelemetryItem]]:
        """Load enough raw rows to build one complete page."""
        limit = self._validate_limit(limit)
        requested_start, requested_end = self._requested_time_bounds(start, end)
        current_end = requested_end
        window_seconds = self._initial_window_seconds()
        rows: list[TimestampedRow[RawTelemetryItem]] = []

        while current_end > requested_start:
            window_start = self._window_start(
                current_end,
                requested_start,
                window_seconds,
            )
            flux, params = await self._prepare_query(
                measurement=measurement,
                start=window_start,
                end=current_end,
                tags=tags,
                fields=fields,
                bucket=bucket,
                row_limit=None,
            )
            async for values in self._iter_query_values(flux, params):
                item = self._raw_item_from_values(values)
                timestamp = item["timestamp"]
                rows.append((item, to_utc(timestamp) if timestamp is not None else None))
            current_end = window_start

            sorted_rows = self._sort_window_rows(rows)
            if not sorted_rows:
                window_seconds = self._next_window_seconds(window_seconds)
                continue

            visible_rows = self._boundary_complete_rows(sorted_rows, limit)
            if current_end <= requested_start:
                return sorted_rows
            if len(visible_rows) >= limit and len(visible_rows) < len(sorted_rows):
                return sorted_rows

            window_seconds = self._next_window_seconds(window_seconds)

        return self._sort_window_rows(rows)

    async def _load_structured_window_rows(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        limit: int,
        bucket: str | None,
    ) -> list[TimestampedRow[StructuredTelemetryItem]]:
        """Load enough rows to build one grouped, complete page."""
        limit = self._validate_limit(limit)
        bucket_name = resolve_bucket(self._default_bucket, bucket)
        normalized_measurement = normalize_measurement(measurement)
        requested_start, requested_end = self._requested_time_bounds(start, end)
        window_seconds = self._initial_window_seconds()
        current_end = requested_end
        grouped_items: dict[StructuredGroupKey, StructuredTelemetryItem] = {}
        selected_fields = ordered_unique(field for field in fields if field) if fields else None

        while current_end > requested_start:
            window_start = self._window_start(
                current_end,
                requested_start,
                window_seconds,
            )
            flux, params = await self._prepare_query(
                measurement=normalized_measurement,
                start=window_start,
                end=current_end,
                tags=tags,
                fields=fields,
                bucket=bucket_name,
                row_limit=None,
            )
            rows = [values async for values in self._iter_query_values(flux, params)]
            self._accumulate_structured_rows(
                grouped_items,
                rows,
                selected_fields,
            )
            current_end = window_start

            grouped_rows = self._sort_window_rows(
                [
                    (
                        item,
                        to_utc(item["timestamp"]),
                    )
                    for item in grouped_items.values()
                ]
            )
            if not grouped_rows:
                window_seconds = self._next_window_seconds(window_seconds)
                continue

            visible_rows = self._boundary_complete_rows(grouped_rows, limit)
            if current_end <= requested_start:
                return grouped_rows
            if len(visible_rows) >= limit and len(visible_rows) < len(grouped_rows):
                return grouped_rows

            window_seconds = self._next_window_seconds(window_seconds)

        grouped_rows = self._sort_window_rows(
            [
                (
                    item,
                    to_utc(item["timestamp"]),
                )
                for item in grouped_items.values()
            ]
        )
        return grouped_rows

    def _accumulate_structured_rows(
        self,
        grouped_items: dict[StructuredGroupKey, StructuredTelemetryItem],
        rows: list[RecordValues],
        selected_fields: list[str] | None,
    ) -> None:
        """Accumulate raw rows into grouped structured items."""
        for row in rows:
            raw_timestamp = row.get("_time")
            timestamp = to_utc(raw_timestamp) if isinstance(raw_timestamp, datetime) else None
            raw_measurement = row.get("_measurement")
            measurement = raw_measurement if isinstance(raw_measurement, str) else None
            if timestamp is None or measurement is None:
                # This shouldnt be possible but if you drop _time or do something weird here is a guard :)
                # (did it to tigthen type hints)
                raise ValueError("Structured telemetry rows must include _time and _measurement.")
            tags = self._row_tags(row)
            group_key = (timestamp, measurement, tuple(sorted(tags.items())))
            item = grouped_items.get(group_key)
            if item is None:
                item = StructuredTelemetryItem(
                    timestamp=timestamp,
                    measurement=measurement,
                    tags=tags,
                    fields={},
                )
                grouped_items[group_key] = item

            field_key = row.get("_field")
            if not isinstance(field_key, str) or not field_key:
                continue
            if selected_fields is not None and field_key not in selected_fields:
                continue
            value = row.get("_value")
            if value is not None:
                item["fields"][field_key] = value

    async def _iter_structured_stream_items(
        self,
        measurement: str | None,
        start: datetime | None,
        end: datetime | None,
        tags: TelemetryTags | None,
        fields: list[str] | None,
        bucket: str | None,
    ) -> AsyncIterator[StructuredTelemetryItem]:
        """Stream grouped telemetry in bounded backward chunks."""
        bucket_name = resolve_bucket(self._default_bucket, bucket)
        normalized_measurement = normalize_measurement(measurement)
        selected_fields = ordered_unique(field for field in fields if field) if fields else None
        requested_start, requested_end = self._requested_time_bounds(start, end)
        current_end = requested_end
        chunk_seconds = max(1, settings.INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS)

        while current_end > requested_start:
            window_start = self._window_start(
                current_end,
                requested_start,
                chunk_seconds,
            )
            flux, params = await self._prepare_query(
                measurement=normalized_measurement,
                start=window_start,
                end=current_end,
                tags=tags,
                fields=fields,
                bucket=bucket_name,
                row_limit=None,
            )
            grouped_items: dict[StructuredGroupKey, StructuredTelemetryItem] = {}
            rows = [values async for values in self._iter_query_values(flux, params)]
            self._accumulate_structured_rows(
                grouped_items,
                rows,
                selected_fields,
            )
            grouped_rows = self._sort_window_rows(
                [
                    (
                        item,
                        to_utc(item["timestamp"]),
                    )
                    for item in grouped_items.values()
                ]
            )
            for item, _timestamp in grouped_rows:
                yield item
            current_end = window_start

    @staticmethod
    def _raw_item_from_values(values: RecordValues) -> RawTelemetryItem:
        return {
            "timestamp": values.get("_time"),
            "measurement": values.get("_measurement"),
            "field": values.get("_field"),
            "value": values.get("_value"),
            "tags": TelemetryReader._row_tags(values),
        }

    @classmethod
    def _row_tags(cls, values: RecordValues) -> TelemetryRecordTags:
        return {
            key: normalized_value
            for key, value in values.items()
            if key not in RESERVED_RESULT_COLUMNS
            if (normalized_value := None if value in (None, "") else str(value)) is not None
        }

    @staticmethod
    def _sort_window_rows[TItem](rows: Sequence[TimestampedRow[TItem]]) -> list[TimestampedRow[TItem]]:
        return sorted(rows, key=lambda row: row[1] or datetime.min.replace(tzinfo=UTC), reverse=True)

    @staticmethod
    def _requested_time_bounds(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
        requested_end = to_utc(end) if end is not None else datetime.now(UTC)
        requested_start = to_utc(start) if start is not None else requested_end - timedelta(hours=24)
        if requested_start > requested_end:
            raise ValueError("start must be <= end")
        return requested_start, requested_end

    @staticmethod
    def _window_start(current_end: datetime, requested_start: datetime, seconds: int) -> datetime:
        return max(requested_start, current_end - timedelta(seconds=seconds))

    @staticmethod
    def _initial_window_seconds() -> int:
        return min(
            max(1, settings.INFLUX_STRUCTURED_READ_INITIAL_WINDOW_SECONDS),
            max(1, settings.INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS),
        )

    @staticmethod
    def _next_window_seconds(current_seconds: int) -> int:
        max_window_seconds = max(1, settings.INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS)
        growth_factor = max(settings.INFLUX_STRUCTURED_READ_WINDOW_GROWTH_FACTOR, 1.0)
        if current_seconds >= max_window_seconds:
            return max_window_seconds
        return min(max_window_seconds, max(current_seconds + 1, int(current_seconds * growth_factor)))

    @classmethod
    def _boundary_complete_rows[TItem](
        cls, rows: Sequence[TimestampedRow[TItem]], limit: int
    ) -> list[TimestampedRow[TItem]]:
        """Return at least `limit` rows (hopefully) without splitting on timestamp boundary."""
        if len(rows) <= limit:
            return list(rows)

        boundary_timestamp = rows[limit - 1][1]
        if not isinstance(boundary_timestamp, datetime):
            return list(rows[:limit])

        cutoff_index = len(rows)
        for index in range(limit, len(rows)):
            row_timestamp = rows[index][1]
            if isinstance(row_timestamp, datetime) and row_timestamp < boundary_timestamp:
                cutoff_index = index
                break
        return list(rows[:cutoff_index])

    def _validate_limit(self, limit: int) -> int:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if limit > self._max_limit:
            raise ValueError(f"limit cannot exceed {self._max_limit}")
        return limit

    @classmethod
    def _finalize_window_result[TItem](
        cls, rows: list[TimestampedRow[TItem]], limit: int
    ) -> TelemetryWindowResult[TItem]:
        if not rows:
            return TelemetryWindowResult[TItem](items=[], has_more=False, next_end=None)

        visible_rows = cls._boundary_complete_rows(rows, limit)
        has_more = len(visible_rows) < len(rows)
        next_end = visible_rows[-1][1] if has_more and visible_rows else None
        return TelemetryWindowResult[TItem](
            items=[item for item, _ in visible_rows],
            has_more=has_more,
            next_end=next_end if isinstance(next_end, datetime) else None,
        )
