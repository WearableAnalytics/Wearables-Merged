from collections import defaultdict

from psycopg import Connection
from psycopg.rows import dict_row

from ..pipeline import Context

QUERY = """
SELECT kind, ts, text
FROM worker.patient_context
WHERE patient_id = %(patient_id)s
  AND (ts IS NULL OR ts < %(night_date)s::date + 1)
ORDER BY kind, ts NULLS FIRST
"""


class LoadContext:
    name = "load_context"

    def run(self, ctx: Context, conn: Connection) -> dict[str, int]:
        event = ctx.event
        with conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(QUERY, {"patient_id": event.patient_id, "night_date": event.night_date}).fetchall()

        grouped = defaultdict(list)
        for row in rows:
            grouped[row.pop("kind")].append(row)
        ctx.patient = dict(grouped)
        return {kind: len(entries) for kind, entries in ctx.patient.items()}
