from sqlalchemy import Column, ForeignKey, String, Table, Uuid, func

from .metadata import metadata

cases = Table(
    "cases",
    metadata,
    Column("id", Uuid, primary_key=True, server_default=func.uuidv7()),
    Column("status", String, nullable=False),
    # CASCADE so that when a patient is deleted, their cases are also deleted
    # Indexed for faster lookups when querying cases by patient_id
    Column("patient_id", Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True),
)
