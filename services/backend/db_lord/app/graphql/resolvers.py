from __future__ import annotations

from asyncio import Semaphore
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from typing import TYPE_CHECKING, Any
from uuid import UUID

import strawberry
import strawberry.relay as relay
from sqlalchemy import literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry.types.cast import cast as strawberry_cast
from strawberry.types.maybe import Some

from app.core.config import settings
from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import DotDependencyFile as DotDependencyFileModel
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

if TYPE_CHECKING:
    from app.db.influx.repos.telemetry_repo import TelemetryRepo


def _session_context(info: strawberry.Info) -> tuple[async_sessionmaker[AsyncSession], Semaphore]:
    return info.context["session_factory"], info.context["db_semaphore"]


async def _with_db[TDbResult](info: strawberry.Info, fn: Callable[[AsyncSession], Awaitable[TDbResult]]) -> TDbResult:
    session_factory, db_semaphore = _session_context(info)
    async with db_semaphore, session_factory() as db:
        return await fn(db)


def _keyset_source[TGraphQL](
    info: strawberry.Info, model: type[Any], graphql_type: type[TGraphQL], filter_input: FilterInput | None
) -> KeysetSource[TGraphQL]:
    session_factory, db_semaphore = _session_context(info)
    return KeysetSource(session_factory, db_semaphore, model, graphql_type, apply_filter(model, filter_input))


def _merge_tag_filter(tags: dict[str, str | list[str]], key: str, incoming: str | list[str]) -> None:
    existing = tags.get(key)
    if existing is None:
        tags[key] = incoming
        return

    existing_values = existing if isinstance(existing, list) else [existing]
    incoming_values = incoming if isinstance(incoming, list) else [incoming]
    tags[key] = list(dict.fromkeys([*existing_values, *incoming_values]))


def _normalize_bucket(bucket: str | None) -> str:
    normalized = settings.INFLUX_BUCKET if bucket is None else bucket.strip()
    if not normalized:
        raise ValueError("bucket must be a non-empty string when provided.")
    return normalized


def _enforce_telemetry_fanout_limits(ids_by_key: dict[str, list[str]]) -> dict[str, list[str]]:
    max_per_tag = max(1, settings.TELEMETRY_MAX_IDS_PER_TAG)
    max_total = max(1, settings.TELEMETRY_MAX_TOTAL_IDS)

    normalized: dict[str, list[str]] = {}
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


async def _build_resolved_metadata(db: AsyncSession, ids_by_key: dict[str, list[str]]) -> TelemetryResolvedMetadata:
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

    ids_by_key = _enforce_telemetry_fanout_limits(await _resolve_entity_ids_bulk(db, active_tag_filter_specs))
    for tag_key, _, _ in active_tag_filter_specs:
        ids = ids_by_key.get(tag_key, [])
        if not ids:
            return tags, ids_by_key, False
        _merge_tag_filter(tags, tag_key, ids)

    if query.codes:
        code_tag: str | list[str] = query.codes[0] if len(query.codes) == 1 else query.codes
        _merge_tag_filter(tags, "code", code_tag)

    return tags, ids_by_key, True


async def _build_influx_measurement_introspection(
    telemetry_repo: TelemetryRepo,
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

    @relay.connection(
        KeysetConnection[DotDependencyFileType],
        description="Query dot dependency files with filtering.",
    )
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
        telemetry_repo: TelemetryRepo = info.context["telemetry_repo"]
        bucket_name = _normalize_bucket(bucket)
        if measurement is not None and measurement.strip() == "":
            raise ValueError("measurement must be a non-empty string when provided.")
        if tag_value_limit is not None and tag_value_limit < 1:
            raise ValueError("tag_value_limit must be >= 1 when provided.")

        measurement_names = (
            [measurement] if measurement is not None else await telemetry_repo.list_measurements(bucket=bucket_name)
        )
        measurements = [
            await _build_influx_measurement_introspection(
                telemetry_repo,
                bucket_name,
                measurement_name,
                include_tag_values=include_tag_values,
                tag_value_limit=tag_value_limit,
            )
            for measurement_name in measurement_names
        ]
        return InfluxDbIntrospection(bucket=bucket_name, measurements=measurements)

    @strawberry.field(description="Query telemetry data from InfluxDB.")
    async def telemetry(self, info: strawberry.Info, query: TelemetryQueryInput) -> TelemetryPage:
        telemetry_repo: TelemetryRepo = info.context["telemetry_repo"]
        bucket_name = _normalize_bucket(query.bucket)

        async def _resolve_inputs(
            db: AsyncSession,
        ) -> tuple[dict[str, str | list[str]], bool, TelemetryResolvedMetadata | None]:
            tags, ids_by_key, has_results = await _prepare_telemetry_filters(db, query)
            resolved_metadata = (
                await _build_resolved_metadata(db, ids_by_key) if query.include_resolved_metadata else None
            )
            return tags, has_results, resolved_metadata

        tags, has_results, resolved_metadata = await _with_db(info, _resolve_inputs)
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
        telemetry_repo: TelemetryRepo = info.context["telemetry_repo"]
        bucket_name = _normalize_bucket(query.bucket)

        tags, _, has_results = await _with_db(info, lambda db: _prepare_telemetry_filters(db, query))
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
