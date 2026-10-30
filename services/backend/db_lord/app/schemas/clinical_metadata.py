"""Minimal metadata under current clinical assignment; no hospital-match assertion."""

from datetime import date
from uuid import UUID

from pydantic import Field

from app.schemas.case import CaseStatus
from app.schemas.common import TunedBase


class ClinicalPatientMetadata(TunedBase):
    id: UUID
    name: str = Field(max_length=256)
    dob: date | None


class ClinicalCaseMetadata(TunedBase):
    id: UUID
    patient_id: UUID
    status: CaseStatus
    patient: ClinicalPatientMetadata


class ClinicalMetadataPage(TunedBase):
    items: list[ClinicalCaseMetadata]
    next_cursor: UUID | None
