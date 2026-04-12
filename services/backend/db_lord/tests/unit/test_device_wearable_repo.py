"""
Repository tests for device and wearable status updates with expected_status guards
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import Device, Wearable
from app.db.postgres.repos.device_repo import DeviceRepo
from app.db.postgres.repos.wearable_repo import WearableRepo

pytestmark = pytest.mark.anyio


class TestDeviceRepoUpdateStatus:
    async def test_update_status_with_expected_match(self, db_session: AsyncSession, device_orm_factory):
        device = await device_orm_factory(status="AVAILABLE")
        repo = DeviceRepo(db_session)

        ok = await repo.update_status(device.id, "ASSIGNED", expected_status="AVAILABLE")
        assert ok is True

        result = await db_session.execute(select(Device.status).where(Device.id == device.id))
        assert result.scalar_one() == "ASSIGNED"

    async def test_update_status_with_expected_mismatch(self, db_session: AsyncSession, device_orm_factory):
        device = await device_orm_factory(status="IN_REPAIR")
        repo = DeviceRepo(db_session)

        ok = await repo.update_status(device.id, "ASSIGNED", expected_status="AVAILABLE")
        assert ok is False

        result = await db_session.execute(select(Device.status).where(Device.id == device.id))
        assert result.scalar_one() == "IN_REPAIR"


class TestWearableRepoUpdateStatus:
    async def test_update_status_with_expected_match(self, db_session: AsyncSession, wearable_orm_factory):
        wearable = await wearable_orm_factory(status="AVAILABLE")
        repo = WearableRepo(db_session)

        ok = await repo.update_status(wearable.id, "ASSIGNED", expected_status="AVAILABLE")
        assert ok is True

        result = await db_session.execute(select(Wearable.status).where(Wearable.id == wearable.id))
        assert result.scalar_one() == "ASSIGNED"

    async def test_update_status_with_expected_mismatch(self, db_session: AsyncSession, wearable_orm_factory):
        wearable = await wearable_orm_factory(status="IN_REPAIR")
        repo = WearableRepo(db_session)

        ok = await repo.update_status(wearable.id, "ASSIGNED", expected_status="AVAILABLE")
        assert ok is False

        result = await db_session.execute(select(Wearable.status).where(Wearable.id == wearable.id))
        assert result.scalar_one() == "IN_REPAIR"
