from uuid import UUID

from pydantic import AwareDatetime, model_validator

from .common import TunedBase, TunedUpdateBase


class DeviceAssignmentCreate(TunedBase):
    assigned_from: AwareDatetime | None
    assigned_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_assignment_window(self) -> DeviceAssignmentCreate:
        if self.assigned_from is not None and self.assigned_to is not None and self.assigned_to <= self.assigned_from:
            msg = "assigned_to must be later than assigned_from"
            raise ValueError(msg)
        return self


class DeviceAssignmentUpdate(TunedUpdateBase):
    case_id: UUID
    device_id: UUID
    assigned_from: AwareDatetime | None = None  # Should we allow changing assigned_from?
    assigned_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_assignment_window(self) -> DeviceAssignmentUpdate:
        if self.assigned_from is not None and self.assigned_to is not None and self.assigned_to <= self.assigned_from:
            msg = "assigned_to must be later than assigned_from"
            raise ValueError(msg)
        return self


class DeviceAssignmentResponse(TunedBase):
    case_id: UUID
    device_id: UUID
    assigned_from: AwareDatetime
    assigned_to: AwareDatetime | None


class WearableAssignmentCreate(TunedBase):
    assigned_from: AwareDatetime | None
    assigned_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_assignment_window(self) -> WearableAssignmentCreate:
        if self.assigned_from is not None and self.assigned_to is not None and self.assigned_to <= self.assigned_from:
            msg = "assigned_to must be later than assigned_from"
            raise ValueError(msg)
        return self


class WearableAssignmentUpdate(TunedUpdateBase):
    case_id: UUID
    wearable_id: UUID
    assigned_from: AwareDatetime | None = None
    assigned_to: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_assignment_window(self) -> WearableAssignmentUpdate:
        if self.assigned_from is not None and self.assigned_to is not None and self.assigned_to <= self.assigned_from:
            msg = "assigned_to must be later than assigned_from"
            raise ValueError(msg)
        return self


class WearableAssignmentResponse(TunedBase):
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
