from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class HardwareStatus(str, Enum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    IN_REPAIR = "in_repair"
    DECOMMISSIONED = "decommissioned"
    LOST = "lost"
    OTHER = "other"


class TunedBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        str_strip_whitespace=True,
        # validate_assignment=True, # Re-validates if values are changed after init can be expensive
    )


class HardwareBase(TunedBase):
    serial_nr: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The unique serial number of the hardware provided by the manufacturer.",
        examples=["SN1234567890", "SN12-3456-7890"],
    )
    model: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="The model of the hardware provided by the manufacturer.",
        examples=["Model X", "Iphone Y"],
    )
    manufacturer: str | None = Field(None, max_length=100)
    os_version: str = Field(..., max_length=50)
    status: HardwareStatus = HardwareStatus.AVAILABLE
