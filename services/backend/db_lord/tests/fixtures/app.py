import asyncio
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.graphql.context import GraphQLContext


def _configure_test_app(main_app: FastAPI, db_session: AsyncSession, influx_client: InfluxDBClientAsync) -> None:
    from app.api.dependencies import get_db, get_graphql_context
    from app.db.influx.telemetry import TelemetryRepo
    from app.graphql.dataloaders import Loaders
    from app.services.telemetry_service import TelemetryService

    bind = db_session.bind
    if bind is None:
        raise RuntimeError("Test db_session is not bound to an engine.")

    telemetry_service = TelemetryService(TelemetryRepo(influx_client))
    session_factory = async_sessionmaker(
        bind=bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    db_semaphore = asyncio.Semaphore(1)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
            finally:
                if session.in_transaction():
                    await session.rollback()

    async def override_graphql_context(request: Request) -> GraphQLContext:
        return GraphQLContext(
            request=request,
            session_factory=session_factory,
            db_semaphore=db_semaphore,
            loaders=Loaders(session_factory, db_semaphore),
            telemetry_service=telemetry_service,
        )

    main_app.dependency_overrides[get_db] = override_get_db
    main_app.dependency_overrides[get_graphql_context] = override_graphql_context
    main_app.state.influx_client = influx_client
    main_app.state.telemetry_service = telemetry_service


@pytest.fixture
async def app(db_session: AsyncSession, mock_influx_client) -> AsyncGenerator[FastAPI]:
    """Create a FastAPI app with test dependencies."""
    from app.main import create_app

    main_app = create_app()
    _configure_test_app(main_app, db_session, mock_influx_client)

    yield main_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async HTTP test client."""
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://test") as ac,
    ):
        yield ac


@pytest.fixture
async def integration_app(integration_db_session: AsyncSession, integration_influx_client) -> AsyncGenerator[FastAPI]:
    """Create a FastAPI app with real database connections for integration tests."""
    from app.main import create_app

    main_app = create_app()
    _configure_test_app(main_app, integration_db_session, integration_influx_client)

    yield main_app


@pytest.fixture
async def integration_client(integration_app: FastAPI) -> AsyncGenerator[AsyncClient]:
    """Create an async HTTP test client connected to real databases."""
    async with (
        integration_app.router.lifespan_context(integration_app),
        AsyncClient(transport=ASGITransport(integration_app), base_url="http://test") as ac,
    ):
        yield ac
