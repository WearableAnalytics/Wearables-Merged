from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime

from fastapi_pagination.types import Cursor

from app.db.influx.repos.telemetry_repo import TelemetryPage, TelemetryRepo
from app.schemas.telemetry import TelemetryCreate


class TelemetryService:
    def __init__(self, repo: TelemetryRepo):
        self.repo = repo

    async def record_telemetry(self, item_in: TelemetryCreate) -> None:
        point = self._create_to_dict(item_in)
        await self.repo.write_point(point)

    async def record_batch(self, items_in: Iterable[TelemetryCreate]) -> None:
        points = [self._create_to_dict(item) for item in items_in]
        if points:
            await self.repo.write_batch(points)

    async def read_telemetry(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> TelemetryPage:
        return await self.repo.get_points(measurement, start, end, tags, fields, page_size, cursor)

    async def read_telemetry_raw(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> TelemetryPage:
        return await self.repo.get_points_raw(measurement, start, end, tags, fields, page_size, cursor)

    def stream_telemetry(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        return self.repo.stream_points(measurement, start, end, tags, fields, page_size, cursor)

    def stream_telemetry_raw(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str | list[str]] | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        return self.repo.stream_points_raw(measurement, start, end, tags, fields, page_size, cursor)

    # TODO: finally remove this cause why tf did i even create this in the first place
    def _create_to_dict(self, item: TelemetryCreate) -> dict[str, object]:
        timestamp = item.timestamp or datetime.now(UTC)

        tags = {
            "patient_id": item.patient_id,
            "case_id": item.case_id,
            "device_id": item.device_id,
            "wearable_id": item.wearable_id,
            "mapping_id": item.mapping_id,
            "code": item.code,
        }
        if item.context_id:
            tags["context_id"] = item.context_id
        if item.other_tags:
            tags.update(item.other_tags)

        return {
            "measurement": item.measurement,
            "timestamp": timestamp,
            "tags": tags,
            "fields": item.fields or {},
        }
