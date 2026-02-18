from collections.abc import AsyncIterator, Iterable
from datetime import datetime

from fastapi_pagination.types import Cursor

from app.db.influx.repos.telemetry_repo import TelemetryPage, TelemetryRepo
from app.schemas.telemetry import TelemetryCreate


class TelemetryService:
    def __init__(self, repo: TelemetryRepo):
        self.repo = repo

    async def record_telemetry(self, item_in: TelemetryCreate) -> None:
        await self.repo.write_point(item_in)

    async def record_batch(self, items_in: Iterable[TelemetryCreate]) -> None:
        await self.repo.write_batch(items_in)

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
