from asyncio import Semaphore
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import strawberry
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry.fastapi import BaseContext

from app.services.telemetry_service import TelemetryService

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders


class GraphQLContext(BaseContext):
    session_factory: async_sessionmaker[AsyncSession]
    db_semaphore: Semaphore
    loaders: Loaders
    telemetry_service: TelemetryService

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        db_semaphore: Semaphore,
        loaders: Loaders,
        telemetry_service: TelemetryService,
        request: Request | None = None,
    ) -> None:
        super().__init__()
        self.request = request
        self.session_factory = session_factory
        self.db_semaphore = db_semaphore
        self.loaders = loaders
        self.telemetry_service = telemetry_service

    @asynccontextmanager
    async def db_session(self) -> AsyncIterator[AsyncSession]:
        async with self.db_semaphore, self.session_factory() as db:
            yield db


def context_from_info(info: strawberry.Info) -> GraphQLContext:
    context = info.context
    if not isinstance(context, GraphQLContext):
        raise TypeError("GraphQL context must be GraphQLContext.")
    return context
