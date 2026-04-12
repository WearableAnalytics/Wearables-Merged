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
    status: CaseStatus = Field(default=CaseStatus.PLANNED, description="Current lifecycle status of the case.")
    patient_id: UUID = Field(description="Patient identifier.")


class CaseCreate(CaseBase):
    pass


class CaseUpdate(TunedUpdateBase):
    status: CaseStatus | None = None
    patient_id: UUID | None = None


class CaseResponse(CaseBase):
    id: UUID


# Expanded response shape
class CaseDeviceAssignmentExpandedResponse(TunedBase):
    assigned_from: AwareDatetime = Field(description="Assignment start timestamp.")
    assigned_to: AwareDatetime | None = Field(default=None, description="Assignment end timestamp when closed.")
    device: DeviceResponse = Field(description="Assigned device details.")


class CaseWearableAssignmentExpandedResponse(TunedBase):
    assigned_from: AwareDatetime = Field(description="Assignment start timestamp.")
    assigned_to: AwareDatetime | None = Field(default=None, description="Assignment end timestamp when closed.")
    wearable: WearableResponse = Field(description="Assigned wearable details.")


class CaseExpanded(CaseResponse):
    devices: list[CaseDeviceAssignmentExpandedResponse] = Field(
        default_factory=list,
        description="Expanded device assignments for the case.",
    )
    wearables: list[CaseWearableAssignmentExpandedResponse] = Field(
        default_factory=list,
        description="Expanded wearable assignments for the case.",
    )
    contexts: list[ContextResponse] = Field(default_factory=list, description="Contexts linked to the case.")
    patient: PatientResponse | None = Field(default=None, description="Expanded patient details.")
