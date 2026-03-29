import json
from asyncio import Semaphore
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self
from uuid import UUID

import strawberry
import strawberry.relay as relay
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry import cast as strawberry_cast
from strawberry.dataloader import DataLoader
from strawberry.relay.types import NodeIterableType
from strawberry.relay.utils import to_base64

from app.core.config import settings
from app.core.json_types import JsonObject
from app.core.utils import to_utc
from app.db.postgres.repos.assignment_repo import AssignmentCursorKey, AssignmentRepo
from app.db.postgres.repos.base import ConnectionItem, GroupedConnectionPage
from app.db.postgres.repos.case_repo import CaseRepo
from app.db.postgres.repos.context_repo import ContextRepo
from app.db.postgres.repos.fhir_mapping_repo import DotDependencyFileRepo
from app.graphql.context import context_from_info
from app.graphql.cursor_codec import decode_base64_cursor, invalid_cursor_argument
from app.graphql.keyset_connection import derive_page_flags, resolve_edge_type, resolve_pagination_window

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders

NESTED_CURSOR_PREFIX = "nested-keyset"
NESTED_CURSOR_VERSION = 1


class NestedConnectionField(StrEnum):
    PATIENT_CASES = "patient_cases"
    CONTEXT_CASES = "context_cases"
    CASE_CONTEXTS = "case_contexts"
    CASE_DEVICE_ASSIGNMENTS = "case_device_assignments"
    CASE_WEARABLE_ASSIGNMENTS = "case_wearable_assignments"
    MAPPING_DOT_DEPENDENCY_FILES = "mapping_dot_dependency_files"
    DEVICE_CASE_ASSIGNMENTS = "device_case_assignments"
    WEARABLE_CASE_ASSIGNMENTS = "wearable_case_assignments"
    CASE_DEVICES = "case_devices"
    CASE_WEARABLES = "case_wearables"


type NestedCursorKey = tuple[UUID] | tuple[datetime, UUID]


