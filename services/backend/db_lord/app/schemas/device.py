import uuid

from pydantic import Field

from .common import HardwareBase, HardwareStatus, TunedUpdateBase


# Crud shemas
class DeviceBase(HardwareBase):
    pass


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(TunedUpdateBase):
    serial_nr: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        title="Serial Number",
        description="The unique serial number of the hardware provided by the manufacturer.",
        examples=["SN1234567890", "SN12-3456-7890"],
    )
    model: str | None = Field(
        None,
        min_length=1,
        max_length=100,
        title="Model Name",
        description="The model of the hardware provided by the manufacturer.",
        examples=["Model X", "Iphone 32 Pro"],
    )
    manufacturer: str | None = Field(
        None,
        max_length=100,
        title="Manufacturer",
        description="The manufacturer of the hardware.",
        examples=["Manufacturer A", "Company B", "Apple"],
    )
    os_version: str | None = Field(
        None,
        max_length=50,
        title="OS Version",
        description="The currently installed operating system or firmware version.",
        examples=["iOS 16.4.4", "Android 12", "Firmware v1.2.3"],
    )
    status: HardwareStatus | None = Field(
        None,
        title="Lifecycle Status",
        description="The current physical availability of the device.",
    )


class Device(HardwareBase):
    id: uuid.UUID
