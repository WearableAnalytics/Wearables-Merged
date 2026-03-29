from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, ClassVar, cast
from uuid import UUID

import strawberry
import strawberry.relay as relay
from sqlalchemy import select, tuple_
from strawberry import cast as strawberry_cast

from app.core.json_types import JsonObject, JsonValue
from app.core.utils import to_utc
from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import CaseDevice as CaseDeviceModel
from app.db.postgres.orm import CaseWearable as CaseWearableModel
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
from app.telemetry.types import TelemetryRecordTags

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders


def _encode_assignment_node_id(case_id: UUID, asset_id: UUID, assigned_from: datetime) -> str:
    return json.dumps(
        {
            "c": str(case_id),
            "a": str(asset_id),
            "t": to_utc(assigned_from).isoformat(),
        },
        separators=(",", ":"),
    )


def _decode_assignment_node_id(node_id: str) -> tuple[UUID, UUID, datetime]:
    try:
        payload = json.loads(node_id)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid assignment node id.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid assignment node id.")

    case_raw = payload.get("c")
    asset_raw = payload.get("a")
    assigned_from_raw = payload.get("t")
    if not isinstance(case_raw, str) or not isinstance(asset_raw, str) or not isinstance(assigned_from_raw, str):
        raise ValueError("Invalid assignment node id.")

    try:
        return UUID(case_raw), UUID(asset_raw), to_utc(datetime.fromisoformat(assigned_from_raw))
    except ValueError as exc:
        raise ValueError("Invalid assignment node id.") from exc


