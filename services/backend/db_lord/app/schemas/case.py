from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field

from .common import TunedBase, TunedUpdateBase
from .context import ContextResponse
from .device import DeviceResponse
from .patient import PatientResponse
from .wearable import WearableResponse


class CaseStatus(StrEnum):
    PLANNED = "PLANNED"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"
    OTHER = "OTHER"


class CaseExpandableFields(StrEnum):
    DEVICES = "devices"
    WEARABLES = "wearables"
    CONTEXTS = "contexts"
    PATIENT = "patient"


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


# Expanded response shape
class CaseDeviceAssignmentExpandedResponse(TunedBase):
    assigned_from: AwareDatetime
    assigned_to: AwareDatetime | None
    device: DeviceResponse


class CaseWearableAssignmentExpandedResponse(TunedBase):
    assigned_from: AwareDatetime
    assigned_to: AwareDatetime | None
    wearable: WearableResponse


class CaseExpanded(CaseResponse):
    devices: list[CaseDeviceAssignmentExpandedResponse] = Field(default_factory=list)
    wearables: list[CaseWearableAssignmentExpandedResponse] = Field(default_factory=list)
    contexts: list[ContextResponse] = Field(default_factory=list)
    patient: PatientResponse | None = None
