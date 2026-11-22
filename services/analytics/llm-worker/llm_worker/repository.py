from importlib.resources import files
from typing import Any

from psycopg import Connection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from .pipeline import Event
from .providers.scenarios import ScenarioStore

CLAIM = """
UPDATE worker.suspicious_events
SET state = 'processing',
    attempts = attempts + 1,
    locked_by = %(worker_id)s,
    locked_until = now() + make_interval(secs => %(lease_seconds)s),
    started_at = now()
WHERE event_id IN (
    SELECT event_id
    FROM worker.suspicious_events
    WHERE (state = 'pending' AND run_after <= now())
       OR (state = 'processing' AND locked_until < now())
    ORDER BY run_after, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT %(limit)s
)
RETURNING event_id, patient_id, night_date, reasons, red_flag, features, attempts
"""

ENQUEUE = """
INSERT INTO worker.suspicious_events (patient_id, night_date, reasons, red_flag, features)
VALUES (%(patient_id)s, %(night_date)s, %(reasons)s, %(red_flag)s, %(features)s)
ON CONFLICT (patient_id, night_date) DO NOTHING
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


def seed(conn: Connection, store: ScenarioStore) -> int:
    """Enqueue the candidate of every scenario (mock data). Safe to run again."""
    with conn.transaction():
        for name in store.names():
            c = store.get(name).candidate(candidate_id=0)
            conn.execute(
                ENQUEUE,
                {
                    "patient_id": c.patient_id,
                    "night_date": c.night_date,
                    "reasons": ", ".join(c.trigger_reasons),
                    "red_flag": c.red_flag,
                    "features": Jsonb({"l2_score": c.l2_score, "scenario": name}),
                },
            )
    return len(store.names())


def claim_batch(conn: Connection, worker_id: str, lease_seconds: float, limit: int) -> list[Event]:
    """Claim up to `limit` due events in queue order. Rows locked by another worker are skipped, never shared."""
    with conn.cursor(row_factory=class_row(Event)) as cur:
        rows = cur.execute(CLAIM, {"worker_id": worker_id, "lease_seconds": lease_seconds, "limit": limit}).fetchall()
    return sorted(rows, key=lambda e: e.event_id)


def claim(conn: Connection, worker_id: str, lease_seconds: float) -> Event | None:
    batch = claim_batch(conn, worker_id, lease_seconds, limit=1)
    return batch[0] if batch else None


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
