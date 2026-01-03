import uuid

from pydantic import Field

from .common import HardwareBase, TunedBase


class WearableBase(HardwareBase):
    pass


class WearableCreate(WearableBase):
    pass


class WearableUpdate(TunedBase):
    serial_nr: str | None = Field(None, min_length=1, max_length=100)
    model: str | None = Field(None, min_length=1, max_length=100)
    manufacturer: str | None = Field(None, max_length=100)
    os_version: str | None = Field(None, max_length=50)


class Wearable(HardwareBase):
    id: uuid.UUID
