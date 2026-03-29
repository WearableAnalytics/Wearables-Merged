from collections.abc import AsyncIterator, Awaitable, Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi_filters import FilterSet, SortingValues
from fastapi_filters.ext.sqlalchemy import apply_filters_and_sorting, apply_sorting
from fastapi_pagination.cursor import CursorPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.utils import ordered_unique
from app.filters import GLOBAL_SORT_VALUES


@dataclass(frozen=True)
class ConnectionItem[NodeType]:
    """GraphQL grouped connection item containing a node and cursor payload."""

    node: NodeType
    cursor_values: tuple[object, ...]


@dataclass(frozen=True)
class GroupedConnectionPage[NodeType]:
    """GraphQL grouped connection page keyed by parent id."""

    items_by_parent: dict[UUID, list[ConnectionItem[NodeType]]]
    has_extra_by_parent: dict[UUID, bool]

def slice_grouped_page[T](
    *, parent_ids: Sequence[UUID], values_by_parent: Mapping[UUID, list[T]], page_size: int, fetch_backward: bool
) -> tuple[dict[UUID, bool], dict[UUID, list[T]]]:
    """GraphQL helper: slice per-parent rows and normalize backward ordering."""
    has_extra_by_parent: dict[UUID, bool] = {}
    kept_values_by_parent: dict[UUID, list[T]] = {}
    for parent_id in parent_ids:
        values = values_by_parent.get(parent_id, [])
        has_extra_by_parent[parent_id] = len(values) > page_size if page_size > 0 else bool(values)
        if page_size == 0:
            kept_values: list[T] = []
        else:
            kept_values = values[:page_size]
            if fetch_backward:
                kept_values.reverse()
        kept_values_by_parent[parent_id] = kept_values
    return has_extra_by_parent, kept_values_by_parent


async def grouped_page_from_ranked_subquery[TValue: Hashable, NodeType](
    *,
    db: AsyncSession,
    parent_ids: Sequence[UUID],
    ranked_subquery: Any,
    page_size: int,
    fetch_backward: bool,
    value_from_row: Callable[[Any], TValue],
    load_nodes_by_value: Callable[[list[TValue]], Awaitable[dict[TValue, NodeType]]],
    cursor_values_from: Callable[[NodeType, TValue], tuple[object, ...]],
) -> GroupedConnectionPage[NodeType]:
    """Build per-parent connection payload for GraphQL resolvers from ranked SQL rows."""
    fetch_limit = page_size + 1 if page_size > 0 else 1
    rows_stmt = (
        select(*ranked_subquery.c)
        .where(ranked_subquery.c.rn <= fetch_limit)
        .order_by(ranked_subquery.c.parent_id, ranked_subquery.c.rn)
    )
    rows_result = await db.execute(rows_stmt)
    rows = rows_result.all()

    values_by_parent: dict[UUID, list[TValue]] = {}
    for row in rows:
        values_by_parent.setdefault(row.parent_id, []).append(value_from_row(row))

    has_extra_by_parent, kept_values_by_parent = slice_grouped_page(
        parent_ids=parent_ids,
        values_by_parent=values_by_parent,
        page_size=page_size,
        fetch_backward=fetch_backward,
    )

    unique_values: list[TValue] = ordered_unique(value for values in kept_values_by_parent.values() for value in values)
    nodes_by_value = await load_nodes_by_value(unique_values) if unique_values else {}

    items_by_parent: dict[UUID, list[ConnectionItem[NodeType]]] = {}
    for parent_id in parent_ids:
        parent_items: list[ConnectionItem[NodeType]] = []
        for value in kept_values_by_parent[parent_id]:
            node = nodes_by_value.get(value)
            if node is None:
                continue
            parent_items.append(ConnectionItem(node=node, cursor_values=cursor_values_from(node, value)))
        items_by_parent[parent_id] = parent_items

    return GroupedConnectionPage(items_by_parent=items_by_parent, has_extra_by_parent=has_extra_by_parent)


class BaseRepo[ModelType: DeclarativeBase, CreateSchemaType: BaseModel, UpdateSchemaType: BaseModel]:
    """Base repository with CRUD operations using ORM models for Postgres."""

    def __init__(self, model: type[ModelType], db: AsyncSession, pk: str = "id"):
        self.model = model
        self.db = db
        self.pk_col = getattr(model, pk)

    async def get(self, id: Any) -> ModelType | None:
        return await self.db.get(self.model, id)

    async def list_by_ids(self, ids: Sequence[Any]) -> list[ModelType]:
        if not ids:
            return []
        stmt = select(self.model).where(self.pk_col.in_(ids))
        return list(await self.db.scalars(stmt))

    async def map_by_ids(self, ids: Sequence[Any]) -> dict[Any, ModelType]:
        """Returns `{primary_key: entity}` for the given IDs.

        Used by GraphQL grouped connection loaders (`grouped_page_from_ranked_subquery`) which need
        fast key->node lookup after fetching ranked parent-child row keys.
        """
        entities = await self.list_by_ids(ids)
        return {getattr(entity, self.pk_col.key): entity for entity in entities}

    def _build_filtered_query(self, filters: FilterSet | None = None, sorting: SortingValues | None = None):
        """Create a filtered/sorted query and return the effective sorting used."""
        query = select(self.model)
        effective_sorting = sorting if sorting is not None else GLOBAL_SORT_VALUES
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
        avoids ORM entity construction for read-only streaming paths.
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
        return await self.db.scalar(stmt)

    async def delete(self, id: Any) -> ModelType | None:
        stmt = delete(self.model).where(self.pk_col == id).returning(self.model)
        return await self.db.scalar(stmt)

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
