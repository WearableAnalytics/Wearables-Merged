from __future__ import annotations

from collections.abc import AsyncGenerator, Iterable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import strawberry
import strawberry.relay as relay
from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.types.cast import cast as strawberry_cast
from strawberry.types.maybe import Some

from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import FHIRMapping as FHIRMappingModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel
from app.graphql.filter_builder import apply_filter
from app.graphql.inputs import FilterInput, TelemetryQueryInput
from app.graphql.keyset_connection import KeysetConnection, KeysetSource
from app.graphql.types import (
    Case,
    Context,
    Device,
    Patient,
    TelemetryPage,
    TelemetryPoint,
    TelemetryResolvedMetadata,
    Wearable,
)
from app.graphql.types import (
    FHIRMapping as FHIRMappingType,
)

if TYPE_CHECKING:
    from app.db.influx.repos.telemetry_repo import TelemetryRepo


def _keyset_source[TGraphQL](
    db: AsyncSession, model: type[Any], graphql_type: type[TGraphQL], filter_input: FilterInput | None
) -> KeysetSource[TGraphQL]:
    return KeysetSource(db, model, graphql_type, apply_filter(model, filter_input))


async def _get_entity[TGraphQL](
    db: AsyncSession, model: type, graphql_type: type[TGraphQL], entity_id: UUID
) -> TGraphQL | None:
    result = await db.execute(select(model).where(model.id == entity_id))
    entity = result.scalar_one_or_none()
    return strawberry_cast(graphql_type, entity) if entity else None


def _merge_tag_filter(tags: dict[str, str | list[str]], key: str, incoming: str | list[str]) -> None:
    existing = tags.get(key)
    if existing is None:
        tags[key] = incoming
        return

    existing_values = existing if isinstance(existing, list) else [existing]
    incoming_values = incoming if isinstance(incoming, list) else [incoming]
    tags[key] = list(dict.fromkeys([*existing_values, *incoming_values]))


async def _resolve_entity_ids_bulk(
    db: AsyncSession, specs: list[tuple[str, type[Any], FilterInput]]
) -> dict[str, list[str]]:
    tagged_selects = []
    for tag_key, model, filter_input in specs:
        stmt = select(
            literal(tag_key).label("tag_key"),
            model.id.label("entity_id"),
        )
        where_clause = apply_filter(model, filter_input)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        tagged_selects.append(stmt)

    if not tagged_selects:
        return {}

    combined_query = tagged_selects[0] if len(tagged_selects) == 1 else union_all(*tagged_selects)

    result = await db.execute(combined_query)
    grouped: dict[str, list[str]] = {}
    for tag_key, entity_id in result.all():
        grouped.setdefault(str(tag_key), []).append(str(entity_id))
    return grouped


async def _load_entities_by_ids[TGraphQL](
    db: AsyncSession, model: type[Any], graphql_type: type[TGraphQL], entity_ids: list[str]
) -> list[TGraphQL]:
    unique_ids = _normalize_unique_uuid_ids(entity_ids)
    if not unique_ids:
        return []

    result = await db.execute(select(model).where(model.id.in_(unique_ids)))
    entities = {str(entity.id): strawberry_cast(graphql_type, entity) for entity in result.scalars().all()}
    return [entities[str(entity_id)] for entity_id in unique_ids if str(entity_id) in entities]


def _normalize_unique_uuid_ids(entity_ids: list[str]) -> list[UUID]:
    unique_ids: list[UUID] = []
    seen: set[UUID] = set()
    for entity_id in entity_ids:
        try:
            parsed = UUID(entity_id)
        except ValueError:
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        unique_ids.append(parsed)
    return unique_ids


