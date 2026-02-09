from app.db.postgres.orm import Device
from app.db.postgres.repos.device_repo import DeviceRepo
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.services.base import BaseService


class DeviceService(BaseService[Device, DeviceCreate, DeviceUpdate, DeviceRepo]):
    def __init__(self, repo: DeviceRepo):
        super().__init__(repo)
