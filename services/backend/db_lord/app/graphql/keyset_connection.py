from asyncio import Semaphore
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from functools import cache
from typing import Any, Self
from uuid import UUID

import strawberry
import strawberry.relay as relay
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from strawberry import cast as strawberry_cast
from strawberry.relay.types import NodeIterableType
from strawberry.relay.utils import to_base64
from strawberry.types.base import StrawberryContainer, get_object_definition

from app.graphql.context import context_from_info
from app.graphql.cursor_codec import decode_base64_cursor, invalid_cursor_argument

KEYSET_CURSOR_PREFIX = "keyset"


@dataclass(frozen=True)
class PaginationWindow:
    page_size: int
    fetch_backward: bool


def resolve_pagination_window(first: int | None, last: int | None, max_allowed: int) -> PaginationWindow:
    """Normalize Relay pagination args into a page size and traversal direction."""
    if first is not None and last is not None:
        raise ValueError("Arguments 'first' and 'last' cannot both be provided.")

    if first is not None:
        if first < 0:
            raise ValueError("Argument 'first' must be a non-negative integer.")
        if first > max_allowed:
            raise ValueError(f"Argument 'first' cannot be higher than {max_allowed}.")
        return PaginationWindow(first, False)

    if last is not None:
        if last < 0:
            raise ValueError("Argument 'last' must be a non-negative integer.")
        if last > max_allowed:
            raise ValueError(f"Argument 'last' cannot be higher than {max_allowed}.")
        return PaginationWindow(last, True)

    return PaginationWindow(max_allowed, False)


def derive_page_flags(
    fetch_backward: bool,
    has_extra: bool,
    before: str | None,
    after: str | None,
) -> tuple[bool, bool]:
    """Compute Relay `hasNextPage` / `hasPreviousPage` from keyset fetch context."""
    if fetch_backward:
        has_previous_page = has_extra
        has_next_page = before is not None
    else:
        has_previous_page = after is not None
        has_next_page = has_extra
    return has_next_page, has_previous_page


@cache
def resolve_edge_type(connection_type: type[relay.Connection[Any]]) -> type[relay.Edge[Any]]:
    """Resolve and cache the concrete Relay Edge type for a connection class."""
    type_def = get_object_definition(connection_type)
    if type_def is None:
        raise TypeError("Connection type is missing a Strawberry object definition.")
    field_def = type_def.get_field("edges")
    if field_def is None:
        raise TypeError("Connection type is missing an 'edges' field.")

    field_type = field_def.resolve_type(type_definition=type_def)
    while isinstance(field_type, StrawberryContainer):
        field_type = field_type.of_type

    if not isinstance(field_type, type) or not issubclass(field_type, relay.Edge):
        raise TypeError("Connection edges field did not resolve to a Relay Edge type.")
    return field_type


@dataclass(frozen=True)
class KeysetSource[NodeType](Iterable[NodeType]):
    session_factory: async_sessionmaker[AsyncSession]
    db_semaphore: Semaphore
    model: type[Any]
    graphql_type: type[NodeType]
    where_clause: ColumnElement[bool] | None = None

    def __iter__(self) -> Iterator[NodeType]:
        """Prevent direct iteration. Needs to inherit from iterable for Strawberry type resolution
        but should only be consumed by KeysetConnection."""
        raise TypeError("KeysetSource is resolved by KeysetConnection, not iterated directly.")


@strawberry.type(name="Connection", description="A connection to a list of items.")
class KeysetConnection[NodeType: relay.Node](relay.ListConnection[NodeType]):
    @classmethod
    async def resolve_connection(
        cls,
        nodes: NodeIterableType[NodeType],
        info: strawberry.Info,
        before: str | None = None,
        after: str | None = None,
        first: int | None = None,
        last: int | None = None,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> Self:
        """Resolve a Relay connection using ID keyset pagination over a SQLAlchemy model."""
        if not isinstance(nodes, KeysetSource):
            raise TypeError("KeysetConnection requires KeysetSource nodes.")

        max_allowed = max_results if max_results is not None else info.schema.config.relay_max_results
        window = resolve_pagination_window(first=first, last=last, max_allowed=max_allowed)
        page_size = window.page_size
        fetch_backward = window.fetch_backward

        after_id = None
        if after:
            try:
                after_id = UUID(decode_base64_cursor(after, KEYSET_CURSOR_PREFIX, "after"))
            except ValueError as exc:
                raise invalid_cursor_argument("after") from exc

        before_id = None
        if before:
            try:
                before_id = UUID(decode_base64_cursor(before, KEYSET_CURSOR_PREFIX, "before"))
            except ValueError as exc:
                raise invalid_cursor_argument("before") from exc

        query = select(nodes.model)
        if nodes.where_clause is not None:
            query = query.where(nodes.where_clause)
        if after_id is not None:
            query = query.where(nodes.model.id < after_id)
        if before_id is not None:
            query = query.where(nodes.model.id > before_id)

        # Fetch one extra row so we can derive Relay page flags without a separate query
        fetch_limit = page_size + 1 if page_size > 0 else 1
        order_by = nodes.model.id.asc() if fetch_backward else nodes.model.id.desc()
        query = query.order_by(order_by).limit(fetch_limit)

        async with nodes.db_semaphore, nodes.session_factory() as db:
            result = await db.execute(query)
            entities = list(result.scalars().all())

        context_from_info(info).loaders.prime_entities(nodes.graphql_type, entities)

        if page_size == 0:
            has_extra = bool(entities)
            entities = []
        else:
            has_extra = len(entities) > page_size
            if has_extra:
                entities = entities[:page_size]

        if fetch_backward:
            entities.reverse()

        has_next_page, has_previous_page = derive_page_flags(fetch_backward, has_extra, before, after)

        edge_type = resolve_edge_type(cls)
        edges = [
            edge_type(
                cursor=to_base64(KEYSET_CURSOR_PREFIX, str(entity.id)),
                node=cls.resolve_node(strawberry_cast(nodes.graphql_type, entity), info=info, **kwargs),
            )
            for entity in entities
        ]

        return cls(
            edges=edges,
            page_info=relay.PageInfo(
                has_next_page=has_next_page,
                has_previous_page=has_previous_page,
                start_cursor=edges[0].cursor if edges else None,
                end_cursor=edges[-1].cursor if edges else None,
            ),
        )