async def _load_mappings_by_ids(db: AsyncSession, entity_ids: list[str]) -> list[FHIRMappingType]:
    unique_ids = _normalize_unique_uuid_ids(entity_ids)
    if not unique_ids:
        return []

    result = await db.execute(select(FHIRMappingModel).where(FHIRMappingModel.id.in_(unique_ids)))
    mappings_by_id = {
        str(mapping.id): FHIRMappingType(
            id=mapping.id,
            version=mapping.version,
            full_mapping=mapping.full_mapping,
        )
        for mapping in result.scalars().all()
    }
    return [mappings_by_id[str(entity_id)] for entity_id in unique_ids if str(entity_id) in mappings_by_id]


async def _build_resolved_metadata(db: AsyncSession, ids_by_key: dict[str, list[str]]) -> TelemetryResolvedMetadata:
    return TelemetryResolvedMetadata(
        patients=await _load_entities_by_ids(db, PatientModel, Patient, ids_by_key.get("patient_id", [])),
        cases=await _load_entities_by_ids(db, CaseModel, Case, ids_by_key.get("case_id", [])),
        devices=await _load_entities_by_ids(db, DeviceModel, Device, ids_by_key.get("device_id", [])),
        wearables=await _load_entities_by_ids(db, WearableModel, Wearable, ids_by_key.get("wearable_id", [])),
        contexts=await _load_entities_by_ids(db, ContextModel, Context, ids_by_key.get("context_id", [])),
        mappings=await _load_mappings_by_ids(db, ids_by_key.get("mapping_id", [])),
    )


def _telemetry_point_from_item(item: dict[str, Any]) -> TelemetryPoint:
    return TelemetryPoint(
        timestamp=item["timestamp"],
        measurement=item["measurement"],
        patient_id=item["patient_id"],
        device_id=item["device_id"],
        wearable_id=item["wearable_id"],
        case_id=item["case_id"],
        mapping_id=item["mapping_id"],
        code=item["code"],
        context_id=item.get("context_id"),
        other_tags=item.get("other_tags", {}),
        fields=item.get("fields", {}),
    )


async def _prepare_telemetry_filters(
    db: AsyncSession, query: TelemetryQueryInput
) -> tuple[dict[str, str | list[str]], dict[str, list[str]], bool]:
    tags: dict[str, str | list[str]] = {}

    if query.tags:
        for tag in query.tags:
            if isinstance(tag.match.values, Some):
                if len(tag.match.values.value) == 0:
                    raise ValueError(f"Tag '{tag.key}' 'values' must not be empty")
                _merge_tag_filter(tags, tag.key, tag.match.values.value)
            else:
                _merge_tag_filter(tags, tag.key, tag.match.value.value)

    tag_filter_specs: list[tuple[str, type[Any], FilterInput | None]] = [
        ("patient_id", PatientModel, query.patient_filter),
        ("case_id", CaseModel, query.case_filter),
        ("device_id", DeviceModel, query.device_filter),
        ("wearable_id", WearableModel, query.wearable_filter),
        ("context_id", ContextModel, query.context_filter),
        ("mapping_id", FHIRMappingModel, query.mapping_filter),
    ]
    active_tag_filter_specs: list[tuple[str, type[Any], FilterInput]] = [
        (tag_key, model, filter_input) for tag_key, model, filter_input in tag_filter_specs if filter_input is not None
    ]

    ids_by_key = await _resolve_entity_ids_bulk(db, active_tag_filter_specs)
    for tag_key, _, _ in active_tag_filter_specs:
        ids = ids_by_key.get(tag_key, [])
        if not ids:
            return tags, ids_by_key, False
        _merge_tag_filter(tags, tag_key, ids)

    if query.codes:
        code_tag: str | list[str] = query.codes[0] if len(query.codes) == 1 else query.codes
        _merge_tag_filter(tags, "code", code_tag)

    return tags, ids_by_key, True


