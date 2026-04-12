from uuid import UUID

from pydantic import Field

from app.model_constants import CONTEXT_COORDINATOR_MAX_LEN, CONTEXT_GROUP_NAME_MAX_LEN

from .common import TunedBase, TunedUpdateBase


class ContextBase(TunedBase):
    group_name: str = Field(
        ...,
        min_length=1,
        max_length=CONTEXT_GROUP_NAME_MAX_LEN,
        description="Name of the context group.",
    )
    coordinator: str | None = Field(
        None,
        max_length=CONTEXT_COORDINATOR_MAX_LEN,
        description="Optional coordinator or owner for the context.",
    )


class ContextCreate(ContextBase):
    pass


class ContextUpdate(TunedUpdateBase):
    group_name: str | None = Field(None, min_length=1, max_length=CONTEXT_GROUP_NAME_MAX_LEN)
    coordinator: str | None = Field(None, max_length=CONTEXT_COORDINATOR_MAX_LEN)


class ContextResponse(ContextBase):
    id: UUID
