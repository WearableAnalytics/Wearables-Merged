from importlib.resources import files
from typing import Any

from psycopg import Connection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from .pipeline import Event

CLAIM = """
UPDATE worker.suspicious_events
SET state = 'processing',
    attempts = attempts + 1,
    locked_by = %(worker_id)s,
    locked_until = now() + make_interval(secs => %(lease_seconds)s),
    started_at = now()
WHERE event_id = (
    SELECT event_id
    FROM worker.suspicious_events
    WHERE (state = 'pending' AND run_after <= now())
       OR (state = 'processing' AND locked_until < now())
    ORDER BY run_after, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING event_id, patient_id, night_date, reasons, red_flag, features, attempts
"""

FINISH = """
UPDATE worker.suspicious_events
SET state = 'finished',
    result = %(result)s,
    explanation = %(explanation)s,
    error = NULL,
    locked_until = NULL,
    finished_at = now()
WHERE event_id = %(event_id)s AND locked_by = %(worker_id)s AND state = 'processing'
"""

FAIL = """
UPDATE worker.suspicious_events
SET state = CASE WHEN attempts >= %(max_attempts)s THEN 'failed' ELSE 'pending' END,
    error = %(error)s,
    locked_until = NULL,
    run_after = now() + make_interval(secs => %(backoff_seconds)s * power(2, attempts - 1)),
    finished_at = CASE WHEN attempts >= %(max_attempts)s THEN now() END
WHERE event_id = %(event_id)s AND locked_by = %(worker_id)s AND state = 'processing'
RETURNING state
"""


def migrate(conn: Connection) -> None:
    conn.execute(_sql("schema.sql"))


def seed(conn: Connection) -> None:
    conn.execute(_sql("seed.sql"))


def claim(conn: Connection, worker_id: str, lease_seconds: float) -> Event | None:
    with conn.cursor(row_factory=class_row(Event)) as cur:
        return cur.execute(CLAIM, {"worker_id": worker_id, "lease_seconds": lease_seconds}).fetchone()


def finish(conn: Connection, event: Event, worker_id: str, result: dict[str, Any], explanation: str | None) -> bool:
    cur = conn.execute(
        FINISH,
        {"event_id": event.event_id, "worker_id": worker_id, "result": Jsonb(result), "explanation": explanation},
    )
    return cur.rowcount == 1


def fail(
    conn: Connection, event: Event, worker_id: str, error: str, max_attempts: int, backoff_seconds: float
) -> str | None:
    row = conn.execute(
        FAIL,
        {
            "event_id": event.event_id,
            "worker_id": worker_id,
            "error": error,
            "max_attempts": max_attempts,
            "backoff_seconds": backoff_seconds,
        },
    ).fetchone()
    return row[0] if row else None


def _sql(name: str) -> bytes:
    return files("llm_worker.sql").joinpath(name).read_bytes()
