from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.repos.assignment_repo import AssignmentRepo
from app.db.postgres.repos.case_repo import CaseRepo
from app.db.postgres.repos.device_repo import DeviceRepo
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus


class AssignmentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.device_repo = DeviceRepo(db)
        self.case_repo = CaseRepo(db)
        self.wearable_repo = WearableRepo(db)
        self.assignment_repo = AssignmentRepo(db)

    async def assign_device(self, case_id: UUID, device_id: UUID) -> None:
        # 1. Check Device Availability
        device = await self.device_repo.get(device_id)
        if not device:
            raise ValueError("Device not found")
        current_status = device.get("status")
        if current_status != HardwareStatus.AVAILABLE.value:
            raise ValueError(f"Device is {current_status}")

        # 2. Check Case Active
        case = await self.case_repo.get(case_id)
        if not case:
            raise ValueError("Case not found")
        case_status = case.get("status")
        if case_status not in {CaseStatus.PLANNED.value, CaseStatus.ONGOING.value}:
            raise ValueError("Case is not active")

        # 3. Transactional updates (commit handled by get_db dependency)
        ok = await self.device_repo.update_status(device_id, HardwareStatus.ASSIGNED)
        if not ok:
            raise ValueError("Device not available for assignment")

        await self.assignment_repo.create_assignment(case_id, device_id)

    async def unassign_device(self, case_id: UUID, device_id: UUID) -> None:
        assignment = await self.assignment_repo.find_active_assignment(case_id, device_id)
        if not assignment:
            raise ValueError("No active assignment found")

        await self.assignment_repo.close_assignment(case_id, device_id)
        await self.device_repo.update_status(device_id, HardwareStatus.AVAILABLE)

    # Wearables
    async def assign_wearable(self, case_id: UUID, wearable_id: UUID) -> None:
        # 1. Check Wearable Availability
        wearable = await self.wearable_repo.get(wearable_id)
        if not wearable:
            raise ValueError("Wearable not found")
        current_status = wearable.get("status")
        if current_status != HardwareStatus.AVAILABLE.value:
            raise ValueError(f"Wearable is {current_status}")

        # 2. Check Case Active
        case = await self.case_repo.get(case_id)
        if not case:
            raise ValueError("Case not found")
        case_status = case.get("status")
        if case_status not in {CaseStatus.PLANNED.value, CaseStatus.ONGOING.value}:
            raise ValueError("Case is not active")

        ok = await self.wearable_repo.update_status(wearable_id, HardwareStatus.ASSIGNED)
        if not ok:
            raise ValueError("Wearable not available for assignment")
        await self.assignment_repo.create_wearable_assignment(case_id, wearable_id)

    async def unassign_wearable(self, case_id: UUID, wearable_id: UUID) -> None:
        assignment = await self.assignment_repo.find_active_wearable_assignment(case_id, wearable_id)
        if not assignment:
            raise ValueError("No active assignment found")

        await self.assignment_repo.close_wearable_assignment(case_id, wearable_id)
        await self.wearable_repo.update_status(wearable_id, HardwareStatus.AVAILABLE)

    # Contexts
    async def link_context(self, case_id: UUID, context_id: UUID) -> None:
        await self.assignment_repo.link_context(case_id, context_id)

    async def unlink_context(self, case_id: UUID, context_id: UUID) -> None:
        await self.assignment_repo.unlink_context(case_id, context_id)
