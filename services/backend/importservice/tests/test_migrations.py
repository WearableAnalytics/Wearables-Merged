"""Real PostgreSQL checks for install, upgrade, adoption and runtime authority."""

import asyncio
import json
import os
import secrets
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from psycopg import AsyncConnection, errors, sql
from psycopg.conninfo import make_conninfo

from app import migrate as migration
from app.contracts import parse_upload
from app.crypto import ArchiveCipher
from app.main import create_app
from app.repository import Repository

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def database(settings):
    if not os.getenv("INGEST_TEST_DATABASE_URL"):
        pytest.skip("Set INGEST_TEST_DATABASE_URL to the isolated ingestion_test database")
    async with await AsyncConnection.connect(settings.database_url, autocommit=True) as connection:
        assert (await (await connection.execute("SELECT current_database()")).fetchone())[0] == "ingestion_test"
        await connection.execute("DROP SCHEMA IF EXISTS ingestion CASCADE")
        role, password = "ingestion_test_" + uuid4().hex, secrets.token_urlsafe(24)
        await connection.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(password))
        )
        try:
            yield connection, role, make_conninfo(settings.database_url, user=role, password=password)
        finally:
            await connection.execute("DROP SCHEMA IF EXISTS ingestion CASCADE")
            await connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            await connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


async def test_fresh_and_concurrent_repeated_migration(database, settings):
    connection, role, _ = database
    await asyncio.gather(migration.migrate(settings.database_url, role), migration.migrate(settings.database_url, role))
    assert (await (await connection.execute("SELECT count(*) FROM ingestion.schema_migrations")).fetchone())[0] == 1
    assert not (await (await connection.execute("SELECT to_regclass('ingestion.uploads') IS NULL")).fetchone())[0]


async def test_legacy_schema_is_adopted_without_losing_accepted_data(database, settings, batch, claims):
    connection, role, _ = database
    await connection.execute((migration.MIGRATIONS / "001_ingestion.sql").read_text())
    repository = Repository(settings, ArchiveCipher(settings))
    await repository.open()
    try:
        upload_id, _ = await repository.accept(parse_upload(json.dumps(batch).encode(), claims, None, settings))
    finally:
        await repository.close()
    before = await (
        await connection.execute("SELECT raw_ciphertext FROM ingestion.uploads WHERE id=%s", (upload_id,))
    ).fetchone()
    await migration.migrate(settings.database_url, role)
    after = await (
        await connection.execute("SELECT raw_ciphertext FROM ingestion.uploads WHERE id=%s", (upload_id,))
    ).fetchone()
    assert before == after
    assert (await (await connection.execute("SELECT count(*) FROM ingestion.outbox")).fetchone())[0] == 1


@pytest.mark.parametrize(
    "change",
    [
        "ALTER TABLE ingestion.records DROP COLUMN input_sha256",
        "DROP TABLE ingestion.events",
    ],
)
async def test_partial_or_changed_legacy_schema_is_not_silently_adopted(database, settings, change):
    connection, role, _ = database
    await connection.execute((migration.MIGRATIONS / "001_ingestion.sql").read_text())
    await connection.execute(change)
    with pytest.raises(RuntimeError, match="differs from migration"):
        await migration.migrate(settings.database_url, role)
    assert (await (await connection.execute("SELECT to_regclass('ingestion.schema_migrations')")).fetchone())[0] is None


async def test_changed_applied_migration_fails_without_modifying_journal(database, settings, monkeypatch, tmp_path):
    connection, role, _ = database
    await migration.migrate(settings.database_url, role)
    original = (migration.MIGRATIONS / "001_ingestion.sql").read_text()
    (tmp_path / "001_ingestion.sql").write_text(original + "\n-- changed after application\n")
    monkeypatch.setattr(migration, "MIGRATIONS", tmp_path)
    with pytest.raises(RuntimeError, match="applied ingestion migration was changed"):
        await migration.migrate(settings.database_url, role)
    assert (await (await connection.execute("SELECT count(*) FROM ingestion.schema_migrations")).fetchone())[0] == 1


async def test_windows_line_endings_keep_same_migration_checksum(database, settings, monkeypatch, tmp_path):
    _, role, _ = database
    await migration.migrate(settings.database_url, role)
    raw = (migration.MIGRATIONS / "001_ingestion.sql").read_bytes()
    (tmp_path / "001_ingestion.sql").write_bytes(raw.replace(b"\n", b"\r\n"))
    monkeypatch.setattr(migration, "MIGRATIONS", tmp_path)
    await migration.migrate(settings.database_url, role)


async def test_older_image_rejects_newer_database_migration_history(database, settings):
    connection, role, _ = database
    await migration.migrate(settings.database_url, role)
    await connection.execute(
        "INSERT INTO ingestion.schema_migrations(version,sha256) VALUES ('999_future.sql','future')"
    )
    with pytest.raises(RuntimeError, match="history is not supported"):
        await migration.migrate(settings.database_url, role)


async def test_runtime_can_accept_and_claim_but_cannot_change_archive_or_schema(database, settings, batch, claims):
    _, role, runtime_url = database
    await migration.migrate(settings.database_url, role)
    settings.database_url = runtime_url
    repository = Repository(settings, ArchiveCipher(settings))
    await repository.open()
    try:
        await repository.check_ready()
        upload_id, _ = await repository.accept(parse_upload(json.dumps(batch).encode(), claims, None, settings))
        assert (await repository.receipt(upload_id, claims))["recordCount"] == 1
        assert (await repository.claim())["stage"] == "raw"
    finally:
        await repository.close()
    async with await AsyncConnection.connect(runtime_url, autocommit=True) as runtime:
        for statement in [
            "UPDATE ingestion.uploads SET reading_count=reading_count",
            "DELETE FROM ingestion.uploads",
            "TRUNCATE ingestion.records CASCADE",
            "CREATE TABLE ingestion.forbidden (id integer)",
            "SELECT * FROM ingestion.schema_migrations",
        ]:
            with pytest.raises(errors.InsufficientPrivilege):
                await runtime.execute(statement)


async def test_ready_fails_when_required_runtime_privilege_is_revoked(database, settings):
    connection, role, runtime_url = database
    await migration.migrate(settings.database_url, role)
    settings.database_url = runtime_url
    repository = Repository(settings, ArchiveCipher(settings))
    await repository.open()
    app = create_app(settings)
    app.state.repository = repository
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/ready")).status_code == 200
            await connection.execute(sql.SQL("REVOKE UPDATE ON ingestion.outbox FROM {}").format(sql.Identifier(role)))
            assert (await client.get("/ready")).status_code == 503
            assert (await client.get("/health")).status_code == 200
    finally:
        await repository.close()


async def test_privileged_or_missing_runtime_role_rolls_back_install(database, settings):
    connection, _, _ = database
    current_user = (await (await connection.execute("SELECT current_user")).fetchone())[0]
    for role in [current_user, "missing_" + uuid4().hex]:
        with pytest.raises(RuntimeError, match="unprivileged login role"):
            await migration.migrate(settings.database_url, role)
        assert (await (await connection.execute("SELECT to_regclass('ingestion.uploads')")).fetchone())[0] is None
