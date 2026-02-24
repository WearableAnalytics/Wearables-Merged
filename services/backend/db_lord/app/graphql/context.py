from __future__ import annotations

from asyncio import Semaphore
from collections.abc import AsyncIterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, TypedDict, cast

import strawberry
from fastapi import Request
from fastapi_pagination.types import Cursor
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

if TYPE_CHECKING:
    from app.db.influx.repos.telemetry_repo import MeasurementSchema, TelemetryPage
    from app.graphql.dataloaders import Loaders
    from app.telemetry.types import TelemetryTags


class GraphQLTelemetryRepo(Protocol):
    def resolve_bucket(self, bucket: str | None) -> str: ...

    async def list_measurements(self, *, bucket: str | None = None) -> list[str]: ...

    async def describe_measurement(self, measurement: str, *, bucket: str | None = None) -> MeasurementSchema: ...

    async def get_measurement_tag_values(
        self,
        measurement: str,
        tag_key: str,
        *,
        limit: int | None = 500,
        bucket: str | None = None,
    ) -> list[str]: ...

    async def get_points(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
        bucket: str | None = None,
    ) -> TelemetryPage: ...

    def stream_points(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        page_size: int = 100,
        cursor: Cursor | None = None,
        bucket: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]: ...


class GraphQLContext(TypedDict):
    request: Request | None
    session_factory: async_sessionmaker[AsyncSession]
    db_semaphore: Semaphore
    loaders: Loaders | None
    telemetry_repo: GraphQLTelemetryRepo


def context_from_info(info: strawberry.Info) -> GraphQLContext:
    return cast(GraphQLContext, info.context)
