from __future__ import annotations

from asyncio import Semaphore
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import strawberry
import strawberry.relay as relay
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry import cast as strawberry_cast

from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import DotDependencyFile as DotDependencyFileModel
from app.db.postgres.orm import FHIRMapping as FHIRMappingModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel
from app.graphql.connection_batching import NestedConnectionField, NestedConnectionSource, NestedKeysetConnection
from app.graphql.context import context_from_info
from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders


def _session_context(info: strawberry.Info) -> tuple[async_sessionmaker[AsyncSession], Semaphore]:
    context = context_from_info(info)
    return context["session_factory"], context["db_semaphore"]


async def _resolve_relay_nodes[TNode: relay.Node](
    *,
    info: strawberry.Info,
    node_ids: Iterable[str],
    model: type[Any],
    graphql_type: type[TNode],
    required: bool,
) -> list[TNode | None]:
    raw_node_ids = list(node_ids)
    parsed_node_ids: list[UUID | None] = []
    for node_id in raw_node_ids:
        try:
            parsed_node_ids.append(UUID(node_id))
        except ValueError:
            if required:
                raise ValueError(f"Invalid {graphql_type.__name__} node id '{node_id}'.") from None
            parsed_node_ids.append(None)

    valid_node_ids = [node_id for node_id in parsed_node_ids if node_id is not None]
    if not valid_node_ids:
        return [None for _ in raw_node_ids]

    session_factory, db_semaphore = _session_context(info)
    async with db_semaphore, session_factory() as db:
        result = await db.scalars(select(model).where(model.id.in_(valid_node_ids)))
        entities_by_id = {str(entity.id): strawberry_cast(graphql_type, entity) for entity in result}

    resolved_nodes: list[TNode | None] = []
    for raw_node_id, parsed_node_id in zip(raw_node_ids, parsed_node_ids, strict=True):
        if parsed_node_id is None:
            resolved_nodes.append(None)
            continue

        resolved = entities_by_id.get(str(parsed_node_id))
        if resolved is None and required:
            raise ValueError(f"{graphql_type.__name__} node '{raw_node_id}' was not found.")
        resolved_nodes.append(resolved)

    return resolved_nodes


@strawberry.type
class Patient(relay.Node):
    id: relay.NodeID[UUID]
    charite_id: UUID
    name: str
    sex: str | None
    dob: date | None
    weight: Decimal | None
    height: Decimal | None

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=PatientModel,
            graphql_type=cls,
            required=required,
        )

    @relay.connection(NestedKeysetConnection["Case"], description="Relay connection for patient cases.")
    async def cases(self) -> Iterable[Case]:
        return NestedConnectionSource(
            field=NestedConnectionField.PATIENT_CASES,
            parent_id=self.id,
            graphql_type=Case,
        )


@strawberry.type
class Device(relay.Node):
    id: relay.NodeID[UUID]
    serial_nr: str
    model: str
    manufacturer: str | None
    os_version: str
    status: HardwareStatus

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=DeviceModel,
            graphql_type=cls,
            required=required,
        )

    @relay.connection(
        NestedKeysetConnection["DeviceAssignment"],
        description="Relay connection for device case assignments.",
    )
    async def case_assignments(self) -> Iterable[DeviceAssignment]:
        return NestedConnectionSource(
            field=NestedConnectionField.DEVICE_CASE_ASSIGNMENTS,
            parent_id=self.id,
            graphql_type=DeviceAssignment,
        )


@strawberry.type
class Wearable(relay.Node):
    id: relay.NodeID[UUID]
    serial_nr: str
    model: str
    manufacturer: str | None
    os_version: str
    status: HardwareStatus

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=WearableModel,
            graphql_type=cls,
            required=required,
        )

    @relay.connection(
        NestedKeysetConnection["WearableAssignment"],
        description="Relay connection for wearable case assignments.",
    )
    async def case_assignments(self) -> Iterable[WearableAssignment]:
        return NestedConnectionSource(
            field=NestedConnectionField.WEARABLE_CASE_ASSIGNMENTS,
            parent_id=self.id,
            graphql_type=WearableAssignment,
        )


@strawberry.type
class Context(relay.Node):
    id: relay.NodeID[UUID]
    group_name: str
    coordinator: str | None

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=ContextModel,
            graphql_type=cls,
            required=required,
        )

    @relay.connection(NestedKeysetConnection["Case"], description="Relay connection for context cases.")
    async def cases(self) -> Iterable[Case]:
        return NestedConnectionSource(
            field=NestedConnectionField.CONTEXT_CASES,
            parent_id=self.id,
            graphql_type=Case,
        )


@strawberry.type
class FHIRMapping(relay.Node):
    id: relay.NodeID[UUID]
    version: str
    full_mapping: strawberry.scalars.JSON

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=FHIRMappingModel,
            graphql_type=cls,
            required=required,
        )


