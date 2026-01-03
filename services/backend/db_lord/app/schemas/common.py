from pydantic import BaseModel, ConfigDict, Field


class TunedBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True,
        str_strip_whitespace=True,
        # validate_assignment=True, # Re-validates if values are changed after init can be expensive
    )


class HardwareBase(TunedBase):
    serial_nr: str = Field(..., min_length=1, max_length=100)
    model: str = Field(..., min_length=1, max_length=100)
    manufacturer: str | None = Field(None, max_length=100)
    os_version: str = Field(..., max_length=50)
