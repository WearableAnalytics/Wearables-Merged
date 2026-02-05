import uuid
from typing import Any

from pydantic import Field

from .common import TunedBase, TunedUpdateBase


class MappingsBase(TunedBase):
    version: str = Field(..., min_length=1, max_length=100)
    full_mapping: dict[str, Any]


class MappingsCreate(MappingsBase):
    pass


class MappingsUpdate(TunedUpdateBase):
    version: str | None = Field(None, min_length=1, max_length=100)
    full_mapping: dict[str, Any] | None


class Mappings(MappingsBase):
    id: uuid.UUID


class MapTreesBase(TunedBase):
    version: str = Field(..., min_length=1, max_length=100)
    map_tree: dict[str, Any]
    category: str = Field(..., min_length=1, max_length=100)
    mapping_id: uuid.UUID


class MapTreesCreate(MapTreesBase):
    pass


class MapTreesUpdate(TunedUpdateBase):
    version: str | None = Field(None, min_length=1, max_length=100)
    map_tree: dict[str, Any] | None
    category: str | None = Field(None, min_length=1, max_length=100)
    mapping_id: uuid.UUID | None


class MapTrees(MapTreesBase):
    id: uuid.UUID
