import uuid
from enum import Enum

from pydantic import Field

from .common import TunedBase


class CaseStatus(str, Enum):
    PLANNED = "planned"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    OTHER = "other"


class CaseBase(TunedBase):
    status: CaseStatus = Field(CaseStatus.PLANNED)
    patient_id: uuid.UUID


class CaseCreate(CaseBase):
    pass


class CaseUpdate(TunedBase):
    status: CaseStatus | None = None
    patient_id: uuid.UUID | None = None


class Case(CaseBase):
    id: uuid.UUID
