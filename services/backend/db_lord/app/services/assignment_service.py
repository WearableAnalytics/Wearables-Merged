from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, EntityNotFoundError
from app.db.postgres.repos.assignment_repo import AssignmentRepo
from app.db.postgres.repos.case_repo import CaseRepo
from app.db.postgres.repos.device_repo import DeviceRepo
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.schemas.assignment import ContextAssignmentResponse, DeviceAssignmentResponse, WearableAssignmentResponse
from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus


class AssignmentService:
    """Service for managing device/wearable/context assignments to cases."""

    def __init__(
        self,
        db: AsyncSession,
        device_repo: DeviceRepo,
        wearable_repo: WearableRepo,
        case_repo: CaseRepo,
        assignment_repo: AssignmentRepo,
    ):
        self.db = db
        self.device_repo = device_repo
        self.wearable_repo = wearable_repo
        self.case_repo = case_repo
        self.assignment_repo = assignment_repo

    async def _ensure_active_case(self, case_id: UUID) -> None:
        case = await self.case_repo.get(case_id)
        if not case:
            raise EntityNotFoundError("Case", case_id)
        if case.status not in {CaseStatus.PLANNED, CaseStatus.ONGOING}:
            raise BadRequestError("Case is not active")

    async def _claim_hardware(
        self,
        *,
        hardware_name: str,
        hardware_id: UUID,
        update_status: Callable[..., Awaitable[bool]],
        get_current: Callable[[UUID], Awaitable[Any | None]],
    ) -> None:
        claimed = await update_status(
            hardware_id,
            HardwareStatus.ASSIGNED.value,
            expected_status=HardwareStatus.AVAILABLE.value,
        )
        if claimed:
            return

        current = await get_current(hardware_id)
        if not current:
            raise EntityNotFoundError(hardware_name, hardware_id)

        raise BadRequestError(f"{hardware_name} is not available (Current status: {current.status})")

    async def _mark_hardware_available(
        self, *, hardware_id: UUID, update_status: Callable[..., Awaitable[bool]]
    ) -> None:
        await update_status(hardware_id, HardwareStatus.AVAILABLE.value)

    async def get_active_device_assignment(self, case_id: UUID, device_id: UUID) -> DeviceAssignmentResponse:
        assignment = await self.assignment_repo.get_active_device(case_id, device_id)
        if not assignment:
            raise EntityNotFoundError("ActiveDeviceAssignment", f"{case_id}/{device_id}")
        return DeviceAssignmentResponse.model_validate(assignment)

    async def get_last_device_assignment(self, case_id: UUID) -> DeviceAssignmentResponse:
        assignment = await self.assignment_repo.get_last_device_assignment(case_id)
        if not assignment:
            raise EntityNotFoundError("DeviceAssignment", f"Case {case_id}")
        return DeviceAssignmentResponse.model_validate(assignment)

    async def get_active_wearable_assignment(self, case_id: UUID, wearable_id: UUID) -> WearableAssignmentResponse:
        assignment = await self.assignment_repo.get_active_wearable(case_id, wearable_id)
        if not assignment:
            raise EntityNotFoundError("ActiveWearableAssignment", f"{case_id}/{wearable_id}")
        return WearableAssignmentResponse.model_validate(assignment)

    async def get_last_wearable_assignment(self, case_id: UUID) -> WearableAssignmentResponse:
        assignment = await self.assignment_repo.get_last_wearable_assignment(case_id)
        if not assignment:
            raise EntityNotFoundError("WearableAssignment", f"Case {case_id}")
        return WearableAssignmentResponse.model_validate(assignment)

    # Devices
    async def assign_device(
        self, case_id: UUID, device_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> DeviceAssignmentResponse:
        async with self.db.begin():
            await self._ensure_active_case(case_id)
            await self._claim_hardware(
                hardware_name="Device",
                hardware_id=device_id,
                update_status=self.device_repo.update_status,
                get_current=self.device_repo.get,
            )

            assignment = await self.assignment_repo.assign_device(case_id, device_id, start_time, end_time)
            if not assignment:
                raise EntityNotFoundError("DeviceAssignment", f"{case_id}/{device_id}")
            return DeviceAssignmentResponse.model_validate(assignment)

    async def unassign_device(
        self, case_id: UUID, device_id: UUID, end_time: datetime | None = None
    ) -> DeviceAssignmentResponse:
        async with self.db.begin():
            # Close assignment
            assignment = await self.assignment_repo.unassign_device(case_id, device_id, end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveDeviceAssignment", f"{case_id}/{device_id}")

            await self._mark_hardware_available(
                hardware_id=device_id,
                update_status=self.device_repo.update_status,
            )

            return DeviceAssignmentResponse.model_validate(assignment)

    async def unassign_last_device(self, case_id: UUID, end_time: datetime | None = None) -> DeviceAssignmentResponse:
        async with self.db.begin():
            assignment = await self.assignment_repo.unassign_last_device(case_id, end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveDeviceAssignment", f"Case {case_id}")

            await self._mark_hardware_available(
                hardware_id=assignment.device_id,
                update_status=self.device_repo.update_status,
            )

            return DeviceAssignmentResponse.model_validate(assignment)

    async def delete_device_assignment(
        self, case_id: UUID, device_id: UUID, assigned_from: datetime | None = None
    ) -> DeviceAssignmentResponse | None:
        async with self.db.begin():
            # Hard delete
            assignment = await self.assignment_repo.delete_device_assignment(case_id, device_id, assigned_from)

            if assignment:
                # Edge Case: If we deleted an ACTIVE assignment, we must free the device
                if assignment.assigned_to is None:
                    await self._mark_hardware_available(
                        hardware_id=device_id,
                        update_status=self.device_repo.update_status,
                    )

                return DeviceAssignmentResponse.model_validate(assignment)

            # If None-> Not Found (or Ambiguous)
            return None

    # Wearables
    async def assign_wearable(
        self, case_id: UUID, wearable_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> WearableAssignmentResponse:
        async with self.db.begin():
            await self._ensure_active_case(case_id)
            await self._claim_hardware(
                hardware_name="Wearable",
                hardware_id=wearable_id,
                update_status=self.wearable_repo.update_status,
                get_current=self.wearable_repo.get,
            )

            assignment = await self.assignment_repo.assign_wearable(case_id, wearable_id, start_time, end_time)
            if not assignment:
                raise EntityNotFoundError("WearableAssignment", f"{case_id}/{wearable_id}")
            return WearableAssignmentResponse.model_validate(assignment)

    async def unassign_wearable(
        self, case_id: UUID, wearable_id: UUID, end_time: datetime | None = None
    ) -> WearableAssignmentResponse:
        async with self.db.begin():
            assignment = await self.assignment_repo.unassign_wearable(case_id, wearable_id, end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveWearableAssignment", f"{case_id}/{wearable_id}")

            await self._mark_hardware_available(
                hardware_id=wearable_id,
                update_status=self.wearable_repo.update_status,
            )
            return WearableAssignmentResponse.model_validate(assignment)

    async def unassign_last_wearable(
        self, case_id: UUID, end_time: datetime | None = None
    ) -> WearableAssignmentResponse:
        async with self.db.begin():
            assignment = await self.assignment_repo.unassign_last_wearable(case_id, end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveWearableAssignment", f"Case {case_id}")

            await self._mark_hardware_available(
                hardware_id=assignment.wearable_id,
                update_status=self.wearable_repo.update_status,
            )
            return WearableAssignmentResponse.model_validate(assignment)

    async def delete_wearable_assignment(
        self, case_id: UUID, wearable_id: UUID, assigned_from: datetime | None = None
    ) -> WearableAssignmentResponse | None:
        async with self.db.begin():
            assignment = await self.assignment_repo.delete_wearable_assignment(case_id, wearable_id, assigned_from)

            if assignment:
                if assignment.assigned_to is None:
                    await self._mark_hardware_available(
                        hardware_id=wearable_id,
                        update_status=self.wearable_repo.update_status,
                    )
                return WearableAssignmentResponse.model_validate(assignment)
            return None

    # Contexts
    async def link_context(self, case_id: UUID, context_id: UUID) -> ContextAssignmentResponse:
        async with self.db.begin():
            result = await self.assignment_repo.link_context(case_id, context_id)
            if not result:
                return ContextAssignmentResponse(case_id=case_id, context_id=context_id)
            return ContextAssignmentResponse(case_id=result.case_id, context_id=result.context_id)

    async def unlink_context(self, case_id: UUID, context_id: UUID) -> ContextAssignmentResponse:
        async with self.db.begin():
            result = await self.assignment_repo.unlink_context(case_id, context_id)
            if not result:
                raise EntityNotFoundError("ContextAssignment", f"{case_id}/{context_id}")
            return ContextAssignmentResponse(case_id=result.case_id, context_id=result.context_id)
