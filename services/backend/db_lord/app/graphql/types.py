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
from strawberry.types.cast import cast as strawberry_cast

from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel
from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders


def _session_context(info: strawberry.Info) -> tuple[async_sessionmaker[AsyncSession], Semaphore]:
    return info.context["session_factory"], info.context["db_semaphore"]


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
        result = await db.execute(select(model).where(model.id.in_(valid_node_ids)))
        entities_by_id = {str(entity.id): strawberry_cast(graphql_type, entity) for entity in result.scalars().all()}

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
    ) -> list[Patient | None]:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=PatientModel,
            graphql_type=cls,
            required=required,
        )

    @strawberry.field
    async def cases(self, info: strawberry.Info) -> list[Case]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.cases_by_patient.load(self.id)


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
    ) -> list[Device | None]:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=DeviceModel,
            graphql_type=cls,
            required=required,
        )

    @strawberry.field
    async def case_assignments(self, info: strawberry.Info) -> list[DeviceAssignment]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.device_assignments_by_device.load(self.id)


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
    ) -> list[Wearable | None]:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=WearableModel,
            graphql_type=cls,
            required=required,
        )

    @strawberry.field
    async def case_assignments(self, info: strawberry.Info) -> list[WearableAssignment]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearable_assignments_by_wearable.load(self.id)


@strawberry.type
class Context(relay.Node):
    id: relay.NodeID[UUID]
    group_name: str
    coordinator: str | None

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> list[Context | None]:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=ContextModel,
            graphql_type=cls,
            required=required,
        )

    @strawberry.field
    async def cases(self, info: strawberry.Info) -> list[Case]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.cases_by_context.load(self.id)


@strawberry.type
class FHIRMapping:
    id: UUID
    version: str
    full_mapping: strawberry.scalars.JSON


@strawberry.type
class DotDependencyFile:
    id: UUID
    version: str
    category: str
    digraph: strawberry.scalars.JSON
    mapping_id: UUID


@strawberry.type
class DeviceAssignment:
    case_id: UUID
    device_id: UUID
    assigned_from: datetime
    assigned_to: datetime | None

    @strawberry.field
    async def device(self, info: strawberry.Info) -> Device | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.device_by_id.load(self.device_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Case | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.case_by_id.load(self.case_id)


@strawberry.type
class WearableAssignment:
    case_id: UUID
    wearable_id: UUID
    assigned_from: datetime
    assigned_to: datetime | None

    @strawberry.field
    async def wearable(self, info: strawberry.Info) -> Wearable | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearable_by_id.load(self.wearable_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Case | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.case_by_id.load(self.case_id)


@strawberry.type
class Case(relay.Node):
    id: relay.NodeID[UUID]
    status: CaseStatus
    patient_id: UUID

    @classmethod
    async def resolve_nodes(
        cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False
    ) -> list[Case | None]:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=CaseModel,
            graphql_type=cls,
            required=required,
        )

    @strawberry.field
    async def patient(self, info: strawberry.Info) -> Patient | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.patient_by_id.load(self.patient_id)

    @strawberry.field
    async def devices(self, info: strawberry.Info) -> list[Device]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.devices_by_case.load(self.id)

    @strawberry.field
    async def device_assignments(self, info: strawberry.Info) -> list[DeviceAssignment]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.device_assignments_by_case.load(self.id)

    @strawberry.field
    async def wearables(self, info: strawberry.Info) -> list[Wearable]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearables_by_case.load(self.id)

    @strawberry.field
    async def wearable_assignments(self, info: strawberry.Info) -> list[WearableAssignment]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearable_assignments_by_case.load(self.id)

    @strawberry.field
    async def contexts(self, info: strawberry.Info) -> list[Context]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.contexts_by_case.load(self.id)


@strawberry.type
class TelemetryPoint:
    timestamp: datetime
    measurement: str
    patient_id: str | None
    device_id: str | None
    wearable_id: str | None
    case_id: str | None
    mapping_id: str | None
    code: str | None
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
