from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class TelemetryCreate(BaseModel):
    patient_id: UUID
    case_id: UUID
    device_id: UUID
    measurement: str
    value: float
    timestamp: datetime | None = None
