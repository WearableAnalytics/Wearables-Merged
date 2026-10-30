"""Closed account provisioning and password authentication. Secrets are never response fields."""

from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, field_validator, model_validator

from app.schemas.control import UserResponse, UserRole

Password = Annotated[SecretStr, Field(min_length=1, max_length=256)]


class PasswordModel(BaseModel):
    # Password whitespace is significant. Do not inherit TunedBase's string stripping.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class PasswordLogin(PasswordModel):
    email: str = Field(min_length=3, max_length=320)
    password: Password

    @field_validator("email")
    @classmethod
    def email_normalized(cls, value: str) -> str:
        return value.strip().lower()


class PasswordActor(PasswordModel):
    actor_id: UUID
    actor_auth_version: int = Field(strict=True, ge=1)


class StaffCreate(PasswordActor):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str | None = Field(default=None, max_length=200)
    is_admin: StrictBool = False
    roles: list[UserRole] = Field(default_factory=list, max_length=2)
    temporary_password: Password

    @field_validator("email", mode="before")
    @classmethod
    def email_normalized(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def role_assignment(self) -> Self:
        if (self.is_admin and self.roles) or (not self.is_admin and not self.roles):
            raise ValueError("Choose admin authority or at least one staff role")
        if len(self.roles) != len(set(self.roles)):
            raise ValueError("Duplicate staff role")
        return self


class PasswordReset(PasswordActor):
    expected_revision: int = Field(strict=True, ge=1)
    temporary_password: Password


class PasswordChange(PasswordActor):
    current_password: Password
    new_password: Password


class PasswordResult(BaseModel):
    allowed: bool
    user: UserResponse | None = None
    password_change_required: bool = False
