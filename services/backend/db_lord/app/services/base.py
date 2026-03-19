from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

from fastapi_filters import FilterSet, SortingValues
from fastapi_pagination.cursor import CursorPage
from pydantic import BaseModel
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.exceptions import EntityNotFoundError
from app.db.postgres.repos.base import BaseRepo


class BaseService[
    ModelType: DeclarativeBase,
    CreateSchemaType: BaseModel,
    UpdateSchemaType: BaseModel,
    RepoType: BaseRepo[Any, Any, Any],
]:
    """Base service with CRUD operations using ORM models."""

    def __init__(self, repo: RepoType):
        self.repo: RepoType = repo
        self.db: AsyncSession = repo.db
        self.name = repo.model.__name__.replace("Model", "")

    async def get(self, id: UUID) -> ModelType:
        result = await self.repo.get(id=id)
        if not result:
            raise EntityNotFoundError(self.name, id)
        return result

    async def list(
        self, filters: FilterSet | None = None, sorting: SortingValues | None = None
    ) -> CursorPage[ModelType]:
        return await self.repo.list_paginated(filters, sorting)

    def stream_all(
        self,
        filters: FilterSet | None = None,
        sorting: SortingValues | None = None,
        batch_size: int = 500,
        as_mapping: bool = False,
    ) -> AsyncIterator[ModelType | RowMapping]:
        return self.repo.stream_all(filters, sorting, batch_size, as_mapping)

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        async with self.db.begin():
            new_obj = await self.repo.create(obj_in)
            return new_obj

    async def update(self, id: UUID, obj_in: UpdateSchemaType) -> ModelType:
        async with self.db.begin():
            result = await self.repo.update(id, obj_in)
            if not result:
                raise EntityNotFoundError(self.name, id)
            return result

    async def delete(self, id: UUID) -> ModelType:
        async with self.db.begin():
            result = await self.repo.delete(id)
            if not result:
                raise EntityNotFoundError(self.name, id)
            return result
