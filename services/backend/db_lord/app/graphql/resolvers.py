from __future__ import annotations

import asyncio
from asyncio import Semaphore
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from typing import Any
from uuid import UUID

import strawberry
import strawberry.relay as relay
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry import cast as strawberry_cast
from strawberry.types.maybe import Some

from app.core.config import settings
from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import DotDependencyFile as DotDependencyFileModel
from app.db.postgres.orm import FHIRMapping as FHIRMappingModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel
from app.graphql.context import GraphQLTelemetryRepo, context_from_info
from app.graphql.filter_builder import apply_filter
from app.graphql.inputs import FilterInput, TelemetryQueryInput
from app.graphql.keyset_connection import KeysetConnection, KeysetSource
from app.graphql.types import (
    Case,
    Context,
    Device,
    InfluxDbIntrospection,
    InfluxMeasurementIntrospection,
    InfluxTagIntrospection,
    Patient,
    TelemetryPage,
    TelemetryPoint,
    TelemetryResolvedMetadata,
    Wearable,
)
from app.graphql.types import (
    DotDependencyFile as DotDependencyFileType,
)
from app.graphql.types import (
    FHIRMapping as FHIRMappingType,
)
from app.telemetry.tag_filters import merge_tag_filter
from app.telemetry.types import TelemetryTags

_UUID_ADAPTER = TypeAdapter(UUID)


def _session_context(info: strawberry.Info) -> tuple[async_sessionmaker[AsyncSession], Semaphore]:
    context = context_from_info(info)
    return context["session_factory"], context["db_semaphore"]


async def _with_db[TDbResult](info: strawberry.Info, fn: Callable[[AsyncSession], Awaitable[TDbResult]]) -> TDbResult:
    session_factory, db_semaphore = _session_context(info)
    async with db_semaphore, session_factory() as db:
        return await fn(db)


def _keyset_source[TGraphQL](
    info: strawberry.Info, model: type[Any], graphql_type: type[TGraphQL], filter_input: FilterInput | None
) -> KeysetSource[TGraphQL]:
    session_factory, db_semaphore = _session_context(info)
    return KeysetSource(session_factory, db_semaphore, model, graphql_type, apply_filter(model, filter_input))


def _enforce_telemetry_fanout_limits[TId](ids_by_key: dict[str, list[TId]]) -> dict[str, list[TId]]:
    max_per_tag = max(1, settings.TELEMETRY_MAX_IDS_PER_TAG)
    max_total = max(1, settings.TELEMETRY_MAX_TOTAL_IDS)

    normalized: dict[str, list[TId]] = {}
    total = 0
    for tag_key, entity_ids in ids_by_key.items():
        deduped = list(dict.fromkeys(entity_ids))
        count = len(deduped)
        if count > max_per_tag:
            raise ValueError(
                f"Telemetry filter '{tag_key}' resolved to {count} IDs, "
                f"which exceeds TELEMETRY_MAX_IDS_PER_TAG={max_per_tag}."
            )
        total += count
        normalized[tag_key] = deduped

    if total > max_total:
        raise ValueError(
            f"Telemetry filters resolved to {total} IDs in total, which exceeds TELEMETRY_MAX_TOTAL_IDS={max_total}."
        )

    return normalized


async def _resolve_entity_ids_bulk(
    db: AsyncSession, specs: list[tuple[str, type[Any], FilterInput]]
) -> dict[str, list[UUID]]:
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
    grouped: dict[str, list[UUID]] = {}
    for tag_key, entity_id in result.all():
        try:
            parsed_id = _UUID_ADAPTER.validate_python(entity_id)
        except ValidationError:
            continue
        grouped.setdefault(str(tag_key), []).append(parsed_id)
    return grouped


async def _load_entities_by_ids[TGraphQL](
    db: AsyncSession, model: type[Any], graphql_type: type[TGraphQL], entity_ids: list[UUID]
) -> list[TGraphQL]:
    unique_ids = list(dict.fromkeys(entity_ids))
    if not unique_ids:
        empty: list[TGraphQL] = []
        return empty

    entities_result = await db.scalars(select(model).where(model.id.in_(unique_ids)))
    entities = {entity.id: strawberry_cast(graphql_type, entity) for entity in entities_result}
    resolved_entities: list[TGraphQL] = []
    for entity_id in unique_ids:
        entity = entities.get(entity_id)
        if entity is not None:
            resolved_entities.append(entity)
    return resolved_entities


