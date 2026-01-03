from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import UUID7, BaseModel, ConfigDict, Field


class CaseStatus(str, Enum):
    PLANNED = "planned"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class TunedModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# Linking helper models
class CaseLinkContextRequest(TunedModel):
    context_id: UUID7


class CaseLinkDeviceRequest(TunedModel):
    item_id: UUID7
    assigned_from: Optional[datetime] = None


class CaseLinkWearableRequest(TunedModel):
    item_id: UUID7
    assigned_from: Optional[datetime] = None


# Links (sparse views)
class CaseDeviceLink(TunedModel):
    device_id: UUID7
    assigned_from: datetime
    assigned_to: Optional[datetime] = None


class CaseWearableLink(TunedModel):
    wearable_id: UUID7
    assigned_from: datetime
    assigned_to: Optional[datetime] = None


# Patients
class PatientBase(TunedModel):
    charite_id: UUID7
    name: str
    sex: Optional[str] = None
    dob: Optional[date] = None
    weight: Optional[float] = None
    height: Optional[float] = None


# In case we want to add extra fields later without breaking existing code
class PatientCreate(PatientBase):
    pass


class PatientUpdate(TunedModel):
    charite_id: Optional[UUID7] = None
    name: Optional[str] = None
    sex: Optional[str] = None
    dob: Optional[date] = None
    weight: Optional[float] = None
    height: Optional[float] = None


# This inherits "name", etc. from PatientBase and adds id
class Patient(PatientBase):
    id: UUID7


# creates a smaller summary version of Patient for thing like dropdowns etc.
class PatientSummary(TunedModel):
    id: UUID7
    name: str
    charite_id: UUID7


# Devices
class DeviceBase(TunedModel):
    serial_nr: str
    model: str
    manufacturer: Optional[str] = None
    os_version: str


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(TunedModel):
    serial_nr: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None


class Device(DeviceBase):
    id: UUID7


# Wearables
class WearableBase(TunedModel):
    serial_nr: str
    model: str
    manufacturer: Optional[str] = None
    os_version: str


class WearableCreate(WearableBase):
    pass


class WearableUpdate(TunedModel):
    serial_nr: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    os_version: Optional[str] = None


class Wearable(WearableBase):
    id: UUID7


# Contexts
class ContextBase(TunedModel):
    group_name: str
    coordinator: Optional[str] = None


class ContextCreate(ContextBase):
    pass


class ContextUpdate(TunedModel):
    group_name: Optional[str] = None
    coordinator: Optional[str] = None


class Context(ContextBase):
    id: UUID7


# Detailed link views
class CaseDeviceDetail(Device):
    assigned_from: datetime
    assigned_to: Optional[datetime] = None


class CaseWearableDetail(Wearable):
    assigned_from: datetime
    assigned_to: Optional[datetime] = None


# Cases
class CaseBase(TunedModel):
    status: CaseStatus


class CaseCreate(CaseBase):
    patient_id: UUID7

    linked_device_ids: List[UUID7] = Field(default_factory=list)
    linked_wearable_ids: List[UUID7] = Field(default_factory=list)
    linked_context_ids: List[UUID7] = Field(default_factory=list)


class CaseUpdate(TunedModel):
    patient_id: Optional[UUID7] = None
    status: Optional[CaseStatus] = None


class Case(CaseBase):
    id: UUID7

    patient_id: UUID7
    patient_details: Optional[Patient] = None

    linked_device_ids: List[UUID7] = []
    linked_device_details: Optional[List[CaseDeviceDetail]] = None

    linked_wearable_ids: List[UUID7] = []
    linked_wearable_details: Optional[List[CaseWearableDetail]] = None

    linked_context_ids: List[UUID7] = []
    linked_context_details: Optional[List[Context]] = None
