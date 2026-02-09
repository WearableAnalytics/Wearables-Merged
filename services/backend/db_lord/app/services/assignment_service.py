from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, EntityNotFoundError
from app.db.postgres.orm import CaseDevice, CaseWearable
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

    # Read helpers (used by GraphQL dataloaders)
    async def list_device_assignments_by_case_ids(self, case_ids: list[UUID]) -> list[CaseDevice]:
        return await self.assignment_repo.list_device_assignments_by_case_ids(case_ids)

    async def list_device_assignments_by_device_ids(self, device_ids: list[UUID]) -> list[CaseDevice]:
        return await self.assignment_repo.list_device_assignments_by_device_ids(device_ids)

    async def list_active_device_assignments_by_case_ids(
        self, case_ids: list[UUID], now_ts: datetime | None = None
    ) -> list[CaseDevice]:
        return await self.assignment_repo.list_active_device_assignments_by_case_ids(case_ids, now_ts=now_ts)

    async def list_wearable_assignments_by_case_ids(self, case_ids: list[UUID]) -> list[CaseWearable]:
        return await self.assignment_repo.list_wearable_assignments_by_case_ids(case_ids)

    async def list_wearable_assignments_by_wearable_ids(self, wearable_ids: list[UUID]) -> list[CaseWearable]:
        return await self.assignment_repo.list_wearable_assignments_by_wearable_ids(wearable_ids)

    async def list_active_wearable_assignments_by_case_ids(
        self, case_ids: list[UUID], now_ts: datetime | None = None
    ) -> list[CaseWearable]:
        return await self.assignment_repo.list_active_wearable_assignments_by_case_ids(case_ids, now_ts=now_ts)

    # Devices
    async def assign_device(
        self, case_id: UUID, device_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> DeviceAssignmentResponse:
        try:
            effective_start_time = start_time or datetime.now(UTC)
            # Validate Case State
            case = await self.case_repo.get(case_id)
            if not case:
                raise EntityNotFoundError("Case", case_id)
            if case.status not in {CaseStatus.PLANNED, CaseStatus.ONGOING}:
                raise BadRequestError("Case is not active")

            # Optimistic
            device = await self.device_repo.update_status(
                device_id, HardwareStatus.ASSIGNED.value, expected_status=HardwareStatus.AVAILABLE.value
            )

            if not device:
                # Slow Path:-> why did it fail?
                current_device = await self.device_repo.get(device_id)
                if not current_device:
                    raise EntityNotFoundError("Device", device_id)

                # If it exists but wasnt updated it wasnt AVAILABLE
                raise BadRequestError(f"Device is not available (Current status: {current_device.status})")

            assignment = await self.assignment_repo.assign_device(case_id, device_id, effective_start_time, end_time)
            await self.db.commit()
            return assignment

        except Exception:
            await self.db.rollback()
            raise

    async def unassign_device(
        self, case_id: UUID, device_id: UUID, end_time: datetime | None = None
    ) -> DeviceAssignmentResponse:
        try:
            effective_end_time = end_time or datetime.now(UTC)
            # Close assignment
            assignment = await self.assignment_repo.unassign_device(case_id, device_id, effective_end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveDeviceAssignment", f"{case_id}/{device_id}")

            # Free device
            await self.device_repo.update_status(device_id, HardwareStatus.AVAILABLE.value)

            await self.db.commit()
            return assignment
        except Exception:
            await self.db.rollback()
            raise

    async def unassign_last_device(self, case_id: UUID, end_time: datetime | None = None) -> DeviceAssignmentResponse:
        try:
            effective_end_time = end_time or datetime.now(UTC)

            assignment = await self.assignment_repo.unassign_last_device(case_id, effective_end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveDeviceAssignment", f"Case {case_id}")

            await self.device_repo.update_status(assignment.device_id, HardwareStatus.AVAILABLE.value)

            await self.db.commit()
            return assignment
        except Exception:
            await self.db.rollback()
            raise

    async def delete_device_assignment(
        self, case_id: UUID, device_id: UUID, assigned_from: datetime | None = None
    ) -> DeviceAssignmentResponse | None:
        try:
            # Hard delete
            assignment = await self.assignment_repo.delete_device_assignment(case_id, device_id, assigned_from)

            if assignment:
                # Edge Case: If we deleted an ACTIVE assignment, we must free the device
                if assignment.assigned_to is None:
                    await self.device_repo.update_status(device_id, HardwareStatus.AVAILABLE.value)

                await self.db.commit()
                return assignment

            # If None-> Not Found (or Ambiguous)
            return None
        except Exception:
            await self.db.rollback()
            raise

    # Wearables
    async def assign_wearable(
        self, case_id: UUID, wearable_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> WearableAssignmentResponse:
        try:
            effective_start_time = start_time or datetime.now(UTC)
            case = await self.case_repo.get(case_id)
            if not case:
                raise EntityNotFoundError("Case", case_id)
            if case.status not in {CaseStatus.PLANNED, CaseStatus.ONGOING}:
                raise BadRequestError("Case is not active")

            wearable = await self.wearable_repo.update_status(
                wearable_id,
                HardwareStatus.ASSIGNED.value,
                expected_status=HardwareStatus.AVAILABLE.value,
            )

            if not wearable:
                current_wearable = await self.wearable_repo.get(wearable_id)
                if not current_wearable:
                    raise EntityNotFoundError("Wearable", wearable_id)
                raise BadRequestError(f"Wearable is not available (Current status: {current_wearable.status})")

            assignment = await self.assignment_repo.assign_wearable(
                case_id, wearable_id, effective_start_time, end_time
            )
            await self.db.commit()
            return assignment
        except Exception:
            await self.db.rollback()
            raise

    async def unassign_wearable(
        self, case_id: UUID, wearable_id: UUID, end_time: datetime | None = None
    ) -> WearableAssignmentResponse:
        try:
            effective_end_time = end_time or datetime.now(UTC)
            assignment = await self.assignment_repo.unassign_wearable(case_id, wearable_id, effective_end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveWearableAssignment", f"{case_id}/{wearable_id}")

            await self.wearable_repo.update_status(wearable_id, HardwareStatus.AVAILABLE.value)
            await self.db.commit()
            return assignment
        except Exception:
            await self.db.rollback()
            raise

    async def unassign_last_wearable(
        self, case_id: UUID, end_time: datetime | None = None
    ) -> WearableAssignmentResponse:
        try:
            effective_end_time = end_time or datetime.now(UTC)
            assignment = await self.assignment_repo.unassign_last_wearable(case_id, effective_end_time)

            if not assignment:
                raise EntityNotFoundError("ActiveWearableAssignment", f"Case {case_id}")

            await self.wearable_repo.update_status(assignment.wearable_id, HardwareStatus.AVAILABLE.value)
            await self.db.commit()
            return assignment
        except Exception:
            await self.db.rollback()
            raise

    async def delete_wearable_assignment(
        self, case_id: UUID, wearable_id: UUID, assigned_from: datetime | None = None
    ) -> WearableAssignmentResponse | None:
        try:
            assignment = await self.assignment_repo.delete_wearable_assignment(case_id, wearable_id, assigned_from)

            if assignment:
                if assignment.assigned_to is None:
                    await self.wearable_repo.update_status(wearable_id, HardwareStatus.AVAILABLE.value)
                await self.db.commit()
                return assignment
            return None
        except Exception:
            await self.db.rollback()
            raise

    # Contexts
    async def link_context(self, case_id: UUID, context_id: UUID) -> ContextAssignmentResponse:
        try:
            result = await self.assignment_repo.link_context(case_id, context_id)
            await self.db.commit()

            # TODO: allign with other repos
            if not result:
                return ContextAssignmentResponse(case_id=case_id, context_id=context_id)
            return result
        except Exception:
            await self.db.rollback()
            raise

    async def unlink_context(self, case_id: UUID, context_id: UUID) -> ContextAssignmentResponse:
        try:
            result = await self.assignment_repo.unlink_context(case_id, context_id)
            if not result:
                raise EntityNotFoundError("ContextAssignment", f"{case_id}/{context_id}")

            await self.db.commit()
            return result
        except Exception:
            await self.db.rollback()
            raise
