import uuid

from .common import HardwareBase, TunedBase


class DeviceCreate(HardwareBase):
    pass


class DeviceUpdate(TunedBase):
    serial_nr: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    os_version: str | None = None


class Device(HardwareBase):
    id: uuid.UUID
