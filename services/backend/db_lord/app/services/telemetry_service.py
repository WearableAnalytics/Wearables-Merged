from collections.abc import AsyncIterator, Iterable
from datetime import datetime

from app.db.influx.telemetry import TelemetryRepo
from app.schemas.telemetry import TelemetryCreate
from app.telemetry.constants import TELEMETRY_DEFAULT_LIMIT
from app.telemetry.types import (
    MeasurementSchema,
    RawTelemetryItem,
    StructuredTelemetryItem,
    TelemetryTags,
    TelemetryWindowResult,
)


class TelemetryService:
    def __init__(self, repo: TelemetryRepo):
        self.repo = repo

    async def record_telemetry(self, item_in: TelemetryCreate) -> None:
        await self.repo.write_point(item_in)

    async def record_batch(self, items_in: Iterable[TelemetryCreate]) -> None:
        await self.repo.write_batch(items_in)

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
        return await self.repo.read_window(measurement, start, end, tags, fields, limit, bucket)

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
        return await self.repo.read_raw_window(measurement, start, end, tags, fields, limit, bucket)

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
        return self.repo.stream_structured(measurement, start, end, tags, fields, limit, bucket)

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
        return self.repo.stream_raw(measurement, start, end, tags, fields, limit, bucket)

    async def list_measurements(self, bucket: str | None = None) -> list[str]:
        return await self.repo.list_measurements(bucket)

    async def describe_measurement(self, measurement: str, bucket: str | None = None) -> MeasurementSchema:
        return await self.repo.describe_measurement(measurement, bucket=bucket)

    async def get_measurement_tag_values(
        self,
        measurement: str,
        tag_key: str,
        limit: int | None = 500,
        bucket: str | None = None,
    ) -> list[str]:
        return await self.repo.get_measurement_tag_values(measurement, tag_key, limit, bucket)
