from fastapi import APIRouter, status

from app.schemas.telemetry import TelemetryCreate
from app.services.telemetry_service import TelemetryService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_telemetry(item_in: TelemetryCreate):
    service = TelemetryService()
    await service.record_telemetry(
        measurement=item_in.measurement,
        value=item_in.value,
        patient_id=item_in.patient_id,
        case_id=item_in.case_id,
        device_id=item_in.device_id,
        timestamp=item_in.timestamp,
    )
    return None
