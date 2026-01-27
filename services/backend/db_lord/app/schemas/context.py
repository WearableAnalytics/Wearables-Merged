import uuid

from pydantic import Field

from .common import TunedBase


class ContextBase(TunedBase):
    group_name: str = Field(..., min_length=1, max_length=100)
    coordinator: str | None = Field(None, max_length=255)


class ContextCreate(ContextBase):
    pass


class ContextUpdate(TunedBase):
    group_name: str | None = Field(None, min_length=1, max_length=100)
    coordinator: str | None = Field(None, max_length=255)


class Context(ContextBase):
    id: uuid.UUID
