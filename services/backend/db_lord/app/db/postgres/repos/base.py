from collections.abc import AsyncIterator, Sequence
from typing import Any

from fastapi_filters import FilterSet, SortingValues
from fastapi_filters.ext.sqlalchemy import apply_filters_and_sorting, apply_sorting
from fastapi_pagination.cursor import CursorPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import BaseModel
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.filters import GLOBAL_SORT_VALUES


class BaseRepo[ModelType: DeclarativeBase, CreateSchemaType: BaseModel, UpdateSchemaType: BaseModel]:
    """Base repository with CRUD operations using ORM models for Postgres.


    This counts are approximated using PostgreSQL's pg_class.reltuples.
    This statistic is updated by vacuum and analyze operations.

    For accurate counts after bulk inserts/updates, run:
        analyze table_name;

    TODO: Maybe Schedule periodic analyze in maintenance windows or after large data loads
    ->The default autovacuum settings probably work fine
    """

    def __init__(self, model: type[ModelType], db: AsyncSession, pk: str = "id"):
        self.model = model
        self.db = db
        self.pk_col = getattr(model, pk)

    async def get(self, id: Any) -> ModelType | None:
        return await self.db.get(self.model, id)

    async def get_all(self, limit: int = 1000) -> Sequence[ModelType]:
        query = select(self.model).limit(min(limit, 1000))
        result = await self.db.execute(query)
        return result.scalars().all()

    @staticmethod
    def _effective_sorting(sorting: SortingValues | None) -> SortingValues:
        return sorting if sorting is not None else GLOBAL_SORT_VALUES

    def _build_filtered_query(
        self,
        filters: FilterSet | None = None,
        sorting: SortingValues | None = None,
    ):
        query = select(self.model)
        effective_sorting = self._effective_sorting(sorting)
        if filters:
            return apply_filters_and_sorting(query, filters, effective_sorting), effective_sorting
        return apply_sorting(query, effective_sorting), effective_sorting

    async def stream_all(
        self,
        filters: FilterSet | None = None,
        sorting: SortingValues | None = None,
        batch_size: int = 500,
        as_mapping: bool = False,
    ) -> AsyncIterator[ModelType | RowMapping]:
        """Stream matching records using server-side cursors.

        `as_mapping=True` yields SQLAlchemy RowMapping objects projected from table columns,
        which avoids ORM entity construction for read-only streaming paths.
        """
        query, _ = self._build_filtered_query(filters, sorting)
        if as_mapping:
            query = query.with_only_columns(*self.model.__table__.c, maintain_column_froms=True)

        result = await self.db.stream(query)
        if as_mapping:
            async for row in result.mappings().yield_per(batch_size):
                row_mapping: RowMapping = row
                yield row_mapping
        else:
            async for row in result.scalars().yield_per(batch_size):
                entity: ModelType = row
                yield entity

    async def create(self, obj_in: CreateSchemaType) -> ModelType:
        obj_data = obj_in.model_dump(exclude_unset=True)
        obj = self.model(**obj_data)
        self.db.add(obj)
        await self.db.flush()
        return obj

    async def update(self, id: Any, obj_in: UpdateSchemaType) -> ModelType | None:
        obj_data = obj_in.model_dump(exclude_unset=True)
        if not obj_data:
            return await self.get(id)

        stmt = update(self.model).where(self.pk_col == id).values(**obj_data).returning(self.model)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, id: Any, obj_in: CreateSchemaType) -> ModelType | None:
        """Insert or update a record.

        On conflict updates all fields except the primary key.
        """
        insert_data = obj_in.model_dump(exclude_unset=True)
        insert_data[self.pk_col.key] = id

        # Exclude PK from update set
        update_data = {k: v for k, v in insert_data.items() if k != self.pk_col.key}

        stmt = (
            pg_insert(self.model)
            .values(**insert_data)
            .on_conflict_do_update(index_elements=[self.pk_col], set_=update_data)
            .returning(self.model)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, id: Any) -> ModelType | None:
        stmt = delete(self.model).where(self.pk_col == id).returning(self.model)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        filters: FilterSet | None = None,
        sorting: SortingValues | None = None,
    ) -> CursorPage[ModelType]:
        """
        List records with filtering, sorting, and cursor pagination.
        """
        query, effective_sorting = self._build_filtered_query(filters, sorting)

        # deterministic ordering for keyset pagination explicitly includes the primary key in sort fields
        if not any(sort and sort[0] == self.pk_col.key for sort in effective_sorting):
            query = query.order_by(self.pk_col.desc())

        return await apaginate(self.db, query)

    async def get_approximate_count(self) -> int:
        """Get approximate row count using pg_class.reltuples."""
        table_name = self.model.__tablename__
        query = text("SELECT reltuples::bigint FROM pg_class WHERE relname = :table_name")
        result = await self.db.execute(query, {"table_name": table_name})
        row = result.scalar()
        return max(0, row or 0)  # reltuples can be -1 for unknown tables
