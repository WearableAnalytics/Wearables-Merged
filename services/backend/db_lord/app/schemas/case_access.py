from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import Field, StrictBool, model_validator

from app.schemas.common import TunedBase

Scope = Literal["read", "export"]
Purpose = Literal["clinical-reference", "synthetic-research"]
Reason = Annotated[str, Field(min_length=1, max_length=256)]


class Actor(TunedBase):
    actor_id: UUID
    actor_auth_version: Annotated[int, Field(strict=True, ge=1)]


class AccessPut(Actor):
    expected_revision: Annotated[int, Field(strict=True, ge=0, le=9_223_372_036_854_775_807)]
    active: StrictBool
    purpose: Purpose
    scopes: Annotated[list[Scope], Field(max_length=2)]
    reason: Reason

    @model_validator(mode="after")
    def scopes_valid(self) -> Self:
        if (
            (self.active and "read" not in self.scopes)
            or len(set(self.scopes)) != len(self.scopes)
            or ("export" in self.scopes and "read" not in self.scopes)
        ):
            raise ValueError("INVALID_ACCESS_SCOPES")
        return self


class AccessResponse(TunedBase):
    case_id: UUID
    patient_id: UUID
    user_id: UUID
    active: bool
    purpose: Purpose
    scopes: list[Scope]
    revision: int
    created_at: datetime
    updated_at: datetime


class AccessPage(TunedBase):
    items: list[AccessResponse]
    next_cursor: UUID | None


class AccessDecision(Actor):
    case_id: UUID
    scope: Scope


class AccessDecisionResponse(TunedBase):
    case_id: UUID
    patient_id: UUID | None
    allowed: bool
    reason: str
    capabilities: list[Scope]
