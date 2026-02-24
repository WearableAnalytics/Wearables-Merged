from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.model_constants import (
    PATIENT_HEIGHT_PRECISION,
    PATIENT_HEIGHT_SCALE,
    PATIENT_NAME_MAX_LEN,
    PATIENT_SEX_MAX_LEN,
    PATIENT_WEIGHT_PRECISION,
    PATIENT_WEIGHT_SCALE,
)

from .common import TunedBase, TunedUpdateBase


class PatientBase(TunedBase):
    charite_id: UUID
    name: str = Field(..., min_length=1, max_length=PATIENT_NAME_MAX_LEN)
    sex: str | None = Field(None, max_length=PATIENT_SEX_MAX_LEN)
    dob: date | None = None
    weight: Decimal | None = Field(
        None,
        gt=0,
        max_digits=PATIENT_WEIGHT_PRECISION,
        decimal_places=PATIENT_WEIGHT_SCALE,
    )
    height: Decimal | None = Field(
        None,
        gt=0,
        max_digits=PATIENT_HEIGHT_PRECISION,
        decimal_places=PATIENT_HEIGHT_SCALE,
    )


class PatientCreate(PatientBase):
    pass


class PatientUpdate(TunedUpdateBase):
    name: str | None = Field(None, min_length=1, max_length=PATIENT_NAME_MAX_LEN)
    sex: str | None = Field(None, max_length=PATIENT_SEX_MAX_LEN)
    dob: date | None = None
    weight: Decimal | None = Field(
        None,
        gt=0,
        max_digits=PATIENT_WEIGHT_PRECISION,
        decimal_places=PATIENT_WEIGHT_SCALE,
    )
    height: Decimal | None = Field(
        None,
        gt=0,
        max_digits=PATIENT_HEIGHT_PRECISION,
        decimal_places=PATIENT_HEIGHT_SCALE,
    )


class PatientResponse(PatientBase):
    id: UUID
