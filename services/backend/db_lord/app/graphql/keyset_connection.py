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
from strawberry.types.base import StrawberryContainer, get_object_definition

from app.graphql.cursor_codec import decode_base64_cursor, encode_base64_cursor, invalid_cursor_argument

KEYSET_CURSOR_PREFIX = "keyset"


def _encode_keyset_cursor(node_id: UUID) -> str:
    return encode_base64_cursor(prefix=KEYSET_CURSOR_PREFIX, payload=str(node_id))


def _decode_keyset_cursor(cursor: str, argument_name: str) -> UUID:
    raw_value = decode_base64_cursor(
        cursor=cursor,
        expected_prefix=KEYSET_CURSOR_PREFIX,
        argument_name=argument_name,
    )

    try:
        return UUID(raw_value)
    except ValueError as exc:
        raise invalid_cursor_argument(argument_name) from exc


@dataclass(frozen=True)
class PaginationWindow:
    page_size: int
    fetch_backward: bool


def resolve_pagination_window(first: int | None, last: int | None, max_allowed: int) -> PaginationWindow:
    if first is not None and last is not None:
        raise ValueError("Arguments 'first' and 'last' cannot both be provided.")

    if first is not None:
        if first < 0:
            raise ValueError("Argument 'first' must be a non-negative integer.")
        if first > max_allowed:
            raise ValueError(f"Argument 'first' cannot be higher than {max_allowed}.")
        return PaginationWindow(page_size=first, fetch_backward=False)

    if last is not None:
        if last < 0:
            raise ValueError("Argument 'last' must be a non-negative integer.")
        if last > max_allowed:
            raise ValueError(f"Argument 'last' cannot be higher than {max_allowed}.")
        return PaginationWindow(page_size=last, fetch_backward=True)

    return PaginationWindow(page_size=max_allowed, fetch_backward=False)


def derive_page_flags(
    *,
    fetch_backward: bool,
    has_extra: bool,
    before: str | None,
    after: str | None,
) -> tuple[bool, bool]:
    if fetch_backward:
        has_previous_page = has_extra
        has_next_page = before is not None
    else:
        has_previous_page = after is not None
        has_next_page = has_extra
    return has_next_page, has_previous_page


@cache
def resolve_edge_type(connection_type: type[relay.Connection[Any]]) -> type[relay.Edge[Any]]:
    type_def = get_object_definition(connection_type)
    assert type_def is not None
    field_def = type_def.get_field("edges")
    assert field_def is not None

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
        raise TypeError("KeysetSource is resolved by KeysetConnection, not iterated directly.")


@strawberry.type(name="Connection", description="A connection to a list of items.")
class KeysetConnection[NodeType](relay.ListConnection[NodeType]):  # pyright: ignore[reportInvalidTypeArguments]
    @classmethod
    async def resolve_connection(
        cls,
        nodes: NodeIterableType[NodeType],
        *,
        info: strawberry.Info,
        before: str | None = None,
        after: str | None = None,
        first: int | None = None,
        last: int | None = None,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> Self:
        if not isinstance(nodes, KeysetSource):
            raise TypeError("KeysetConnection requires KeysetSource nodes.")

        max_allowed = max_results if max_results is not None else info.schema.config.relay_max_results
        window = resolve_pagination_window(first=first, last=last, max_allowed=max_allowed)
        page_size = window.page_size
        fetch_backward = window.fetch_backward

        after_id = _decode_keyset_cursor(after, "after") if after else None
        before_id = _decode_keyset_cursor(before, "before") if before else None

        query = select(nodes.model)
        if nodes.where_clause is not None:
            query = query.where(nodes.where_clause)
        if after_id is not None:
            query = query.where(nodes.model.id < after_id)
        if before_id is not None:
            query = query.where(nodes.model.id > before_id)

        fetch_limit = page_size + 1 if page_size > 0 else 1
        order_by = nodes.model.id.asc() if fetch_backward else nodes.model.id.desc()
        query = query.order_by(order_by).limit(fetch_limit)

        async with nodes.db_semaphore, nodes.session_factory() as db:
            result = await db.execute(query)
            entities = list(result.scalars().all())

        if page_size == 0:
            has_extra = bool(entities)
            entities = []
        else:
            has_extra = len(entities) > page_size
            if has_extra:
                entities = entities[:page_size]

        if fetch_backward:
            entities.reverse()

        has_next_page, has_previous_page = derive_page_flags(
            fetch_backward=fetch_backward,
            has_extra=has_extra,
            before=before,
            after=after,
        )

        edge_type = resolve_edge_type(cls)
        edges = [
            edge_type(
                cursor=_encode_keyset_cursor(entity.id),
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
