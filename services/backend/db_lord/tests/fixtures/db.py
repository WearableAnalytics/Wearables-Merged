from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid7

import pytest
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from alembic import command
from app.db.postgres.orm import Base


@compiles(ExcludeConstraint, "sqlite")
def _compile_exclude_constraint_sqlite(_element, _compiler, **_kw):
    """SQLite has no EXCLUDE constraints -> compile to a no op check for unit tests."""
    return "CHECK (1)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    """Compile JSONB to JSON for SQLite."""
    return "JSON"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def async_engine():
    """Create an in-memory SQLite async engine for unit testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record):
        # SQLAlchemy docs recommend explicit transaction control for sqlite/aiosqlite
        # when relying on savepoint heavy patterns in tests.
        dbapi_connection.isolation_level = None
        dbapi_connection.create_function("uuidv7", 0, lambda: str(uuid7()))
        dbapi_connection.create_function(
            "clock_timestamp",
            0,
            lambda: datetime.now(UTC).isoformat(timespec="microseconds"),
        )
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def set_sqlite_begin(conn):
        conn.exec_driver_sql("BEGIN")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession]:
    """Create a database session for unit testing."""
    async with async_engine.connect() as connection:
        outer_transaction = await connection.begin()
        async_session_maker = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )

        async with async_session_maker() as session:
            yield session

        if outer_transaction.is_active:
            await outer_transaction.rollback()


@pytest.fixture(scope="session")
def postgres_container():
    """Start a Postgre container for integration tests."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:18", driver="asyncpg") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def integration_engine_sync(postgres_container):
    """Get sync connection URL for real Postgre container."""
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def integration_db_schema(integration_engine_sync) -> None:
    """Apply integration schema once per test session via Alembic."""
    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", integration_engine_sync)
    command.upgrade(alembic_cfg, "head")


@pytest.fixture
async def integration_engine(integration_engine_sync, integration_db_schema):
    """Create async engine connected to real Postgre container."""
    engine = create_async_engine(
        integration_engine_sync,
        echo=False,
        pool_pre_ping=True,
    )

    yield engine

    await engine.dispose()


@pytest.fixture
async def integration_db_session(integration_engine) -> AsyncGenerator[AsyncSession]:
    """Create a database session for integration testing with real Postgre container."""
    async with integration_engine.connect() as connection:
        outer_transaction = await connection.begin()
        async_session_maker = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )

        async with async_session_maker() as session:
            yield session

        if outer_transaction.is_active:
            await outer_transaction.rollback()
