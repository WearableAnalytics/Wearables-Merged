from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, field_validator

from .common import TunedBase, TunedUpdateBase


# TODO: current hack for sqllite test suite since it doesn't support timezone-aware datetimes.
# should proably just change the test suite instead of adding this hack to the main codebase.
class _AssignmentDateTimeMixin(TunedBase):
    @field_validator("assigned_from", "assigned_to", mode="before", check_fields=False)
    @classmethod
    def _ensure_timezone_aware(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class DeviceAssignmentCreate(TunedBase):
    assigned_from: AwareDatetime | None
    assigned_to: AwareDatetime | None = None


class DeviceAssignmentUpdate(TunedUpdateBase):
    case_id: UUID
    device_id: UUID
    assigned_from: AwareDatetime | None = None  # Should we allow changing assigned_from?
    assigned_to: AwareDatetime | None = None


class DeviceAssignmentResponse(_AssignmentDateTimeMixin):
    case_id: UUID
    device_id: UUID
    assigned_from: AwareDatetime
    assigned_to: AwareDatetime | None


class WearableAssignmentCreate(TunedBase):
    assigned_from: AwareDatetime | None
    assigned_to: AwareDatetime | None = None


class WearableAssignmentUpdate(TunedUpdateBase):
    case_id: UUID
    wearable_id: UUID
    assigned_from: AwareDatetime | None = None
    assigned_to: AwareDatetime | None = None


class WearableAssignmentResponse(_AssignmentDateTimeMixin):
    case_id: UUID
    wearable_id: UUID
    assigned_from: AwareDatetime
    assigned_to: AwareDatetime | None


class ContextAssignmentCreate(TunedBase):
    case_id: UUID
    context_id: UUID


class ContextAssignmentUpdate(TunedUpdateBase):
    case_id: UUID | None = None
    context_id: UUID | None = None


class ContextAssignmentResponse(TunedBase):
    case_id: UUID
    context_id: UUID
