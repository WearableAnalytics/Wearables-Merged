import uuid
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import RowMapping, Table, delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

PK = TypeVar("PK", int, str, uuid.UUID)


class BaseRepo[ModelType: Table, CreateSchemaType: BaseModel, UpdateSchemaType: BaseModel]:
    def __init__(self, model: ModelType, db: AsyncSession, pk: str = "id"):
        self.model = model
        self.db = db
        self.pk_col = model.c[pk]

    async def get(self, id: Any) -> RowMapping | None:
        query = select(self.model).where(self.pk_col == id)
        result = await self.db.execute(query)
        return result.mappings().first()

    async def get_all(self) -> Sequence[RowMapping]:
        query = select(self.model)
        result = await self.db.execute(query)
        return result.mappings().all()

    async def create(self, obj_in: CreateSchemaType) -> RowMapping | None:
        obj_data = obj_in.model_dump()
        stmt = insert(self.model).values(**obj_data).returning(self.model)
        result = await self.db.execute(stmt)
        return result.mappings().first()

    async def delete(self, id: Any) -> RowMapping | None:
        stmt = delete(self.model).where(self.pk_col == id).returning(self.model)
        result = await self.db.execute(stmt)
        return result.mappings().first()

    async def update(self, id: Any, obj_in: UpdateSchemaType) -> RowMapping | None:
        obj_data = obj_in.model_dump(exclude_unset=True)
        if not obj_data:
            return await self.get(id)

        stmt = update(self.model).where(self.pk_col == id).values(**obj_data).returning(self.model)
        result = await self.db.execute(stmt)
        return result.mappings().first()

    async def upsert(self, id: Any, obj_in: CreateSchemaType) -> RowMapping | None:
        obj_data = obj_in.model_dump()
        obj_data["id"] = id

        stmt = pg_insert(self.model).values(**obj_data)

        # Prepare update set (all fields except id)
        update_set = {k: v for k, v in obj_data.items() if k != self.pk_col.name}

        if not update_set:
            # If no fields to update (only ID), do nothing on conflict
            final_stmt = stmt.on_conflict_do_nothing(index_elements=[self.pk_col]).returning(self.model)
        else:
            final_stmt = stmt.on_conflict_do_update(index_elements=[self.pk_col], set_=update_set).returning(self.model)

        result = await self.db.execute(final_stmt)
        return result.mappings().first()
