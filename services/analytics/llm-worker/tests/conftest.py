from collections.abc import Iterator

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from llm_worker.fake_llm import FakeLLM
from llm_worker.tasks import repository
from llm_worker.tasks.model import TaskRequest


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
            conn.execute("TRUNCATE tasks.notifications, tasks.task_runs RESTART IDENTITY")
            conn.execute(
                "TRUNCATE vitals.sync_batches, vitals.nightly_features, vitals.nightly_deviations,"
                " vitals.nightly_flags, patient_context.profiles, patient_context.entries"
            )
        yield pool


@pytest.fixture
def conn(pool: ConnectionPool) -> Iterator[psycopg.Connection]:
    with pool.connection() as conn:
        yield conn


def chat_request(template: str = "patient_explain", **params) -> TaskRequest:
    return TaskRequest(
        template=template,
        params=params or {"patient_id": "P-001", "since_days": 7},
        prompt="What happened to P-001 last week?",
        trigger="chat",
        submitted_by="doctor",
    )


def pipeline_request(patient_id: str = "P-001", night: str = "2026-03-14") -> TaskRequest:
    return TaskRequest(
        template="alert_triage",
        params={"patient_id": patient_id, "night": night, "trigger_reasons": ["rhr_z>2"], "red_flag": False},
        prompt=f"Night {night} of {patient_id} was flagged.",
        trigger="pipeline",
        submitted_by="pipeline",
        dedup_key=f"alert_triage:{patient_id}:{night}",
    )


def task_row(conn: psycopg.Connection, task_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM tasks.task_runs WHERE task_id = %s", (task_id,)).fetchone()


def notifications(conn: psycopg.Connection) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute("SELECT * FROM tasks.notifications ORDER BY notification_id").fetchall()


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    server = FakeLLM()
    yield server
    server.close()