async def _build_resolved_metadata(db: AsyncSession, ids_by_key: dict[str, list[UUID]]) -> TelemetryResolvedMetadata:
    return TelemetryResolvedMetadata(
        patients=await _load_entities_by_ids(db, PatientModel, Patient, ids_by_key.get("patient_id", [])),
        cases=await _load_entities_by_ids(db, CaseModel, Case, ids_by_key.get("case_id", [])),
        devices=await _load_entities_by_ids(db, DeviceModel, Device, ids_by_key.get("device_id", [])),
        wearables=await _load_entities_by_ids(db, WearableModel, Wearable, ids_by_key.get("wearable_id", [])),
        contexts=await _load_entities_by_ids(db, ContextModel, Context, ids_by_key.get("context_id", [])),
        mappings=await _load_entities_by_ids(db, FHIRMappingModel, FHIRMappingType, ids_by_key.get("mapping_id", [])),
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
        dot_dependency_file_id=item["dot_dependency_file_id"],
        context_id=item.get("context_id"),
        other_tags=item.get("other_tags", {}),
        fields=item.get("fields", {}),
    )


async def _prepare_telemetry_filters(
    db: AsyncSession, query: TelemetryQueryInput
) -> tuple[TelemetryTags, dict[str, list[UUID]], bool]:
    tags: TelemetryTags = {}

    if query.tags:
        for tag in query.tags:
            if isinstance(tag.match.values, Some):
                if len(tag.match.values.value) == 0:
                    raise ValueError(f"Tag '{tag.key}' 'values' must not be empty")
                merge_tag_filter(tags, tag.key, tag.match.values.value)
            elif isinstance(tag.match.value, Some):
                merge_tag_filter(tags, tag.key, tag.match.value.value)
            else:
                raise ValueError(f"Tag '{tag.key}' must set either 'value' or 'values'.")

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

    ids_by_key = _enforce_telemetry_fanout_limits(await _resolve_entity_ids_bulk(db, active_tag_filter_specs))
    for tag_key, _, _ in active_tag_filter_specs:
        ids = ids_by_key.get(tag_key, [])
        if not ids:
            return tags, ids_by_key, False
        merge_tag_filter(tags, tag_key, [str(entity_id) for entity_id in ids])

    if query.dot_dependency_file_ids:
        merge_tag_filter(tags, "dot_dependency_file_id", query.dot_dependency_file_ids)

    return tags, ids_by_key, True


async def _resolve_telemetry_query_context(
    info: strawberry.Info,
    query: TelemetryQueryInput,
    *,
    include_resolved_metadata: bool,
) -> tuple[GraphQLTelemetryRepo, str, TelemetryTags, bool, TelemetryResolvedMetadata | None]:
    telemetry_repo: GraphQLTelemetryRepo = context_from_info(info)["telemetry_repo"]
    bucket_name = telemetry_repo.resolve_bucket(query.bucket)

    async def _resolve_inputs(
        db: AsyncSession,
    ) -> tuple[TelemetryTags, bool, TelemetryResolvedMetadata | None]:
        tags, ids_by_key, has_results = await _prepare_telemetry_filters(db, query)
        resolved_metadata = await _build_resolved_metadata(db, ids_by_key) if include_resolved_metadata else None
        return tags, has_results, resolved_metadata

    tags, has_results, resolved_metadata = await _with_db(info, _resolve_inputs)
    return telemetry_repo, bucket_name, tags, has_results, resolved_metadata


async def _build_influx_measurement_introspection(
    telemetry_repo: GraphQLTelemetryRepo,
    bucket: str,
    measurement: str,
    *,
    include_tag_values: bool,
    tag_value_limit: int | None,
) -> InfluxMeasurementIntrospection:
    schema = await telemetry_repo.describe_measurement(measurement, bucket=bucket)
    tags: list[InfluxTagIntrospection] = []
    for tag_key in schema.tag_keys:
        tag_values = (
            await telemetry_repo.get_measurement_tag_values(
                measurement,
                tag_key,
                limit=tag_value_limit,
                bucket=bucket,
            )
            if include_tag_values
            else []
        )
        tags.append(InfluxTagIntrospection(key=tag_key, values=tag_values))

    return InfluxMeasurementIntrospection(
        measurement=measurement,
        tag_keys=list(schema.tag_keys),
        field_keys=sorted(schema.field_keys),
        tags=tags,
    )


