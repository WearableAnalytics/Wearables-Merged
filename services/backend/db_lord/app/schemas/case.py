import uuid
from enum import Enum

from pydantic import Field

from .common import TunedBase, TunedUpdateBase
from .context import Context
from .device import Device
from .patient import Patient
from .wearable import Wearable


class CaseStatus(str, Enum):
    PLANNED = "PLANNED"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    OTHER = "OTHER"


class CaseBase(TunedBase):
    status: CaseStatus = Field(default=CaseStatus.PLANNED)
    patient_id: uuid.UUID


class CaseCreate(CaseBase):
    pass


class CaseUpdate(TunedUpdateBase):
    status: CaseStatus | None = None
    patient_id: uuid.UUID | None = None


class Case(CaseBase):
    id: uuid.UUID


class CaseExpanded(Case):
    devices: list[Device] = Field(default_factory=list)
    wearables: list[Wearable] = Field(default_factory=list)
    contexts: list[Context] = Field(default_factory=list)
    patient: Patient | None = None
