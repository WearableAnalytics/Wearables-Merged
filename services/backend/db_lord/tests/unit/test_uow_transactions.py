from uuid import uuid7

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.postgres.orm import Patient
from app.db.postgres.repos.patient_repo import PatientRepo
from app.schemas.patient import PatientCreate
from app.services.patient_service import PatientService

pytestmark = pytest.mark.anyio


async def test_service_uow_rolls_back_failed_write_and_keeps_session_usable(db_session) -> None:
    service = PatientService(PatientRepo(db_session))
    duplicate_charite_id = uuid7()

    await service.create(
        PatientCreate(
            charite_id=duplicate_charite_id,
            name="Initial Patient",
            sex="M",
            weight=None,
            height=None,
        )
    )

    with pytest.raises(IntegrityError):
        await service.create(
            PatientCreate(
                charite_id=duplicate_charite_id,
                name="Duplicate Patient",
                sex="F",
                weight=None,
                height=None,
            )
        )

    result = await db_session.execute(select(Patient).where(Patient.charite_id == duplicate_charite_id))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].name == "Initial Patient"