async def _resolve_relay_nodes[TNode: relay.Node](
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

    context = context_from_info(info)
    session_factory = context["session_factory"]
    db_semaphore = context["db_semaphore"]
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


class UuidRelayNodeMixin:
    _relay_model: ClassVar[type[Any]]

    @classmethod
    async def resolve_nodes(cls, *, info: strawberry.Info, node_ids: Iterable[str], required: bool = False) -> Any:
        return await _resolve_relay_nodes(
            info=info,
            node_ids=node_ids,
            model=cls._relay_model,
            graphql_type=cls,
            required=required,
        )


@strawberry.type
class Patient(UuidRelayNodeMixin, relay.Node):
    _relay_model = PatientModel

    id: relay.NodeID[UUID]
    charite_id: UUID
    name: str
    sex: str | None
    dob: date | None
    weight: Decimal | None
    height: Decimal | None

    @relay.connection(NestedKeysetConnection["Case"], description="Relay connection for patient cases.")
    async def cases(self) -> Iterable[Case]:
        return NestedConnectionSource(
            NestedConnectionField.PATIENT_CASES,
            self.id,
            Case,
        )


@strawberry.type
class Device(UuidRelayNodeMixin, relay.Node):
    _relay_model = DeviceModel

    id: relay.NodeID[UUID]
    serial_nr: str
    model: str
    manufacturer: str | None
    os_version: str
    status: HardwareStatus

    @relay.connection(
        NestedKeysetConnection["DeviceAssignment"], description="Relay connection for device case assignments."
    )
    async def case_assignments(self) -> Iterable[DeviceAssignment]:
        return NestedConnectionSource(
            NestedConnectionField.DEVICE_CASE_ASSIGNMENTS,
            self.id,
            DeviceAssignment,
        )


@strawberry.type
class Wearable(UuidRelayNodeMixin, relay.Node):
    _relay_model = WearableModel

    id: relay.NodeID[UUID]
    serial_nr: str
    model: str
    manufacturer: str | None
    os_version: str
    status: HardwareStatus

    @relay.connection(
        NestedKeysetConnection["WearableAssignment"], description="Relay connection for wearable case assignments."
    )
    async def case_assignments(self) -> Iterable[WearableAssignment]:
        return NestedConnectionSource(
            NestedConnectionField.WEARABLE_CASE_ASSIGNMENTS,
            self.id,
            WearableAssignment,
        )


@strawberry.type
class Context(UuidRelayNodeMixin, relay.Node):
    _relay_model = ContextModel

    id: relay.NodeID[UUID]
    group_name: str
    coordinator: str | None

    @relay.connection(NestedKeysetConnection["Case"], description="Relay connection for context cases.")
    async def cases(self) -> Iterable[Case]:
        return NestedConnectionSource(
            NestedConnectionField.CONTEXT_CASES,
            self.id,
            Case,
        )


@strawberry.type
class FHIRMapping(UuidRelayNodeMixin, relay.Node):
    _relay_model = FHIRMappingModel

    id: relay.NodeID[UUID]
    version: str
    full_mapping: strawberry.scalars.JSON

    @relay.connection(
        NestedKeysetConnection["DotDependencyFile"],
        description="Relay connection for dot dependency files belonging to this mapping.",
    )
    async def dot_dependency_files(self) -> Iterable[DotDependencyFile]:
        return NestedConnectionSource(
            NestedConnectionField.MAPPING_DOT_DEPENDENCY_FILES,
            self.id,
            DotDependencyFile,
        )


@strawberry.type
class DotDependencyFile(UuidRelayNodeMixin, relay.Node):
    _relay_model = DotDependencyFileModel

    id: relay.NodeID[UUID]
    version: str
    category: str
    digraph: strawberry.scalars.JSON
    mapping_id: UUID

    @strawberry.field
    async def mapping(self, info: strawberry.Info) -> FHIRMapping | None:
        loaders: Loaders = context_from_info(info)["loaders"]
        return await loaders.fhir_mapping_by_id.load(self.mapping_id)


@strawberry.type
class DeviceAssignment(relay.Node):
    id: relay.NodeID[str]
    case_id: UUID
    device_id: UUID
    assigned_from: datetime
    assigned_to: datetime | None

    @classmethod
    def resolve_id(cls, root: Any, *, info: strawberry.Info) -> str:
        return _encode_assignment_node_id(root.case_id, root.device_id, root.assigned_from)

    @classmethod
    async def resolve_nodes(cls, info: strawberry.Info, node_ids: Iterable[str], required: bool = False) -> Any:
        raw_node_ids = list(node_ids)
        parsed_node_ids: list[tuple[UUID, UUID, datetime] | None] = []
        for node_id in raw_node_ids:
            try:
                parsed_node_ids.append(_decode_assignment_node_id(node_id))
            except ValueError:
                if required:
                    raise ValueError(f"Invalid {cls.__name__} node id '{node_id}'.") from None
                parsed_node_ids.append(None)

        keys = [key for key in parsed_node_ids if key is not None]
        if not keys:
            return [None for _ in raw_node_ids]

        context = context_from_info(info)
        session_factory = context["session_factory"]
        db_semaphore = context["db_semaphore"]
        async with db_semaphore, session_factory() as db:
            result = await db.scalars(
                select(CaseDeviceModel).where(
                    tuple_(
                        CaseDeviceModel.case_id,
                        CaseDeviceModel.device_id,
                        CaseDeviceModel.assigned_from,
                    ).in_(keys)
                )
            )
            entities_by_key: dict[tuple[UUID, UUID, datetime], DeviceAssignment] = {
                (entity.case_id, entity.device_id, to_utc(entity.assigned_from)): cast(DeviceAssignment, entity)
                for entity in result
            }

        resolved_nodes: list[DeviceAssignment | None] = []
        for raw_node_id, parsed_node_id in zip(raw_node_ids, parsed_node_ids, strict=True):
            if parsed_node_id is None:
                resolved_nodes.append(None)
                continue
            resolved = entities_by_key.get(parsed_node_id)
            if resolved is None and required:
                raise ValueError(f"{cls.__name__} node '{raw_node_id}' was not found.")
            resolved_nodes.append(resolved)
        return resolved_nodes

    @strawberry.field
    async def device(self, info: strawberry.Info) -> Device | None:
        loaders: Loaders = context_from_info(info)["loaders"]
        return await loaders.device_by_id.load(self.device_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Case | None:
        loaders: Loaders = context_from_info(info)["loaders"]
        return await loaders.case_by_id.load(self.case_id)


@strawberry.type
class WearableAssignment(relay.Node):
    id: relay.NodeID[str]
    case_id: UUID
    wearable_id: UUID
    assigned_from: datetime
    assigned_to: datetime | None

    @classmethod
    def resolve_id(cls, root: Any, *, info: strawberry.Info) -> str:
        return _encode_assignment_node_id(root.case_id, root.wearable_id, root.assigned_from)

    @classmethod
    async def resolve_nodes(cls, info: strawberry.Info, node_ids: Iterable[str], required: bool = False) -> Any:
        raw_node_ids = list(node_ids)
        parsed_node_ids: list[tuple[UUID, UUID, datetime] | None] = []
        for node_id in raw_node_ids:
            try:
                parsed_node_ids.append(_decode_assignment_node_id(node_id))
            except ValueError:
                if required:
                    raise ValueError(f"Invalid {cls.__name__} node id '{node_id}'.") from None
                parsed_node_ids.append(None)

        keys = [key for key in parsed_node_ids if key is not None]
        if not keys:
            return [None for _ in raw_node_ids]

        context = context_from_info(info)
        session_factory = context["session_factory"]
        db_semaphore = context["db_semaphore"]
        async with db_semaphore, session_factory() as db:
            result = await db.scalars(
                select(CaseWearableModel).where(
                    tuple_(
                        CaseWearableModel.case_id,
                        CaseWearableModel.wearable_id,
                        CaseWearableModel.assigned_from,
                    ).in_(keys)
                )
            )
            entities_by_key: dict[tuple[UUID, UUID, datetime], WearableAssignment] = {
                (entity.case_id, entity.wearable_id, to_utc(entity.assigned_from)): cast(WearableAssignment, entity)
                for entity in result
            }

        resolved_nodes: list[WearableAssignment | None] = []
        for raw_node_id, parsed_node_id in zip(raw_node_ids, parsed_node_ids, strict=True):
            if parsed_node_id is None:
                resolved_nodes.append(None)
                continue
            resolved = entities_by_key.get(parsed_node_id)
            if resolved is None and required:
                raise ValueError(f"{cls.__name__} node '{raw_node_id}' was not found.")
            resolved_nodes.append(resolved)
        return resolved_nodes

    @strawberry.field
    async def wearable(self, info: strawberry.Info) -> Wearable | None:
        loaders: Loaders = context_from_info(info)["loaders"]
        return await loaders.wearable_by_id.load(self.wearable_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Case | None:
        loaders: Loaders = context_from_info(info)["loaders"]
        return await loaders.case_by_id.load(self.case_id)


@strawberry.type
class Case(UuidRelayNodeMixin, relay.Node):
    _relay_model = CaseModel

    id: relay.NodeID[UUID]
    status: CaseStatus
    patient_id: UUID

    @strawberry.field
    async def patient(self, info: strawberry.Info) -> Patient | None:
        loaders: Loaders = context_from_info(info)["loaders"]
        return await loaders.patient_by_id.load(self.patient_id)

    @relay.connection(NestedKeysetConnection[Device], description="Relay connection for active case devices.")
    async def devices(self) -> Iterable[Device]:
        return NestedConnectionSource(
            NestedConnectionField.CASE_DEVICES,
            self.id,
            Device,
        )

    @relay.connection(
        NestedKeysetConnection[DeviceAssignment],
        description="Relay connection for case device assignments.",
    )
    async def device_assignments(self) -> Iterable[DeviceAssignment]:
        return NestedConnectionSource(
            NestedConnectionField.CASE_DEVICE_ASSIGNMENTS,
            self.id,
            DeviceAssignment,
        )

    @relay.connection(NestedKeysetConnection[Wearable], description="Relay connection for active case wearables.")
    async def wearables(self) -> Iterable[Wearable]:
        return NestedConnectionSource(
            NestedConnectionField.CASE_WEARABLES,
            self.id,
            Wearable,
        )

    @relay.connection(
        NestedKeysetConnection[WearableAssignment], description="Relay connection for case wearable assignments."
    )
    async def wearable_assignments(self) -> Iterable[WearableAssignment]:
        return NestedConnectionSource(
            NestedConnectionField.CASE_WEARABLE_ASSIGNMENTS,
            self.id,
            WearableAssignment,
        )

    @relay.connection(NestedKeysetConnection[Context], description="Relay connection for case contexts.")
    async def contexts(self) -> Iterable[Context]:
        return NestedConnectionSource(
            NestedConnectionField.CASE_CONTEXTS,
            self.id,
            Context,
        )


@strawberry.type(description="One structured telemetry item grouped by timestamp, measurement, and tag set.")
class TelemetryPoint:
    timestamp: datetime = strawberry.field(description="Timestamp of the grouped telemetry item.")
    measurement: str = strawberry.field(description="Influx measurement name.")
    tags: TelemetryRecordTags = strawberry.field(
        graphql_type=strawberry.scalars.JSON,
        description="Influx tags present on the grouped item.",
    )
    fields: JsonObject = strawberry.field(
        graphql_type=strawberry.scalars.JSON,
        description="Field values grouped into one item.",
    )


@strawberry.type(description="One raw telemetry row from InfluxDB.")
class RawTelemetryPoint:
    timestamp: datetime | None = strawberry.field(description="Timestamp of the raw telemetry row.")
    measurement: str | None = strawberry.field(description="Influx measurement name.")
    field: str | None = strawberry.field(description="Influx field key for this raw row.")
    value: JsonValue = strawberry.field(
        graphql_type=strawberry.scalars.JSON,
        description="Raw field value.",
    )
    tags: TelemetryRecordTags = strawberry.field(
        graphql_type=strawberry.scalars.JSON,
        description="Influx tags present on the raw row.",
    )


@strawberry.type(description="Optional relational metadata resolved from cross-database telemetry filters.")
class TelemetryResolvedMetadata:
    patients: list[Patient]
    cases: list[Case]
    devices: list[Device]
    wearables: list[Wearable]
    contexts: list[Context]
    mappings: list[FHIRMapping]
    dot_dependency_files: list[DotDependencyFile]


@strawberry.type(description="Influx tag metadata for one measurement tag key.")
class InfluxTagIntrospection:
    key: str
    values: list[str]


@strawberry.type(description="Influx measurement metadata including tag and field keys.")
class InfluxMeasurementIntrospection:
    measurement: str
    tag_keys: list[str]
    field_keys: list[str]
    tags: list[InfluxTagIntrospection]


@strawberry.type(description="Influx bucket introspection result.")
class InfluxDbIntrospection:
    bucket: str
    measurements: list[InfluxMeasurementIntrospection]


@strawberry.type(description="Structured telemetry window result.")
class TelemetryWindow:
    items: list[TelemetryPoint] = strawberry.field(description="Structured telemetry items in this window.")
    has_more: bool = strawberry.field(description="Whether older matching telemetry exists beyond this window.")
    next_end: datetime | None = strawberry.field(
        description="Exclusive end timestamp to use for the next older window request."
    )
    resolved: TelemetryResolvedMetadata | None = strawberry.field(
        default=None,
        description="Optional relational entities resolved from GraphQL cross-database filters.",
    )


@strawberry.type(description="Raw telemetry window result.")
class RawTelemetryWindow:
    items: list[RawTelemetryPoint] = strawberry.field(description="Raw telemetry rows in this window.")
    has_more: bool = strawberry.field(description="Whether older matching raw rows exist beyond this window.")
    next_end: datetime | None = strawberry.field(
        description="Exclusive end timestamp to use for the next older window request."
    )
    resolved: TelemetryResolvedMetadata | None = strawberry.field(
        default=None,
        description="Optional relational entities resolved from GraphQL cross-database filters.",
    )
