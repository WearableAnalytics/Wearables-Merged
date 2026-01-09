from sqlalchemy import Column, Enum, ForeignKey, Table, Uuid, func

from app.schemas.case import CaseStatus

from .metadata import metadata

cases = Table(
    "cases",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column(
        "status",
        Enum(CaseStatus, name="case_status", native_enum=True),
        nullable=False,
        server_default=CaseStatus.PLANNED.name,
    ),
    # CASCADE so that when a patient is deleted, their cases are also deleted
    # Indexed for faster lookups when querying cases by patient_id
    Column("patient_id", Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
)
