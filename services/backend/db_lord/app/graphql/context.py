from asyncio import Semaphore
from typing import TYPE_CHECKING, TypedDict

import strawberry
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.telemetry_service import TelemetryService

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders


class GraphQLContext(TypedDict):
    request: Request | None
    session_factory: async_sessionmaker[AsyncSession]
    db_semaphore: Semaphore
    loaders: Loaders
    telemetry_service: TelemetryService


def context_from_info(info: strawberry.Info) -> GraphQLContext:
    return info.context
