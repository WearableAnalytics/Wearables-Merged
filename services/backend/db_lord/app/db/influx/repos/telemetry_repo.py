from datetime import datetime
from uuid import UUID

from influxdb_client import Point

from app.core.config import settings
from app.db.influx.client import client


class TelemetryRepo:
    async def write_point(
        self,
        measurement: str,
        value: float,
        patient_id: UUID,
        case_id: UUID,
        device_id: UUID,
        timestamp: datetime | None = None,
    ) -> None:
        point = (
            Point(measurement)
            .tag("patient_id", str(patient_id))
            .tag("case_id", str(case_id))
            .tag("device_id", str(device_id))
            .field("value", value)
        )
        if timestamp:
            point.time(timestamp)

        write_api = client.write_api()
        success = await write_api.write(bucket=settings.INFLUX_BUCKET, record=point)
        return success

    async def write_batch(self, points: list[Point]) -> None:
        write_api = client.write_api()
        await write_api.write(bucket=settings.INFLUX_BUCKET, record=points)