@strawberry.type
class DotDependencyFile(relay.Node):
    id: relay.NodeID[UUID]
    version: str
    category: str
    digraph: strawberry.scalars.JSON
    mapping_id: UUID

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=DotDependencyFileModel,
            graphql_type=cls,
            required=required,
        )


@strawberry.type
class DeviceAssignment:
    case_id: UUID
    device_id: UUID
    assigned_from: datetime
    assigned_to: datetime | None

    @strawberry.field
    async def device(self, info: strawberry.Info) -> Device | None:
        loaders: Loaders | None = context_from_info(info)["loaders"]
        if loaders is None:
            return None
        return await loaders.device_by_id.load(self.device_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Case | None:
        loaders: Loaders | None = context_from_info(info)["loaders"]
        if loaders is None:
            return None
        return await loaders.case_by_id.load(self.case_id)


@strawberry.type
class WearableAssignment:
    case_id: UUID
    wearable_id: UUID
    assigned_from: datetime
    assigned_to: datetime | None

    @strawberry.field
    async def wearable(self, info: strawberry.Info) -> Wearable | None:
        loaders: Loaders | None = context_from_info(info)["loaders"]
        if loaders is None:
            return None
        return await loaders.wearable_by_id.load(self.wearable_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Case | None:
        loaders: Loaders | None = context_from_info(info)["loaders"]
        if loaders is None:
            return None
        return await loaders.case_by_id.load(self.case_id)


@strawberry.type
class Case(relay.Node):
    id: relay.NodeID[UUID]
    status: CaseStatus
    patient_id: UUID

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=CaseModel,
            graphql_type=cls,
            required=required,
        )

    @strawberry.field
    async def patient(self, info: strawberry.Info) -> Patient | None:
        loaders: Loaders | None = context_from_info(info)["loaders"]
        if loaders is None:
            return None
        return await loaders.patient_by_id.load(self.patient_id)

    @relay.connection(NestedKeysetConnection[Device], description="Relay connection for active case devices.")
    async def devices(self) -> Iterable[Device]:
        return NestedConnectionSource(
            field=NestedConnectionField.CASE_DEVICES,
            parent_id=self.id,
            graphql_type=Device,
        )

    @relay.connection(
        NestedKeysetConnection[DeviceAssignment],
        description="Relay connection for case device assignments.",
    )
    async def device_assignments(self) -> Iterable[DeviceAssignment]:
        return NestedConnectionSource(
            field=NestedConnectionField.CASE_DEVICE_ASSIGNMENTS,
            parent_id=self.id,
            graphql_type=DeviceAssignment,
        )

    @relay.connection(NestedKeysetConnection[Wearable], description="Relay connection for active case wearables.")
    async def wearables(self) -> Iterable[Wearable]:
        return NestedConnectionSource(
            field=NestedConnectionField.CASE_WEARABLES,
            parent_id=self.id,
            graphql_type=Wearable,
        )

    @relay.connection(
        NestedKeysetConnection[WearableAssignment],
        description="Relay connection for case wearable assignments.",
    )
    async def wearable_assignments(self) -> Iterable[WearableAssignment]:
        return NestedConnectionSource(
            field=NestedConnectionField.CASE_WEARABLE_ASSIGNMENTS,
            parent_id=self.id,
            graphql_type=WearableAssignment,
        )

    @relay.connection(NestedKeysetConnection[Context], description="Relay connection for case contexts.")
    async def contexts(self) -> Iterable[Context]:
        return NestedConnectionSource(
            field=NestedConnectionField.CASE_CONTEXTS,
            parent_id=self.id,
            graphql_type=Context,
        )


@strawberry.type
class TelemetryPoint:
    timestamp: datetime
    measurement: str
    patient_id: str | None
    device_id: str | None
    wearable_id: str | None
    case_id: str | None
    mapping_id: str | None
    dot_dependency_file_id: str | None
    context_id: str | None
    other_tags: strawberry.scalars.JSON
    fields: strawberry.scalars.JSON


@strawberry.type
class TelemetryResolvedMetadata:
    patients: list[Patient]
    cases: list[Case]
    devices: list[Device]
    wearables: list[Wearable]
    contexts: list[Context]
    mappings: list[FHIRMapping]


@strawberry.type
class InfluxTagIntrospection:
    key: str
    values: list[str]


@strawberry.type
class InfluxMeasurementIntrospection:
    measurement: str
    tag_keys: list[str]
    field_keys: list[str]
    tags: list[InfluxTagIntrospection]


@strawberry.type
class InfluxDbIntrospection:
    bucket: str
    measurements: list[InfluxMeasurementIntrospection]


@strawberry.type
class TelemetryPage:
    items: list[TelemetryPoint]
    next_cursor: str | None
    resolved: TelemetryResolvedMetadata | None = None
