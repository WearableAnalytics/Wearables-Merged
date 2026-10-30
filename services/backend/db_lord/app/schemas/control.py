from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator

from app.schemas.common import TunedBase


def _request_date(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    utc = value.astimezone(UTC)
    # The existing browser/BFF model uses JavaScript Date (millisecond precision).
    return utc.replace(microsecond=(utc.microsecond // 1000) * 1000)


class UserStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class UserRole(StrEnum):
    PRACTITIONER = "practitioner"
    RESEARCHER = "researcher"


class RequestStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class RoleRequestStatuses(TunedBase):
    practitioner: RequestStatus = RequestStatus.NONE
    researcher: RequestStatus = RequestStatus.NONE


class RoleRequestDates(TunedBase):
    practitioner: AwareDatetime | None = None
    researcher: AwareDatetime | None = None

    @field_validator("practitioner", "researcher")
    @classmethod
    def canonical_dates(cls, value: datetime | None) -> datetime | None:
        return _request_date(value)


class RequestState(TunedBase):
    adminRequestStatus: RequestStatus = RequestStatus.NONE
    adminRequestedAt: AwareDatetime | None = None
    adminReviewedAt: AwareDatetime | None = None
    roleRequestStatuses: RoleRequestStatuses = Field(default_factory=RoleRequestStatuses)
    roleRequestedAt: RoleRequestDates = Field(default_factory=RoleRequestDates)
    roleReviewedAt: RoleRequestDates = Field(default_factory=RoleRequestDates)

    @field_validator("adminRequestedAt", "adminReviewedAt")
    @classmethod
    def canonical_dates(cls, value: datetime | None) -> datetime | None:
        return _request_date(value)


class UserCreate(TunedBase):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str | None = Field(default=None, max_length=200)
    roles: list[UserRole] = Field(default_factory=list, max_length=2)
    request_state: RequestState = Field(default_factory=RequestState)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserPatch(TunedBase):
    expected_revision: int = Field(ge=1)
    actor_id: UUID
    actor_auth_version: int = Field(strict=True, ge=1)
    name: str | None = Field(default=None, max_length=200)
    is_admin: bool | None = None
    roles: list[UserRole] | None = Field(default=None, max_length=2)
    status: UserStatus | None = None
    request_state: RequestState | None = None


class UserResponse(TunedBase):
    id: UUID
    email: str
    name: str | None
    is_admin: bool
    roles: list[UserRole]
    status: UserStatus
    auth_version: int
    revision: int
    request_state: RequestState
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    denied_at: datetime | None


class UserPage(TunedBase):
    items: list[UserResponse]
    next_cursor: UUID | None


class RevokeSessions(TunedBase):
    actor_id: UUID
    actor_auth_version: int = Field(strict=True, ge=1)
    expected_auth_version: int = Field(ge=1)


class UserDecision(TunedBase):
    user_id: UUID
    auth_version: int = Field(ge=1)
    required_roles: list[UserRole] = Field(default_factory=list, max_length=2)
    require_admin: bool = False


class UserDecisionResponse(TunedBase):
    allowed: bool
    reason: str
    user: UserResponse | None
    current_auth_version: int | None


class LoginChallengeCreate(TunedBase):
    token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_id: UUID
    auth_version: int = Field(strict=True, ge=1)
    ttl_seconds: int = Field(strict=True, ge=1, le=3600)


class LoginChallengeConsume(TunedBase):
    token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
