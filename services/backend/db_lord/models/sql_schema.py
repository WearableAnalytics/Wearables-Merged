from datetime import date, datetime
from typing import List, Optional

from pydantic import UUID4, BaseModel


# BASE MODELS
class PatientBase(BaseModel):
    charite_id: UUID4
    name: str
    sex: Optional[str]
    dob: Optional[date]
    weight: Optional[float]
    height: Optional[float]


class DeviceBase(BaseModel):
    serial_nr: str
    model: str
    manufacturer: Optional[str]
    os_version: str


class ContextBase(BaseModel):
    group_name: str
    coordinator: Optional[str]


# CREATE MODELS
class PatientCreate(PatientBase):
    id: UUID4


class DeviceCreate(DeviceBase):
    id: UUID4


class WearableCreate(DeviceBase):
    id: UUID4


class ContextCreate(ContextBase):
    id: UUID4


class CaseDeviceLink(BaseModel):
    device_id: UUID4
    assigned_from: datetime
    assigned_to: Optional[datetime]


class CaseWearableLink(BaseModel):
    wearable_id: UUID4
    assigned_from: datetime
    assigned_to: Optional[datetime]


class CaseCreate(BaseModel):
    id: UUID4
    status: str
    patient_id: UUID4
    # Optional lists to link directly while creating a case
    linked_devices: List[CaseDeviceLink] = []
    linked_wearables: List[CaseWearableLink] = []
    linked_context_ids: List[UUID4] = []
