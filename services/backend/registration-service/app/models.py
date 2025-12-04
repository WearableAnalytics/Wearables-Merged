from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey

from app.db import Base


class PatientRequest(BaseModel):
    patient_id: str
    watch_id: str
    phone_id: str
    context_id: str
    patient_mail: str
    appointment_date: str

class PatientResponse(BaseModel):
    status: str
    message: str
    reg_id: str

class Patient(BaseModel):
    reg_id: str
    patient_id: str
    phone_id: str
    watch_id: str
    context_id: str


class PatientMaster(Base):
    __tablename__ = "event"

    id = Column(String, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    phone_id = Column(String, index=True)
    watch_id = Column(String, index=True)
    context_id = Column(String, index=True)

class RegistrationToken(Base):
    __tablename__ = "registration_token"

    id = Column(String, primary_key=True, index=True)
    event_id = Column(String, index=True)
    status = Column(String, index=True) # Pending/Done