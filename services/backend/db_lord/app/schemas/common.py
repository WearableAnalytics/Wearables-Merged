from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HardwareStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    IN_REPAIR = "IN_REPAIR"
    DECOMMISSIONED = "DECOMMISSIONED"
    LOST = "LOST"
    OTHER = "OTHER"


class TunedBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,  # Is that even needed since we arent using ORM mode? prob not
        use_enum_values=True,
        str_strip_whitespace=True,
        # validate_assignment=True, # Re-validates if values are changed after init can be expensive
    )


class TunedUpdateBase(TunedBase):
    def model_dump(self, **kwargs):
        kwargs.setdefault("exclude_unset", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        kwargs.setdefault("exclude_unset", True)
        return super().model_dump_json(**kwargs)


class HardwareBase(TunedBase):
    serial_nr: str = Field(
        ...,
        min_length=1,
        max_length=100,
        title="Serial Number",
        description="The unique serial number of the hardware provided by the manufacturer.",
        examples=["SN1234567890", "SN12-3456-7890"],
    )
    model: str = Field(
        ...,
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
    os_version: str = Field(
        ...,
        max_length=50,
        title="OS Version",
        description="The currently installed operating system or firmware version.",
        examples=["Firmware v1.2.3", "iOS 16.4.4", "Android 12"],
    )
    status: HardwareStatus = Field(
        default=HardwareStatus.AVAILABLE,
        title="Lifecycle Status",
        description="The current physical availability of the device.",
    )
