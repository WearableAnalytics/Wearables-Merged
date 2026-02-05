from collections.abc import Iterable
from datetime import UTC, datetime

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
        tags: dict[str, str] | None = None,
        page_size: int = 100,
        cursor: str | None = None,
    ) -> TelemetryPage:
        return await self.repo.get_points(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
            page_size=page_size,
            cursor=cursor,
        )

    def _create_to_dict(self, item: TelemetryCreate) -> dict:
        timestamp = item.timestamp or datetime.now(UTC)

        tags = {
            "patient_id": str(item.patient_id),
            "case_id": str(item.case_id),
            "device_id": str(item.device_id),
        }
        if item.tags:
            tags.update(item.tags)

        return {
            "measurement": item.measurement,
            "timestamp": timestamp,
            "tags": tags,
            "fields": item.fields or {},
        }
