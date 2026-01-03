import uuid

from .common import HardwareBase, TunedBase


class WearableCreate(HardwareBase):
    pass


class WearableUpdate(TunedBase):
    serial_nr: str | None = None
    model: str | None = None
    manufacturer: str | None = None
    os_version: str | None = None


class Wearable(HardwareBase):
    id: uuid.UUID