@strawberry.type
class Query:
    @relay.connection(KeysetConnection[Patient], description="Query patients with filtering.")
    async def patients(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Patient]:
        db: AsyncSession = info.context["db"]
        return _keyset_source(db, PatientModel, Patient, filter)

    @strawberry.field(description="Get a single patient by ID.")
    async def patient(self, info: strawberry.Info, id: UUID) -> Patient | None:
        db: AsyncSession = info.context["db"]
        return await _get_entity(db, PatientModel, Patient, id)

    @relay.connection(KeysetConnection[Case], description="Query cases with filtering.")
    async def cases(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Case]:
        db: AsyncSession = info.context["db"]
        return _keyset_source(db, CaseModel, Case, filter)

    @strawberry.field(description="Get a single case by ID.")
    async def case(self, info: strawberry.Info, id: UUID) -> Case | None:
        db: AsyncSession = info.context["db"]
        return await _get_entity(db, CaseModel, Case, id)

    @relay.connection(KeysetConnection[Device], description="Query devices with filtering.")
    async def devices(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Device]:
        db: AsyncSession = info.context["db"]
        return _keyset_source(db, DeviceModel, Device, filter)

    @strawberry.field(description="Get a single device by ID.")
    async def device(self, info: strawberry.Info, id: UUID) -> Device | None:
        db: AsyncSession = info.context["db"]
        return await _get_entity(db, DeviceModel, Device, id)

    @relay.connection(KeysetConnection[Wearable], description="Query wearables with filtering.")
    async def wearables(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Wearable]:
        db: AsyncSession = info.context["db"]
        return _keyset_source(db, WearableModel, Wearable, filter)

    @strawberry.field(description="Get a single wearable by ID.")
    async def wearable(self, info: strawberry.Info, id: UUID) -> Wearable | None:
        db: AsyncSession = info.context["db"]
        return await _get_entity(db, WearableModel, Wearable, id)

    @relay.connection(KeysetConnection[Context], description="Query contexts with filtering.")
    async def contexts(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Context]:
        db: AsyncSession = info.context["db"]
        return _keyset_source(db, ContextModel, Context, filter)

    @strawberry.field(description="Get a single context by ID.")
    async def context(self, info: strawberry.Info, id: UUID) -> Context | None:
        db: AsyncSession = info.context["db"]
        return await _get_entity(db, ContextModel, Context, id)

    @strawberry.field(description="Query telemetry data from InfluxDB.")
    async def telemetry(self, info: strawberry.Info, query: TelemetryQueryInput) -> TelemetryPage:
        db: AsyncSession = info.context["db"]
        telemetry_repo: TelemetryRepo = info.context["telemetry_repo"]

        tags, ids_by_key, has_results = await _prepare_telemetry_filters(db, query)
        if not has_results:
            resolved_metadata = (
                await _build_resolved_metadata(db, ids_by_key) if query.include_resolved_metadata else None
            )
            return TelemetryPage(items=[], next_cursor=None, resolved=resolved_metadata)

        result = await telemetry_repo.get_points(
            measurement=query.measurement,
            start=query.start,
            end=query.end,
            tags=tags or None,
            fields=query.fields,
            page_size=query.page_size,
            cursor=query.cursor,
        )

        items = [_telemetry_point_from_item(item) for item in result.items]

        resolved_metadata = await _build_resolved_metadata(db, ids_by_key) if query.include_resolved_metadata else None
        return TelemetryPage(items=items, next_cursor=result.next_cursor, resolved=resolved_metadata)


@strawberry.type
class Subscription:
    @strawberry.subscription(description=("Stream telemetry points one by one from InfluxDB."))
    async def telemetry_stream(
        self, info: strawberry.Info, query: TelemetryQueryInput
    ) -> AsyncGenerator[TelemetryPoint]:
        db: AsyncSession = info.context["db"]
        telemetry_repo: TelemetryRepo = info.context["telemetry_repo"]

        tags, _, has_results = await _prepare_telemetry_filters(db, query)
        if not has_results:
            return

        async for item in telemetry_repo.stream_points(
            measurement=query.measurement,
            start=query.start,
            end=query.end,
            tags=tags or None,
            fields=query.fields,
            page_size=query.page_size,
            cursor=query.cursor,
        ):
            yield _telemetry_point_from_item(item)