def _serialize_cursor_value(value: object) -> str:
    """Serialize a supported cursor key part into a stable string."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return to_utc(value).isoformat()
    raise TypeError(f"Unsupported cursor value type: {type(value).__name__}")


def _parse_uuid_key(raw_values: Sequence[str]) -> tuple[UUID]:
    if len(raw_values) != 1:
        raise ValueError("UUID cursor key requires exactly one value.")
    return (UUID(raw_values[0]),)


def _parse_datetime_uuid_key(raw_values: Sequence[str]) -> tuple[datetime, UUID]:
    """Parse a two part (datetime, UUID) cursor payload. (for assignment connections)"""
    if len(raw_values) != 2:
        raise ValueError("Datetime+UUID cursor key requires two values.")
    return (to_utc(datetime.fromisoformat(raw_values[0])), UUID(raw_values[1]))


_FIELD_CURSOR_PARSERS: dict[NestedConnectionField, Callable[[Sequence[str]], NestedCursorKey]] = {
    NestedConnectionField.PATIENT_CASES: _parse_uuid_key,
    NestedConnectionField.CONTEXT_CASES: _parse_uuid_key,
    NestedConnectionField.CASE_CONTEXTS: _parse_uuid_key,
    NestedConnectionField.CASE_DEVICE_ASSIGNMENTS: _parse_datetime_uuid_key,
    NestedConnectionField.CASE_WEARABLE_ASSIGNMENTS: _parse_datetime_uuid_key,
    NestedConnectionField.MAPPING_DOT_DEPENDENCY_FILES: _parse_uuid_key,
    NestedConnectionField.DEVICE_CASE_ASSIGNMENTS: _parse_datetime_uuid_key,
    NestedConnectionField.WEARABLE_CASE_ASSIGNMENTS: _parse_datetime_uuid_key,
    NestedConnectionField.CASE_DEVICES: _parse_datetime_uuid_key,
    NestedConnectionField.CASE_WEARABLES: _parse_datetime_uuid_key,
}


@dataclass(frozen=True)
class NestedConnectionSource[NodeType](Iterable[NodeType]):
    field: NestedConnectionField
    parent_id: UUID
    graphql_type: type[NodeType]

    # This has to be an iterable for strawberry
    def __iter__(self) -> Iterator[NodeType]:
        raise TypeError("NestedConnectionSource is resolved by NestedKeysetConnection, not iterated directly.")


@dataclass(frozen=True)
class NestedConnectionRequest:
    field: NestedConnectionField
    parent_id: UUID
    graphql_type: type[Any]
    page_size: int
    fetch_backward: bool
    after: str | None
    before: str | None


@dataclass(frozen=True)
class NestedConnectionSlice[NodeType]:
    nodes: list[NodeType]
    cursors: list[str]
    has_next_page: bool
    has_previous_page: bool
    start_cursor: str | None
    end_cursor: str | None


class NestedCursorCodec:
    @staticmethod
    def encode(field: NestedConnectionField, parent_id: UUID, key_values: Sequence[object]) -> str:
        """Encode nested connection cursor payload with field and parent scope."""
        payload: JsonObject = {
            "v": NESTED_CURSOR_VERSION,
            "f": field.value,
            "p": str(parent_id),
            "k": [_serialize_cursor_value(value) for value in key_values],
        }
        return to_base64(NESTED_CURSOR_PREFIX, json.dumps(payload, separators=(",", ":")))

    @staticmethod
    def decode(
        cursor: str, argument_name: str, expected_field: NestedConnectionField, expected_parent_id: UUID
    ) -> NestedCursorKey:
        try:
            encoded_payload = decode_base64_cursor(cursor, NESTED_CURSOR_PREFIX, argument_name)
            payload = json.loads(encoded_payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise invalid_cursor_argument(argument_name) from exc

        if not isinstance(payload, dict):
            raise invalid_cursor_argument(argument_name)

        if (
            payload.get("v") != NESTED_CURSOR_VERSION
            or payload.get("f") != expected_field.value
            or payload.get("p") != str(expected_parent_id)
        ):
            raise invalid_cursor_argument(argument_name)

        raw_values = payload.get("k")
        if not isinstance(raw_values, list) or not all(isinstance(item, str) for item in raw_values):
            raise invalid_cursor_argument(argument_name)

        try:
            return _FIELD_CURSOR_PARSERS[expected_field](raw_values)
        except ValueError as exc:
            raise invalid_cursor_argument(argument_name) from exc


class NestedConnectionLoader:
    """Batched GraphQL loader for nested keyset connections."""

    MAX_BATCH_SIZE = max(1, settings.GRAPHQL_DATALOADER_MAX_BATCH_SIZE)

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], db_semaphore: Semaphore):
        self._session_factory = session_factory
        self._db_semaphore = db_semaphore
        self._loader: DataLoader[NestedConnectionRequest, NestedConnectionSlice[Any]] = DataLoader(
            load_fn=self._batch_load, max_batch_size=self.MAX_BATCH_SIZE
        )

    async def load(self, request: NestedConnectionRequest) -> NestedConnectionSlice[Any]:
        """Queue and resolve one nested connection request through the batch loader."""
        return await self._loader.load(request)

    @staticmethod
    def _decode_request_cursors(
        request: NestedConnectionRequest,
    ) -> tuple[NestedCursorKey | None, NestedCursorKey | None]:
        """Decode request before/after cursors into typed key tuples."""
        after_key = (
            NestedCursorCodec.decode(
                request.after, "after", expected_field=request.field, expected_parent_id=request.parent_id
            )
            if request.after
            else None
        )
        before_key = (
            NestedCursorCodec.decode(
                request.before,
                "before",
                expected_field=request.field,
                expected_parent_id=request.parent_id,
            )
            if request.before
            else None
        )
        return after_key, before_key

    @staticmethod
    def _build_slice(
        request: NestedConnectionRequest, parent_items: Sequence[ConnectionItem[Any]], has_extra: bool
    ) -> NestedConnectionSlice[Any]:
        """Build a GraphQL connection slice (nodes, cursors, page flags) for one parent."""
        nodes = [strawberry_cast(request.graphql_type, item.node) for item in parent_items]
        cursors = [
            NestedCursorCodec.encode(request.field, request.parent_id, item.cursor_values) for item in parent_items
        ]
        has_next_page, has_previous_page = derive_page_flags(
            request.fetch_backward, has_extra, request.before, request.after
        )
        return NestedConnectionSlice(
            nodes=nodes,
            cursors=cursors,
            has_next_page=has_next_page,
            has_previous_page=has_previous_page,
            start_cursor=cursors[0] if cursors else None,
            end_cursor=cursors[-1] if cursors else None,
        )

    async def _batch_load(
        self, requests: list[NestedConnectionRequest]
    ) -> list[NestedConnectionSlice[Any] | BaseException]:
        """Batch nested requests by query shape and fan results back to each request."""
        results: list[NestedConnectionSlice[Any] | BaseException] = [RuntimeError("unresolved request")] * len(requests)

        grouped_requests: dict[
            tuple[NestedConnectionField, int, bool, NestedCursorKey | None, NestedCursorKey | None],
            list[tuple[int, NestedConnectionRequest]],
        ] = defaultdict(list)
        for index, request in enumerate(requests):
            try:
                after_key, before_key = self._decode_request_cursors(request)
            except TypeError as exc:
                results[index] = exc
                continue

            grouped_requests[(request.field, request.page_size, request.fetch_backward, after_key, before_key)].append(
                (index, request)
            )

        for (field, page_size, fetch_backward, after_key, before_key), grouped in grouped_requests.items():
            parent_ids = [request.parent_id for _, request in grouped]
            try:
                grouped_page = await self._fetch_grouped_page(
                    field, parent_ids, page_size, fetch_backward, after_key, before_key
                )
            except Exception as exc:
                for index, _request in grouped:
                    results[index] = exc
                continue

            for index, request in grouped:
                parent_items = grouped_page.items_by_parent.get(request.parent_id, [])
                has_extra = grouped_page.has_extra_by_parent.get(request.parent_id, False)
                results[index] = self._build_slice(request, parent_items, has_extra)

        return results

    async def _fetch_grouped_page(
        self,
        field: NestedConnectionField,
        parent_ids: list[UUID],
        page_size: int,
        fetch_backward: bool,
        after_key: NestedCursorKey | None,
        before_key: NestedCursorKey | None,
    ) -> GroupedConnectionPage[Any]:
        """Dispatch a GraphQL nested connection request to the corresponding repo connection query."""
        async with self._db_semaphore, self._session_factory() as db:
            match field:
                case (
                    NestedConnectionField.PATIENT_CASES
                    | NestedConnectionField.CONTEXT_CASES
                    | NestedConnectionField.CASE_CONTEXTS
                    | NestedConnectionField.MAPPING_DOT_DEPENDENCY_FILES
                ):
                    after_id, before_id = _cursor_uuid(after_key), _cursor_uuid(before_key)
                    match field:
                        case NestedConnectionField.PATIENT_CASES:
                            case_repo = CaseRepo(db)
                            return await case_repo.list_by_patient_ids_connection(
                                parent_ids, page_size, fetch_backward, after_id, before_id
                            )
                        case NestedConnectionField.CONTEXT_CASES:
                            case_repo = CaseRepo(db)
                            return await case_repo.list_by_context_ids_connection(
                                parent_ids, page_size, fetch_backward, after_id, before_id
                            )
                        case NestedConnectionField.CASE_CONTEXTS:
                            context_repo = ContextRepo(db)
                            return await context_repo.list_by_case_ids_connection(
                                parent_ids, page_size, fetch_backward, after_id, before_id
                            )
                        case NestedConnectionField.MAPPING_DOT_DEPENDENCY_FILES:
                            dot_dependency_file_repo = DotDependencyFileRepo(db)
                            return await dot_dependency_file_repo.list_by_mapping_ids_connection(
                                parent_ids, page_size, fetch_backward, after_id, before_id
                            )
                case (
                    NestedConnectionField.CASE_DEVICE_ASSIGNMENTS
                    | NestedConnectionField.CASE_WEARABLE_ASSIGNMENTS
                    | NestedConnectionField.DEVICE_CASE_ASSIGNMENTS
                    | NestedConnectionField.WEARABLE_CASE_ASSIGNMENTS
                    | NestedConnectionField.CASE_DEVICES
                    | NestedConnectionField.CASE_WEARABLES
                ):
                    assignment_repo = AssignmentRepo(db)
                    after_assignment_key, before_assignment_key = (
                        _cursor_datetime_uuid(after_key),
                        _cursor_datetime_uuid(before_key),
                    )
                    match field:
                        case NestedConnectionField.CASE_DEVICE_ASSIGNMENTS:
                            return await assignment_repo.list_device_assignments_by_case_ids_connection(
                                parent_ids, page_size, fetch_backward, after_assignment_key, before_assignment_key
                            )
                        case NestedConnectionField.CASE_WEARABLE_ASSIGNMENTS:
                            return await assignment_repo.list_wearable_assignments_by_case_ids_connection(
                                parent_ids, page_size, fetch_backward, after_assignment_key, before_assignment_key
                            )
                        case NestedConnectionField.DEVICE_CASE_ASSIGNMENTS:
                            return await assignment_repo.list_device_assignments_by_device_ids_connection(
                                parent_ids, page_size, fetch_backward, after_assignment_key, before_assignment_key
                            )
                        case NestedConnectionField.WEARABLE_CASE_ASSIGNMENTS:
                            return await assignment_repo.list_wearable_assignments_by_wearable_ids_connection(
                                parent_ids, page_size, fetch_backward, after_assignment_key, before_assignment_key
                            )
                        case NestedConnectionField.CASE_DEVICES:
                            return await assignment_repo.list_active_devices_by_case_ids_connection(
                                parent_ids, page_size, fetch_backward, after_assignment_key, before_assignment_key
                            )
                        case NestedConnectionField.CASE_WEARABLES:
                            return await assignment_repo.list_active_wearables_by_case_ids_connection(
                                parent_ids, page_size, fetch_backward, after_assignment_key, before_assignment_key
                            )
        # In case the field enum is extended without updating this loader -> fail with explicit error
        raise RuntimeError(f"Unsupported nested connection field '{field}'.")


@strawberry.type(name="NestedConnection", description="A connection to a list of items.")
class NestedKeysetConnection[NodeType: relay.Node](relay.ListConnection[NodeType]):
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
        """Resolve a nested keyset connection using the per request nested loader."""
        if not isinstance(nodes, NestedConnectionSource):
            raise TypeError("NestedKeysetConnection requires NestedConnectionSource nodes.")

        max_allowed = max_results if max_results is not None else info.schema.config.relay_max_results
        window = resolve_pagination_window(first=first, last=last, max_allowed=max_allowed)

        loaders: Loaders = context_from_info(info)["loaders"]
        result = await loaders.nested_connections.load(
            NestedConnectionRequest(
                nodes.field, nodes.parent_id, nodes.graphql_type, window.page_size, window.fetch_backward, after, before
            )
        )

        edge_type = resolve_edge_type(cls)
        edges = [
            edge_type(cursor=cursor, node=cls.resolve_node(node, info=info, **kwargs))
            for cursor, node in zip(result.cursors, result.nodes, strict=True)
        ]
        return cls(
            edges=edges,
            page_info=relay.PageInfo(
                has_next_page=result.has_next_page,
                has_previous_page=result.has_previous_page,
                start_cursor=result.start_cursor,
                end_cursor=result.end_cursor,
            ),
        )


def _cursor_uuid(key: NestedCursorKey | None) -> UUID | None:
    """Decode UUID cursor keys used by GraphQL nested keyed connections. Makes pyright happy."""
    if key is None:
        return None
    head = key[0]
    if not isinstance(head, UUID):
        raise TypeError("Invalid cursor key type.")
    return head


def _cursor_datetime_uuid(key: NestedCursorKey | None) -> AssignmentCursorKey | None:
    """Decode (datetime, UUID) cursor keys used by GraphQL assignment nested connections. Makes pyright happy."""
    if key is None:
        return None
    if len(key) != 2:
        raise TypeError("Invalid cursor key shape.")
    first, second = key
    if not isinstance(first, datetime) or not isinstance(second, UUID):
        raise TypeError("Invalid cursor key type.")
    return (first, second)
