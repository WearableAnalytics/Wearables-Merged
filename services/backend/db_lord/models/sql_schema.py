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
class Patient(PatientBase):
    id: str


class Device(DeviceBase):
    id: str


class Wearable(DeviceBase):
    id: str


class Context(ContextBase):
    id: str


class CaseDeviceLink(BaseModel):
    device_id: str
    assigned_from: datetime
    assigned_to: Optional[datetime]


class CaseWearableLink(BaseModel):
    wearable_id: str
    assigned_from: datetime
    assigned_to: Optional[datetime]


class CaseBase(BaseModel):
    patient_id: str
    # Optional lists to link directly while creating a case
    linked_devices: List[CaseDeviceLink] = []
    linked_wearables: List[CaseWearableLink] = []
    linked_context_ids: List[str] = []


class Case(CaseBase):
    id: str
    status: str
