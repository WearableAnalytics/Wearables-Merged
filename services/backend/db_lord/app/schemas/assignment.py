from datetime import UTC, datetime
from uuid import UUID

from pydantic import Field

from .common import TunedBase, TunedUpdateBase


def utc_now() -> datetime:
    return datetime.now(UTC)


class DeviceAssignmentBase(TunedBase):
    case_id: UUID
    device_id: UUID
    assigned_from: datetime = Field(default_factory=utc_now)
    assigned_to: datetime | None = None


class DeviceAssignmentCreate(DeviceAssignmentBase):
    pass


class DeviceAssignmentUpdate(TunedUpdateBase):
    assigned_from: datetime | None = None  # Should we allow changing assigned_from?
    assigned_to: datetime | None = None


class DeviceAssignment(DeviceAssignmentBase):
    pass


class WearableAssignmentBase(TunedBase):
    case_id: UUID
    wearable_id: UUID
    assigned_from: datetime = Field(default_factory=utc_now)
    assigned_to: datetime | None = None


class WearableAssignmentCreate(WearableAssignmentBase):
    pass


class WearableAssignmentUpdate(TunedUpdateBase):
    assigned_from: datetime | None = None  # Should we allow changing assigned_from?
    assigned_to: datetime | None = None


class WearableAssignment(WearableAssignmentBase):
    pass


class ContextAssignmentBase(TunedBase):
    case_id: UUID
    context_id: UUID


class ContextAssignmentCreate(ContextAssignmentBase):
    pass


class ContextAssignmentUpdate(TunedUpdateBase):
    case_id: UUID | None = None
    context_id: UUID | None = None
