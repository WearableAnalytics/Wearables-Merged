from uuid import UUID

from pydantic import Field

from app.model_constants import (
    HARDWARE_MANUFACTURER_MAX_LEN,
    HARDWARE_MODEL_MAX_LEN,
    HARDWARE_OS_VERSION_MAX_LEN,
    HARDWARE_SERIAL_MAX_LEN,
)

from .common import HardwareBase, HardwareStatus, TunedUpdateBase


class WearableBase(HardwareBase):
    pass


class WearableCreate(WearableBase):
    pass


class WearableUpdate(TunedUpdateBase):
    serial_nr: str | None = Field(
        None,
        min_length=1,
        max_length=HARDWARE_SERIAL_MAX_LEN,
        title="Serial Number",
        description="The unique serial number of the hardware provided by the manufacturer.",
        examples=["SN1234567890", "SN12-3456-7890"],
    )
    model: str | None = Field(
        None,
        min_length=1,
        max_length=HARDWARE_MODEL_MAX_LEN,
        title="Model Name",
        description="The model of the hardware provided by the manufacturer.",
        examples=["Model X", "Apple Watch Series 8"],
    )
    manufacturer: str | None = Field(
        None,
        max_length=HARDWARE_MANUFACTURER_MAX_LEN,
        title="Manufacturer",
        description="The manufacturer of the hardware.",
        examples=["Manufacturer A", "Company B", "Apple"],
    )
    os_version: str | None = Field(
        None,
        max_length=HARDWARE_OS_VERSION_MAX_LEN,
        title="OS Version",
        description="The currently installed operating system or firmware version.",
        examples=["Firmware v1.2.3", "watchOS 9.5", "Android 12"],
    )
    status: HardwareStatus | None = Field(
        None,
        title="Lifecycle Status",
        description="The current physical availability of the wearable.",
    )


class WearableResponse(HardwareBase):
    id: UUID
