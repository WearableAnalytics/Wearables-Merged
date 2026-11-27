"""The task queue in PostgreSQL (`tasks.task_runs`), claimed with FOR UPDATE SKIP LOCKED."""

from collections.abc import Callable
from importlib.resources import files
from typing import Any

from psycopg import Connection
from psycopg.rows import class_row, dict_row
from psycopg.types.json import Jsonb

from .model import TaskOutcome, TaskRequest, TaskRun

_DUE = """
    ((state = 'pending' AND run_after <= now()) OR (state = 'processing' AND locked_until < now()))
    AND (%(templates)s::text[] IS NULL OR template = ANY(%(templates)s))
"""

HEAD = f"""
SELECT template FROM tasks.task_runs
WHERE {_DUE}
ORDER BY priority, run_after, task_id
FOR UPDATE SKIP LOCKED
LIMIT 1
"""

CLAIM = f"""
UPDATE tasks.task_runs
SET state = 'processing',
    attempts = attempts + 1,
    locked_by = %(worker_id)s,
    locked_until = now() + make_interval(secs => %(lease_seconds)s),
    started_at = now()
WHERE task_id IN (
    SELECT task_id FROM tasks.task_runs
    WHERE {_DUE} AND template = %(template)s
    ORDER BY priority, run_after, task_id
    FOR UPDATE SKIP LOCKED
    LIMIT %(limit)s
)
RETURNING task_id, template, params, prompt, trigger, submitted_by, attempts
"""

ENQUEUE = """
INSERT INTO tasks.task_runs (template, params, prompt, trigger, submitted_by, priority, dedup_key)
VALUES (%(template)s, %(params)s, %(prompt)s, %(trigger)s, %(submitted_by)s, %(priority)s, %(dedup_key)s)
ON CONFLICT (dedup_key) DO NOTHING
RETURNING task_id
"""

FINISH = """
UPDATE tasks.task_runs
SET state = 'finished', answer = %(answer)s, result = %(result)s, model = %(model)s,
    spec_versions = %(spec_versions)s, error = NULL, locked_until = NULL, finished_at = now()
WHERE task_id = %(task_id)s AND locked_by = %(worker_id)s AND state = 'processing'
"""

NOTIFY = """
INSERT INTO tasks.notifications (task_id, patient_id, night_date, verdict, explanation)
VALUES (%(task_id)s, %(patient_id)s, %(night_date)s, %(verdict)s, %(explanation)s)
"""

FAIL = """
UPDATE tasks.task_runs
SET state = CASE WHEN attempts >= %(max_attempts)s THEN 'failed' ELSE 'pending' END,
    error = %(error)s,
    locked_until = NULL,
    run_after = now() + make_interval(secs => %(backoff_seconds)s * power(2, attempts - 1)),
    finished_at = CASE WHEN attempts >= %(max_attempts)s THEN now() END
WHERE task_id = %(task_id)s AND locked_by = %(worker_id)s AND state = 'processing'
RETURNING state
"""

_COLUMNS = """task_id, template, params, prompt, trigger, submitted_by, priority, state, attempts, answer, result,
    error, model, spec_versions, created_at, started_at, finished_at"""


def migrate(conn: Connection) -> None:
    conn.execute(files("llm_worker.sql").joinpath("schema.sql").read_bytes())


def enqueue(conn: Connection, request: TaskRequest, priority: int) -> tuple[int, bool]:
    """Returns (task_id, created). A pipeline event that is already queued returns the existing task."""
    row = conn.execute(
        ENQUEUE,
        {
            "template": request.template,
            "params": Jsonb(request.params),
            "prompt": request.prompt,
            "trigger": request.trigger,
            "submitted_by": request.submitted_by,
            "priority": priority,
            "dedup_key": request.dedup_key,
        },
    ).fetchone()
    if row:
        return row[0], True
    existing = conn.execute("SELECT task_id FROM tasks.task_runs WHERE dedup_key = %s", (request.dedup_key,))
    return existing.fetchone()[0], False


def claim(
    conn: Connection,
    worker_id: str,
    lease_seconds: float,
    batch_size: Callable[[str], int],
    templates: list[str] | None = None,
) -> list[TaskRun]:
    """Claim the most urgent due task, plus more of the same template up to that template's batch size."""
    args = {"templates": templates, "worker_id": worker_id, "lease_seconds": lease_seconds}
    with conn.transaction():
        head = conn.execute(HEAD, args).fetchone()
        if head is None:
            return []
        template = head[0]
        with conn.cursor(row_factory=class_row(TaskRun)) as cur:
            rows = cur.execute(CLAIM, args | {"template": template, "limit": max(batch_size(template), 1)}).fetchall()
    return sorted(rows, key=lambda r: r.task_id)


def finish(
    conn: Connection, run: TaskRun, worker_id: str, outcome: TaskOutcome, notification: dict[str, Any] | None
) -> bool:
    """Write the result, and the notification if any, in one transaction. False if the lease was lost."""
    with conn.transaction():
        cur = conn.execute(
            FINISH,
            {
                "task_id": run.task_id,
                "worker_id": worker_id,
                "answer": outcome.answer,
                "result": Jsonb(outcome.result),
                "model": outcome.model,
                "spec_versions": Jsonb(outcome.spec_versions),
            },
        )
        if cur.rowcount != 1:
            return False
        if notification is not None:
            conn.execute(NOTIFY, {"task_id": run.task_id, **notification})
    return True


def fail(
    conn: Connection, run: TaskRun, worker_id: str, error: str, max_attempts: int, backoff_seconds: float
) -> str | None:
    row = conn.execute(
        FAIL,
        {
            "task_id": run.task_id,
            "worker_id": worker_id,
            "error": error,
            "max_attempts": max_attempts,
            "backoff_seconds": backoff_seconds,
        },
    ).fetchone()
    return row[0] if row else None


def get_task(conn: Connection, task_id: int) -> dict | None:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(f"SELECT {_COLUMNS} FROM tasks.task_runs WHERE task_id = %s", (task_id,)).fetchone()


def list_tasks(conn: Connection, trigger: str | None = None, limit: int = 100) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            f"""SELECT {_COLUMNS} FROM tasks.task_runs
                WHERE %(trigger)s::text IS NULL OR trigger = %(trigger)s
                ORDER BY task_id DESC LIMIT %(limit)s""",
            {"trigger": trigger, "limit": limit},
        ).fetchall()


def list_notifications(conn: Connection, limit: int = 100) -> list[dict]:
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT * FROM tasks.notifications ORDER BY notification_id DESC LIMIT %s", (limit,)
        ).fetchall()
