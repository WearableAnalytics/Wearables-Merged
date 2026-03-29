from collections.abc import AsyncIterator, Iterable
from datetime import datetime

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write.point import Point

from app.core.config import settings
from app.core.utils import to_utc
from app.db.influx.telemetry.queries import normalize_measurement, resolve_bucket
from app.db.influx.telemetry.reads import TelemetryReader
from app.db.influx.telemetry.schema import TelemetrySchemaStore
from app.schemas.telemetry import TelemetryCreate
from app.telemetry.constants import TELEMETRY_DEFAULT_LIMIT, TELEMETRY_MAX_LIMIT, TELEMETRY_TAG_NAMES
from app.telemetry.types import (
    MeasurementSchema,
    RawTelemetryItem,
    StructuredTelemetryItem,
    TelemetryTags,
    TelemetryWindowResult,
)


class TelemetryRepo:
    MAX_LIMIT = TELEMETRY_MAX_LIMIT

    def __init__(self, client: InfluxDBClientAsync):
        self._client = client
        self._write_api = self._client.write_api()
        self._query_api = self._client.query_api()
        self._schema_store = TelemetrySchemaStore(self._query_api)
        self._reader = TelemetryReader(
            self._query_api,
            settings.INFLUX_BUCKET,
            self.MAX_LIMIT,
        )

    async def write_point(self, point: TelemetryCreate) -> None:
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=self._build_point(point))

    async def write_batch(self, points: Iterable[TelemetryCreate]) -> None:
        batch = [self._build_point(point) for point in points]
        if not batch:
            return
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=batch)

    async def read_window(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int = TELEMETRY_DEFAULT_LIMIT,
        bucket: str | None = None,
    ) -> TelemetryWindowResult[StructuredTelemetryItem]:
        return await self._reader.read_window(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            limit=limit,
            bucket=bucket,
        )

    async def read_raw_window(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int = TELEMETRY_DEFAULT_LIMIT,
        bucket: str | None = None,
    ) -> TelemetryWindowResult[RawTelemetryItem]:
        return await self._reader.read_raw_window(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            limit=limit,
            bucket=bucket,
        )

    def stream_structured(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        bucket: str | None = None,
    ) -> AsyncIterator[StructuredTelemetryItem]:
        return self._reader.stream_structured(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            limit=limit,
            bucket=bucket,
        )

    def stream_raw(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int | None = None,
        bucket: str | None = None,
    ) -> AsyncIterator[RawTelemetryItem]:
        return self._reader.stream_raw(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            fields=fields,
            limit=limit,
            bucket=bucket,
        )

    async def list_measurements(self, bucket: str | None = None) -> list[str]:
        """Returns a list of measurement names in the specified bucket. Can be used through GraphQL."""
        return await self._schema_store.list_measurements(bucket=resolve_bucket(settings.INFLUX_BUCKET, bucket))

    async def describe_measurement(self, measurement: str, bucket: str | None = None) -> MeasurementSchema:
        """Returns the schema summary for one measurement:
        - tag keys
        - field keys"""
        normalized_measurement = normalize_measurement(measurement)
        if normalized_measurement is None:
            raise ValueError("measurement must be a non-empty string")
        return await self._schema_store.get_measurement_schema(
            normalized_measurement,
            bucket=resolve_bucket(settings.INFLUX_BUCKET, bucket),
        )

    async def get_measurement_tag_values(
        self,
        measurement: str,
        tag_key: str,
        limit: int | None = 500,
        bucket: str | None = None,
    ) -> list[str]:
        normalized_measurement = normalize_measurement(measurement)
        if normalized_measurement is None:
            raise ValueError("measurement must be a non-empty string")
        return await self._schema_store.get_measurement_tag_values(
            normalized_measurement,
            tag_key,
            limit=limit,
            bucket=resolve_bucket(settings.INFLUX_BUCKET, bucket),
        )

    def _build_point(self, item: TelemetryCreate) -> Point:
        tags: dict[str, str] = {}
        for tag_key in TELEMETRY_TAG_NAMES:
            value = getattr(item, tag_key, None)
            if value is not None:
                tags[tag_key] = str(value)

        for key, value in item.other_tags.items():
            tags[str(key)] = str(value)

        fields = {str(key): value for key, value in item.fields.items() if value is not None}
        if not fields:
            raise ValueError("Point must contain at least one non-None field")

        payload: dict[str, object] = {
            "measurement": item.measurement,
            "tags": tags,
            "fields": fields,
        }
        if item.timestamp is not None:
            payload["time"] = to_utc(item.timestamp)
        return Point.from_dict(payload)
