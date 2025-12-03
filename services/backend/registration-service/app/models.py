from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, ForeignKey

from app.db import Base


class PatientRequest(BaseModel):
    patient_id: str
    watch_id: str
    phone_id: str
    context_id: str

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
    __tablename__ = "master"

    id = Column(String, primary_key=True, index=True)
    patient_id = Column(String, index=True)
    phone_id = Column(String, index=True)
    watch_id = Column(String, index=True)
    context_id = Column(String, index=True)