from enum import Enum
from uuid import UUID

from pydantic import Field

from .common import TunedBase, TunedUpdateBase
from .context import ContextResponse
from .device import DeviceResponse
from .patient import PatientResponse
from .wearable import WearableResponse


class CaseStatus(str, Enum):
    PLANNED = "PLANNED"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    OTHER = "OTHER"


class CaseBase(TunedBase):
    status: CaseStatus = Field(default=CaseStatus.PLANNED)
    patient_id: UUID


class CaseCreate(CaseBase):
    pass


class CaseUpdate(TunedUpdateBase):
    status: CaseStatus | None = None
    patient_id: UUID | None = None


class CaseResponse(CaseBase):
    id: UUID


class CaseExpanded(CaseResponse):
    devices: list[DeviceResponse] = Field(default_factory=list)
    wearables: list[WearableResponse] = Field(default_factory=list)
    contexts: list[ContextResponse] = Field(default_factory=list)
    patient: PatientResponse | None = None
