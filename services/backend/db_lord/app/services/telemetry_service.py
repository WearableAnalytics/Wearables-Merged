from datetime import datetime
from uuid import UUID

from app.db.influx.repos.telemetry_repo import TelemetryRepo


class TelemetryService:
    def __init__(self):
        self.repo = TelemetryRepo()

    async def record_telemetry(
        self,
        measurement: str,
        value: float,
        patient_id: UUID,
        case_id: UUID,
        device_id: UUID,
        timestamp: datetime | None = None,
    ) -> None:
        await self.repo.write_point(
            measurement=measurement,
            value=value,
            patient_id=patient_id,
            case_id=case_id,
            device_id=device_id,
            timestamp=timestamp,
        )
