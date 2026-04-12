import asyncio
from uuid import uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.postgres.orm import Case, Device, Patient, Wearable
from app.db.postgres.repos.assignment_repo import AssignmentRepo
from app.db.postgres.repos.case_repo import CaseRepo
from app.db.postgres.repos.device_repo import DeviceRepo
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus
from app.services.assignment_service import AssignmentService

pytestmark = pytest.mark.anyio


def _build_assignment_service(session: AsyncSession) -> AssignmentService:
    return AssignmentService(
        db=session,
        device_repo=DeviceRepo(session),
        wearable_repo=WearableRepo(session),
        case_repo=CaseRepo(session),
        assignment_repo=AssignmentRepo(session),
    )


class TestAssignmentConcurrency:
    async def test_concurrent_device_assignment(self, async_engine):
        session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

        async with session_maker.begin() as setup_session:
            patient = Patient(id=uuid7(), charite_id=uuid7(), name="Concurrency Patient", sex="M")
            setup_session.add(patient)
            await setup_session.flush()

            case = Case(id=uuid7(), patient_id=patient.id, status=CaseStatus.PLANNED)
            setup_session.add(case)

            device = Device(
                id=uuid7(),
                serial_nr=f"SN-{uuid7().hex[-12:]}",
                model="Concurrency Device",
                os_version="1.0.0",
                status=HardwareStatus.AVAILABLE,
            )
            setup_session.add(device)

        async def attempt_assign():
            async with session_maker() as session:
                service = _build_assignment_service(session)
                await service.assign_device(case.id, device.id)

        results = await asyncio.gather(
            attempt_assign(),
            attempt_assign(),
            return_exceptions=True,
        )

        # One should succeed, one should fail with ValueError
        failures = [r for r in results if isinstance(r, Exception)]
        assert len(failures) == 1

    async def test_concurrent_wearable_assignment(self, async_engine):
        session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

        async with session_maker.begin() as setup_session:
            patient = Patient(id=uuid7(), charite_id=uuid7(), name="Concurrency Patient", sex="M")
            setup_session.add(patient)
            await setup_session.flush()

            case = Case(id=uuid7(), patient_id=patient.id, status=CaseStatus.PLANNED)
            setup_session.add(case)

            wearable = Wearable(
                id=uuid7(),
                serial_nr=f"WR-{uuid7().hex[-12:]}",
                model="Concurrency Wearable",
                os_version="1.0.0",
                status=HardwareStatus.AVAILABLE,
            )
            setup_session.add(wearable)

        async def attempt_assign():
            async with session_maker() as session:
                service = _build_assignment_service(session)
                await service.assign_wearable(case.id, wearable.id)

        results = await asyncio.gather(
            attempt_assign(),
            attempt_assign(),
            return_exceptions=True,
        )

        failures = [r for r in results if isinstance(r, Exception)]
        assert len(failures) == 1
