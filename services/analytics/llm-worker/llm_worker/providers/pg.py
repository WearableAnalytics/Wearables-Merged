"""PostgreSQL data source: the mock gold serving tables (`vitals`) and the descriptive context (`patient_context`).

`load_scenarios` plays the part of the gold sync for now: it writes the scenario fixtures into the serving tables as one
committed batch. The real sync (Spark -> staging -> `commit_batch`, semops plan §4.4) later writes the same tables,
and nothing in the worker changes.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..dto import AlertCandidate, ContextItem, DescriptiveContext, Fact, NightRow, NumericCondition, NumericContext
from . import Match, visible_items
from .scenarios import PREVIOUS_NIGHTS, SIGNALS, WINDOW_NIGHTS, ScenarioStore, age_band

LOAD_NIGHTS = 31  # the window of 14 nights before any of the last 15 nights, plus a margin
_OPS = {">=": ">=", "<=": "<="}
_SIGNAL_COLUMNS = list(SIGNALS)


# --- writing (mock gold sync)


def load_scenarios(conn: Connection, store: ScenarioStore, batch_id: str, nights: int = LOAD_NIGHTS) -> None:
    """Replace the serving tables with the scenario data, as one committed batch."""
    night_from, night_to = store.today - timedelta(days=nights - 1), store.today
    with conn.transaction():
        conn.execute(
            "TRUNCATE vitals.nightly_flags, vitals.nightly_deviations, vitals.nightly_features,"
            " patient_context.entries, patient_context.profiles"
        )
        conn.execute(
            """INSERT INTO vitals.sync_batches (batch_id, source, night_from, night_to, status)
               VALUES (%s, %s, %s, %s, 'staged')
               ON CONFLICT (batch_id) DO UPDATE SET status = 'staged', staged_at = now(), committed_at = NULL""",
            (batch_id, f"scenarios:{len(store.names())} files", night_from, night_to),
        )
        features, deviations, flags, profiles, entries = [], [], [], [], []
        for pid in store.patient_ids():
            scenario = store.patient(pid)
            profiles.append((pid, scenario.patient.birth_year, scenario.patient.sex))
            entries += [(e.id, pid, e.kind, e.ts, e.text.strip()) for e in scenario.context]
            for d in range(nights):
                night = night_to - timedelta(days=d)
                numeric = store.numeric.get(pid, night)
                values = {f.name: f.value for f in numeric.tonight}
                features.append((pid, night, *[values.get(c) for c in _SIGNAL_COLUMNS], batch_id))
                for f in numeric.tonight:
                    spread = SIGNALS[f.name][1]
                    deviations.append((pid, night, f.name, f.baseline, spread, f.z, numeric.coverage[f.name], batch_id))
            flags += [
                (pid, c.night_date, c.trigger_reasons, c.red_flag, c.l2_score, batch_id) for c in scenario.candidates()
            ]

        with conn.cursor() as cur:
            cur.executemany("INSERT INTO patient_context.profiles VALUES (%s, %s, %s)", profiles)
            cur.executemany(
                "INSERT INTO patient_context.entries (entry_id, patient_id, kind, ts, text)"
                " VALUES (%s, %s, %s, %s, %s)",
                entries,
            )
            columns = ", ".join(_SIGNAL_COLUMNS)
            marks = ", ".join(["%s"] * (len(_SIGNAL_COLUMNS) + 3))
            cur.executemany(
                f"INSERT INTO vitals.nightly_features (patient_id, night_date, {columns}, batch_id) VALUES ({marks})",
                features,
            )
            cur.executemany(
                """INSERT INTO vitals.nightly_deviations
                   (patient_id, night_date, signal, baseline_median, baseline_mad, z, coverage, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                deviations,
            )
            cur.executemany(
                """INSERT INTO vitals.nightly_flags (patient_id, night_date, l1_reasons, red_flag, l2_score, batch_id)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                flags,
            )
        conn.execute(
            "UPDATE vitals.sync_batches SET status = 'committed', committed_at = now() WHERE batch_id = %s", (batch_id,)
        )


# --- reading


class PgNumericProvider:
    """One patient-night and the 14 nights before it, from `vitals.nightly_features` + `nightly_deviations`."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def get(self, patient_id: str, night_date: date) -> NumericContext:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                f"""SELECT night_date, {", ".join(_SIGNAL_COLUMNS)} FROM vitals.nightly_features
                    WHERE patient_id = %s AND night_date BETWEEN %s AND %s""",
                (patient_id, night_date - timedelta(days=WINDOW_NIGHTS), night_date),
            ).fetchall()
            deviations = cur.execute(
                """SELECT signal, baseline_median, z, coverage FROM vitals.nightly_deviations
                   WHERE patient_id = %s AND night_date = %s""",
                (patient_id, night_date),
            ).fetchall()
        by_night = {r["night_date"]: r for r in rows}
        if night_date not in by_night:
            raise LookupError(f"no data for patient {patient_id} on {night_date}")
        tracked = {d["signal"]: d for d in deviations}
        names = [n for n in SIGNALS if n in tracked]

        def value(night: date, name: str) -> float | None:
            row = by_night.get(night)
            return None if row is None else row[name]

        facts = [
            Fact(
                id=f"n:{name}",
                name=name,
                unit=SIGNALS[name][0],
                value=value(night_date, name),
                baseline=tracked[name]["baseline_median"],
                z=tracked[name]["z"],
                previous=[value(night_date - timedelta(days=d), name) for d in range(1, PREVIOUS_NIGHTS + 1)],
            )
            for name in names
        ]
        window = [
            NightRow(
                night_date=night_date - timedelta(days=d),
                values={name: value(night_date - timedelta(days=d), name) for name in names},
            )
            for d in range(WINDOW_NIGHTS, 0, -1)
        ]
        return NumericContext(
            night_date=night_date,
            tonight=facts,
            window=window,
            coverage={name: tracked[name]["coverage"] for name in names},
            source="pg:vitals",
        )


class PgDescriptiveProvider:
    """`patient_context`: profile + dated entries, never anything written after `as_of`."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool

    def get(self, patient_id: str, night_date: date, as_of: datetime, max_items: int = 20) -> DescriptiveContext:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            profile = cur.execute(
                "SELECT birth_year, sex FROM patient_context.profiles WHERE patient_id = %s", (patient_id,)
            ).fetchone()
            if profile is None:
                raise LookupError(f"no data for patient {patient_id}")
            rows = cur.execute(
                """SELECT entry_id, kind, ts, text FROM patient_context.entries
                   WHERE patient_id = %s AND (ts IS NULL OR ts < %s)""",
                (patient_id, as_of),
            ).fetchall()
        items = [
            ContextItem(id=f"c:{r['entry_id']}", kind=r["kind"], ts=r["ts"], days_before=None, text=r["text"])
            for r in rows
        ]
        kept, truncated = visible_items(items, night_date, as_of, max_items)
        return DescriptiveContext(
            age_band=age_band(night_date.year - profile["birth_year"]),
            sex=profile["sex"],
            items=kept,
            truncated=truncated,
            source="pg:patient_context",
        )


class PgDataSource:
    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.numeric = PgNumericProvider(pool)
        self.descriptive = PgDescriptiveProvider(pool)

    def _rows(self, query: str, params: tuple | dict = ()) -> list[dict]:
        with self.pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(query, params).fetchall()

    @property
    def today(self) -> date:
        row = self._rows("SELECT max(night_date) AS today FROM vitals.nightly_features")
        return row[0]["today"] or date.min

    def patient_ids(self) -> list[str]:
        return [r["patient_id"] for r in self._rows("SELECT patient_id FROM patient_context.profiles ORDER BY 1")]

    def has_patient(self, patient_id: str) -> bool:
        return bool(self._rows("SELECT 1 FROM patient_context.profiles WHERE patient_id = %s", (patient_id,)))

    def patients(self) -> list[dict]:
        today = self.today
        rows = self._rows(
            """SELECT p.patient_id, p.birth_year, p.sex,
                      coalesce(array_agg(f.night_date ORDER BY f.night_date)
                               FILTER (WHERE f.night_date IS NOT NULL), '{}') AS flagged
               FROM patient_context.profiles p
               LEFT JOIN vitals.nightly_flags f ON f.patient_id = p.patient_id
               GROUP BY p.patient_id, p.birth_year, p.sex ORDER BY p.patient_id"""
        )
        return [
            {
                "patient_id": r["patient_id"],
                "age_band": age_band(today.year - r["birth_year"]),
                "sex": r["sex"],
                "flagged_nights": [n.isoformat() for n in r["flagged"]],
            }
            for r in rows
        ]

    def all_candidates(self) -> list[AlertCandidate]:
        rows = self._rows(
            """SELECT patient_id, night_date, l1_reasons, red_flag, l2_score FROM vitals.nightly_flags
               WHERE cardinality(l1_reasons) > 0 OR red_flag ORDER BY patient_id, night_date"""
        )
        return [
            AlertCandidate(
                candidate_id=0,
                patient_id=r["patient_id"],
                night_date=r["night_date"],
                trigger_reasons=r["l1_reasons"],
                red_flag=r["red_flag"],
                l2_score=r["l2_score"],
            )
            for r in rows
        ]

    def nights_matching(
        self, conditions: list[NumericCondition], match: Match, since_days: int, patient_id: str | None = None
    ) -> list[tuple[str, date]]:
        """Patient-nights in the window where the structured predicate holds. Exact, in SQL; no model involved."""
        if not conditions:
            return []
        clauses, params = [], {"today": self.today, "days": since_days, "pid": patient_id}
        for i, c in enumerate(conditions):
            clauses.append(
                sql.SQL("bool_or(signal = {s} AND z {op} {z})").format(
                    s=sql.Placeholder(f"s{i}"), op=sql.SQL(_OPS[c.op]), z=sql.Placeholder(f"z{i}")
                )
            )
            params |= {f"s{i}": c.signal, f"z{i}": c.z}
        having = sql.SQL(" AND " if match == "all" else " OR ").join(clauses)
        query = sql.SQL(
            """SELECT patient_id, night_date FROM vitals.nightly_deviations
               WHERE night_date > %(today)s::date - %(days)s AND night_date <= %(today)s
                 AND (%(pid)s::text IS NULL OR patient_id = %(pid)s)
               GROUP BY patient_id, night_date
               HAVING {having}
               ORDER BY patient_id, night_date"""
        ).format(having=having)
        with self.pool.connection() as conn:
            return [(r[0], r[1]) for r in conn.execute(query, params).fetchall()]
