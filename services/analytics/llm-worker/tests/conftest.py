import json
from collections.abc import Iterator
from datetime import date

import psycopg
import pytest
from psycopg_pool import ConnectionPool

from llm_worker import repository
from llm_worker.fake_llm import FakeLLM


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer("postgres:16-alpine", driver=None).start()
    except Exception as exc:
        pytest.skip(f"Docker is not available: {exc}")

    dsn = container.get_connection_url()
    with psycopg.connect(dsn, autocommit=True) as conn:
        repository.migrate(conn)
    yield dsn
    container.stop()


@pytest.fixture
def pool(postgres_dsn: str) -> Iterator[ConnectionPool]:
    with ConnectionPool(postgres_dsn, min_size=1, max_size=4, kwargs={"autocommit": True}) as pool:
        with pool.connection() as conn:
            conn.execute("TRUNCATE worker.suspicious_events RESTART IDENTITY")
        yield pool


@pytest.fixture
def conn(pool: ConnectionPool) -> Iterator[psycopg.Connection]:
    with pool.connection() as conn:
        yield conn


def add_event(
    conn: psycopg.Connection,
    patient_id: str = "p-001",
    night_date: date = date(2026, 3, 14),
    reasons: str = "rule:multi_signal",
    red_flag: bool = False,
    features: dict | None = None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO worker.suspicious_events (patient_id, night_date, reasons, red_flag, features)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING event_id
        """,
        (patient_id, night_date, reasons, red_flag, json.dumps(features or {"rhr_z": 2.4, "temp_z": 1.9})),
    ).fetchone()
    return row[0]


def event_row(conn: psycopg.Connection, event_id: int) -> dict:
    with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
        return cur.execute("SELECT * FROM worker.suspicious_events WHERE event_id = %s", (event_id,)).fetchone()


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    server = FakeLLM()
    yield server
    server.close()
