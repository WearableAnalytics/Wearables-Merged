from uuid import UUID

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.orm import Device
from app.db.postgres.repos.device_repo import DeviceRepo
from app.schemas.assignment import DeviceAssignmentResponse
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.services.base import BaseService


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate, DeviceRepo]):
    def __init__(self, repo: DeviceRepo):
        super().__init__(repo)

    async def get_assignments(self, id: UUID) -> list[DeviceAssignmentResponse]:
        device = await self.repo.get_with_assignments(id)
        if not device:
            raise EntityNotFoundError("Device", id)
        return [DeviceAssignmentResponse.model_validate(item) for item in device.case_assignments]
