from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from fastapi_filters import FilterSet, SortingValues
from fastapi_pagination.cursor import CursorPage
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.exceptions import ConflictError, DuplicateEntityError, EntityNotFoundError
from app.db.postgres.repos.base import BaseRepo


class BaseService[
    ModelType: DeclarativeBase,
    CreateSchemaType: BaseModel,
    UpdateSchemaType: BaseModel,
    RepoType: BaseRepo,
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

    async def get_all(self) -> Sequence[ModelType]:
        return await self.repo.get_all()

    async def list(
        self, filters: FilterSet | None = None, sorting: SortingValues | None = None
    ) -> CursorPage[ModelType]:
        return await self.repo.list_paginated(filters, sorting)

    def stream_all(
        self, filters: FilterSet | None = None, sorting: SortingValues | None = None, batch_size: int = 500
    ) -> AsyncIterator[ModelType]:
        return self.repo.stream_all(filters=filters, sorting=sorting, batch_size=batch_size)

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        try:
            new_obj = await self.repo.create(obj_in)
            await self.db.commit()
            return new_obj
        except IntegrityError as e:
            await self.db.rollback()
            raise DuplicateEntityError(self.name, "constraint violation") from e

    async def update(self, id: UUID, obj_in: UpdateSchemaType) -> ModelType:
        try:
            result = await self.repo.update(id, obj_in)
            if not result:
                raise EntityNotFoundError(self.name, id)
            await self.db.commit()
            return result
        except IntegrityError as e:
            await self.db.rollback()
            raise DuplicateEntityError(self.name, "constraint violation during update") from e

    async def delete(self, id: UUID) -> ModelType:
        try:
            result = await self.repo.delete(id)
            if not result:
                raise EntityNotFoundError(self.name, id)
            await self.db.commit()
            return result
        except IntegrityError as e:
            await self.db.rollback()
            raise ConflictError(f"Cannot delete {self.name} due to existing references or constraints") from e