@strawberry.type
class Query:
    node: relay.Node | None = relay.node(description="Fetch an object by its Relay global ID.")

    @relay.connection(KeysetConnection[Patient], description="Query patients with filtering.")
    async def patients(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Patient]:
        return _keyset_source(info, PatientModel, Patient, filter)

    @relay.connection(KeysetConnection[Case], description="Query cases with filtering.")
    async def cases(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Case]:
        return _keyset_source(info, CaseModel, Case, filter)

    @relay.connection(KeysetConnection[Device], description="Query devices with filtering.")
    async def devices(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Device]:
        return _keyset_source(info, DeviceModel, Device, filter)

    @relay.connection(KeysetConnection[Wearable], description="Query wearables with filtering.")
    async def wearables(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Wearable]:
        return _keyset_source(info, WearableModel, Wearable, filter)

    @relay.connection(KeysetConnection[Context], description="Query contexts with filtering.")
    async def contexts(self, info: strawberry.Info, filter: FilterInput | None = None) -> Iterable[Context]:
        return _keyset_source(info, ContextModel, Context, filter)

    @relay.connection(KeysetConnection[FHIRMappingType], description="Query FHIR mappings with filtering.")
    async def fhir_mappings(
        self, info: strawberry.Info, filter: FilterInput | None = None
    ) -> Iterable[FHIRMappingType]:
        return _keyset_source(info, FHIRMappingModel, FHIRMappingType, filter)

    @relay.connection(KeysetConnection[DotDependencyFileType], description="Query dot dependency files with filtering.")
    async def dot_dependency_files(
        self, info: strawberry.Info, filter: FilterInput | None = None
    ) -> Iterable[DotDependencyFileType]:
        return _keyset_source(info, DotDependencyFileModel, DotDependencyFileType, filter)

    @strawberry.field(description="Introspect InfluxDB measurements, tag keys, field keys, and optional tag values.")
    async def influx_db_introspection(
        self,
        info: strawberry.Info,
        measurement: str | None = None,
        bucket: str | None = None,
        include_tag_values: bool = True,
        tag_value_limit: int | None = 500,
    ) -> InfluxDbIntrospection:
        telemetry_repo: GraphQLTelemetryRepo = context_from_info(info)["telemetry_repo"]
        bucket_name = telemetry_repo.resolve_bucket(bucket)
        if measurement is not None and measurement.strip() == "":
            raise ValueError("measurement must be a non-empty string when provided.")
        if tag_value_limit is not None and tag_value_limit < 1:
            raise ValueError("tag_value_limit must be >= 1 when provided.")

        measurement_names = (
            [measurement] if measurement is not None else await telemetry_repo.list_measurements(bucket=bucket_name)
        )
        measurements = await asyncio.gather(
            *(
                _build_influx_measurement_introspection(
                    telemetry_repo,
                    bucket_name,
                    measurement_name,
                    include_tag_values=include_tag_values,
                    tag_value_limit=tag_value_limit,
                )
                for measurement_name in measurement_names
            )
        )
        return InfluxDbIntrospection(bucket=bucket_name, measurements=list(measurements))

    @strawberry.field(description="Query telemetry data from InfluxDB.")
    async def telemetry(self, info: strawberry.Info, query: TelemetryQueryInput) -> TelemetryPage:
        telemetry_repo, bucket_name, tags, has_results, resolved_metadata = await _resolve_telemetry_query_context(
            info,
            query,
            include_resolved_metadata=query.include_resolved_metadata,
        )
        if not has_results:
            return TelemetryPage(items=[], next_cursor=None, resolved=resolved_metadata)

        result = await telemetry_repo.get_points(
            measurement=query.measurement,
            start=query.start,
            end=query.end,
            tags=tags or None,
            fields=query.fields,
            page_size=query.page_size,
            cursor=query.cursor,
            bucket=bucket_name,
        )

        items = [_telemetry_point_from_item(item) for item in result.items]
        return TelemetryPage(items=items, next_cursor=result.next_cursor, resolved=resolved_metadata)


@strawberry.type
class Subscription:
    @strawberry.subscription(description=("Stream telemetry points one by one from InfluxDB."))
    async def telemetry_stream(
        self, info: strawberry.Info, query: TelemetryQueryInput
    ) -> AsyncGenerator[TelemetryPoint]:
        telemetry_repo, bucket_name, tags, has_results, _ = await _resolve_telemetry_query_context(
            info,
            query,
            include_resolved_metadata=False,
        )
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
            bucket=bucket_name,
        ):
            yield _telemetry_point_from_item(item)
