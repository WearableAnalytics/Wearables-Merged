"""Locked, checksummed schema setup and explicit runtime grants. No runtime secrets needed."""

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from psycopg import AsyncConnection, sql

MIGRATIONS = Path(__file__).parents[1] / "migrations"
TABLES = ["uploads", "records", "upload_records", "outbox", "events"]


async def _schema_signature(connection, schema):
    """Compare an untracked original installation with the baseline on this server."""
    queries = {
        "tables": "SELECT c.relname,c.relkind,c.relpersistence FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname::text=ANY(%s) ORDER BY 1",
        "columns": "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,"
        "pg_get_expr(d.adbin,d.adrelid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid=c.oid LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum "
        "WHERE n.nspname=%s AND c.relname::text=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,a.attnum",
        "constraints": "SELECT c.relname,k.contype,k.convalidated,pg_get_constraintdef(k.oid) "
        "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relname::text=ANY(%s) ORDER BY 1,2,4",
        "indexes": "SELECT c.relname,pg_get_indexdef(i.indexrelid),i.indisvalid FROM pg_index i "
        "JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relname::text=ANY(%s) ORDER BY 1,2",
    }
    result = {}
    for name, query in queries.items():
        rows = await (await connection.execute(query, (schema, TABLES))).fetchall()
        result[name] = [
            tuple(value.replace(schema + ".", "ingestion.") if isinstance(value, str) else value for value in row)
            for row in rows
        ]
    return result


async def _adopt_baseline(connection, body):
    # Old app.migrate applied 001 directly. Verify its actual structure before
    # recording it, without changing or deleting any accepted data.
    actual = await _schema_signature(connection, "ingestion")
    temporary = "ingestion_check_" + uuid4().hex
    await connection.execute("SAVEPOINT baseline_check")
    try:
        expected_sql = body.replace("ingestion.", temporary + ".").replace(
            "CREATE SCHEMA IF NOT EXISTS ingestion;", f"CREATE SCHEMA {temporary};"
        )
        await connection.execute(expected_sql)
        expected = await _schema_signature(connection, temporary)
    finally:
        await connection.execute("ROLLBACK TO SAVEPOINT baseline_check")
        await connection.execute("RELEASE SAVEPOINT baseline_check")
    if actual != expected:
        raise RuntimeError("Existing ingestion schema differs from migration 001; operator review is required")


async def _grant_runtime(connection, runtime_role):
    role = await (
        await connection.execute(
            "SELECT rolsuper,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls,rolcanlogin "
            "FROM pg_roles WHERE rolname=%s",
            (runtime_role,),
        )
    ).fetchone()
    if role is None or any(role[:5]) or not role[5]:
        raise RuntimeError("INGEST_RUNTIME_ROLE must be an existing, unprivileged login role")
    inherited = await (
        await connection.execute(
            "SELECT pg_has_role(%s,oid,'MEMBER') FROM pg_roles "
            "WHERE rolname IN (current_user,'pg_read_all_data','pg_write_all_data')",
            (runtime_role,),
        )
    ).fetchall()
    owner = await (
        await connection.execute(
            "SELECT pg_has_role(%s,nspowner,'MEMBER') FROM pg_namespace WHERE nspname='ingestion'",
            (runtime_role,),
        )
    ).fetchone()
    if any(row[0] for row in inherited) or owner[0]:
        raise RuntimeError("Runtime authority must be separate from migration and schema ownership")
    role_name = sql.Identifier(runtime_role)
    for grantee in [sql.SQL("PUBLIC"), role_name]:
        await connection.execute(sql.SQL("REVOKE ALL ON SCHEMA ingestion FROM {}").format(grantee))
        await connection.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA ingestion FROM {}").format(grantee))
        await connection.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA ingestion FROM {}").format(grantee))
    statements = [
        "GRANT USAGE ON SCHEMA ingestion TO {}",
        "GRANT SELECT,INSERT ON ingestion.uploads,ingestion.upload_records TO {}",
        "GRANT SELECT,INSERT,UPDATE ON ingestion.records,ingestion.outbox TO {}",
        "GRANT INSERT ON ingestion.events TO {}",
        "GRANT USAGE,SELECT ON SEQUENCE ingestion.events_id_seq TO {}",
    ]
    for statement in statements:
        await connection.execute(sql.SQL(statement).format(role_name))


async def migrate(database_url, runtime_role=None):
    async with await AsyncConnection.connect(database_url, autocommit=True, connect_timeout=10) as connection:
        async with connection.transaction():
            await connection.execute("SET LOCAL lock_timeout='10s'")
            await connection.execute("SET LOCAL statement_timeout='120s'")
            await connection.execute("SET LOCAL search_path=pg_catalog")
            await connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended('wearables-ingestion-migrations',0))"
            )
            await connection.execute("CREATE SCHEMA IF NOT EXISTS ingestion")
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS ingestion.schema_migrations ("
                "version text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
            )
            paths = sorted(MIGRATIONS.glob("[0-9]*.sql"))
            applied_versions = {
                row[0]
                for row in await (
                    await connection.execute("SELECT version FROM ingestion.schema_migrations")
                ).fetchall()
            }
            if not paths or applied_versions - {path.name for path in paths}:
                raise RuntimeError("Database migration history is not supported by this image")
            for path in paths:
                body = path.read_text(encoding="utf-8")  # Normalize CRLF for Windows-built images.
                checksum = hashlib.sha256(body.encode()).hexdigest()
                applied = await (
                    await connection.execute(
                        "SELECT sha256 FROM ingestion.schema_migrations WHERE version=%s", (path.name,)
                    )
                ).fetchone()
                if applied:
                    if applied[0] != checksum:
                        raise RuntimeError("An applied ingestion migration was changed: " + path.name)
                    continue
                existing = await (
                    await connection.execute(
                        "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='ingestion' AND c.relname::text=ANY(%s)",
                        (TABLES,),
                    )
                ).fetchone()
                if path.name == "001_ingestion.sql" and existing[0]:
                    await _adopt_baseline(connection, body)
                else:
                    await connection.execute(body)
                await connection.execute(
                    "INSERT INTO ingestion.schema_migrations(version,sha256) VALUES (%s,%s)", (path.name, checksum)
                )
            if runtime_role:
                await _grant_runtime(connection, runtime_role)


if __name__ == "__main__":
    asyncio.run(migrate(os.environ["INGEST_DATABASE_URL"], os.getenv("INGEST_RUNTIME_ROLE")))
