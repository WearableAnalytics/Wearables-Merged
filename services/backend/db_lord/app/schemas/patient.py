import uuid
from datetime import date
from decimal import Decimal

from pydantic import Field

from .common import TunedBase, TunedUpdateBase


class PatientBase(TunedBase):
    charite_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    sex: str | None = Field(None, max_length=50)
    dob: date | None = None
    weight: Decimal | None = Field(None, max_digits=6, decimal_places=2)
    height: Decimal | None = Field(None, max_digits=4, decimal_places=2)


class PatientCreate(PatientBase):
    pass


class PatientUpdate(TunedUpdateBase):
    name: str | None = Field(None, min_length=1, max_length=255)
    sex: str | None = Field(None, max_length=50)
    dob: date | None = None
    weight: Decimal | None = Field(None, max_digits=6, decimal_places=2)
    height: Decimal | None = Field(None, max_digits=4, decimal_places=2)


class Patient(PatientBase):
    id: uuid.UUID
