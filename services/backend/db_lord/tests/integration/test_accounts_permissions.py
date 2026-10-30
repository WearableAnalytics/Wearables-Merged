"""Independent PostgreSQL proof. Each test uses a disposable database, never Compose data."""

import asyncio
import hashlib
import os
import secrets
import shutil
import socket
import sys
from pathlib import Path

import httpx
import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.core.config import settings
from app.core.exceptions import ConflictError
from app.db.postgres.orm import ControlUser
from app.schemas.control import LoginChallengeCreate, UserCreate, UserPatch
from app.services.control_service import ControlService
from app.services.login_challenge import LoginChallengeService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[2]
HEADERS = {"X-Control-Service-Token": "synthetic-e2e-account-writer"}
ADMIN_EMAIL = "admin@example.test"


@pytest.fixture
async def account_engine(monkeypatch):
    monkeypatch.setattr(settings, "CONTROL_BOOTSTRAP_ADMIN_EMAILS", f"{ADMIN_EMAIL},second@example.test")
    with PostgresContainer("postgres:18", driver="asyncpg").with_bind_ports(5432, ("127.0.0.1", None)) as postgres:
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", postgres.get_connection_url())
        await asyncio.to_thread(command.upgrade, config, "7c2e9d4b1a6f")
        engine = create_async_engine(postgres.get_connection_url())
        async with engine.begin() as connection:
            patient_id = (
                await connection.execute(
                    text("INSERT INTO patients(charite_id,name) VALUES (uuidv7(),'Synthetic Person') RETURNING id")
                )
            ).scalar_one()
            case_id = (
                await connection.execute(
                    text("INSERT INTO cases(patient_id,status) VALUES (:patient,'ONGOING') RETURNING id"),
                    {"patient": patient_id},
                )
            ).scalar_one()
        await asyncio.to_thread(command.upgrade, config, "head")
        try:
            yield engine, config, str(patient_id), str(case_id)
        finally:
            await engine.dispose()


async def test_migration_preserves_cases_and_has_reversible_access_tables(account_engine):
    engine, config, patient, case = account_engine

    async def check_case():
        async with engine.connect() as connection:
            assert (
                str(
                    (
                        await connection.execute(text("SELECT patient_id FROM cases WHERE id=:id"), {"id": case})
                    ).scalar_one()
                )
                == patient
            )
            assert (await connection.execute(text("SELECT count(*) FROM patients"))).scalar_one() == 1

    await check_case()
    async with engine.connect() as connection:
        assert (await connection.execute(text("SELECT count(*) FROM case_access"))).scalar_one() == 0
        assert (
            await connection.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name IN ('upload_grants','canonical_observations','archive_sources')"
                )
            )
        ).scalar_one() == 0
    await asyncio.to_thread(command.downgrade, config, "7c2e9d4b1a6f")
    await check_case()
    await asyncio.to_thread(command.upgrade, config, "head")
    await check_case()


async def test_postgres_serializes_admin_and_login_proof_changes(account_engine):
    engine, _, _, _ = account_engine
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def call(method, *args, **kwargs):
        async with factory() as db:
            return await getattr(ControlService(db), method)(*args, **kwargs)

    first = await call("create_user", UserCreate(email=ADMIN_EMAIL), bootstrap=True)
    second = await call("create_user", UserCreate(email="second@example.test"), bootstrap=True)
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                call(
                    "patch_user",
                    user.id,
                    UserPatch(actor_id=user.id, actor_auth_version=1, expected_revision=1, is_admin=False),
                )
                for user in (first, second)
            ),
            return_exceptions=True,
        ),
        10,
    )
    assert sum(isinstance(result, ConflictError) for result in results) == 1
    async with factory() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ControlUser)
                .where(ControlUser.status == "approved", ControlUser.is_admin.is_(True))
            )
            == 1
        )
        current = await db.scalar(select(ControlUser).where(ControlUser.is_admin.is_(True)))
        current_id, version = current.id, current.auth_version
    digest = hashlib.sha256(b"synthetic-login-proof").hexdigest()
    async with factory() as db:
        await LoginChallengeService(db).issue(
            LoginChallengeCreate(token_hash=digest, user_id=current_id, auth_version=version, ttl_seconds=60)
        )

    async def consume():
        async with factory() as db:
            return await LoginChallengeService(db).consume(digest)

    results = await asyncio.wait_for(asyncio.gather(consume(), consume(), return_exceptions=True), 10)
    assert sum(isinstance(result, HTTPException) and result.status_code == 403 for result in results) == 1
    assert sum(not isinstance(result, Exception) for result in results) == 1


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def stop(process):
    if process and process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()


async def wait_http(url, process):
    async with httpx.AsyncClient(timeout=1) as client:
        for _ in range(100):
            if process.returncode is not None:
                pytest.fail("Account test service stopped; inspect its test log.")
            try:
                if (await client.get(url)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    pytest.fail("Account test service did not become ready.")


async def test_real_bff_database_approval_case_access_restart_and_logout(account_engine, tmp_path):
    engine, _, patient_id, case_id = account_engine
    db_port, bff_port = port(), port()
    db_url, bff_url = f"http://127.0.0.1:{db_port}", f"http://127.0.0.1:{bff_port}"
    origin = "http://127.0.0.1:5237"
    common = {
        **os.environ,
        "CONTROL_WRITE_TOKEN": HEADERS["X-Control-Service-Token"],
        "CONTROL_READ_TOKEN": "synthetic-e2e-account-reader",
        "CONTROL_BOOTSTRAP_ADMIN_EMAILS": ADMIN_EMAIL,
        "LEGACY_OPERATOR_TOKEN": "synthetic-e2e-operator",
        "API_TOKEN_SERVICE_TOKEN": "synthetic-e2e-token-service",
    }
    db_env = {
        **common,
        "POSTGRES_SERVER": engine.url.host,
        "POSTGRES_PORT": str(engine.url.port),
        "POSTGRES_USER": engine.url.username,
        "POSTGRES_PASSWORD": engine.url.password,
        "POSTGRES_DB": engine.url.database,
    }
    bff_env = {
        **common,
        "PORT": str(bff_port),
        "NODE_ENV": "development",
        "API_PREFIX": "/api",
        "USE_MOCK_DATA": "false",
        "LOG_LEVEL": "error",
        "BACKEND_URL": bff_url,
        "FRONTEND_REDIRECT_URL": origin,
        "FRONTEND_ORIGINS": origin,
        "DATABASE_API_URL": db_url,
        "DATABASE_API_TIMEOUT": "5000",
        "AUTH_SESSION_EXPIRY_SECONDS": "3600",
        "MAGIC_LINK_EXPIRY_SECONDS": "600",
        "TOKEN_ISSUER": "synthetic-account-test",
        "JWT_SECRET": "synthetic-account-test-signing-key-at-least-32",
        "ADMIN_EMAILS": ADMIN_EMAIL,
        "ALLOW_DEV_AUTH_BYPASS": "false",
        "BREVO_API_KEY": "disabled",
    }
    db_process = bff_process = None
    with (tmp_path / "db.log").open("w") as db_log, (tmp_path / "bff.log").open("w") as bff_log:
        try:
            # Account endpoints use only PostgreSQL. No Influx, Kafka or archive is started.
            db_process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(db_port),
                "--lifespan",
                "off",
                "--no-access-log",
                cwd=ROOT,
                env=db_env,
                stdout=db_log,
                stderr=db_log,
            )
            await wait_http(f"{db_url}/livez", db_process)

            async def start_bff():
                process = await asyncio.create_subprocess_exec(
                    shutil.which("node"),
                    "--import",
                    "tsx",
                    "src/server.ts",
                    cwd=WORKSPACE / "services/backend/wearables-bff",
                    env=bff_env,
                    stdout=bff_log,
                    stderr=bff_log,
                )
                await wait_http(f"{bff_url}/api/health", process)
                return process

            bff_process = await start_bff()
            async with (
                httpx.AsyncClient(base_url=db_url, headers=HEADERS) as authority,
                httpx.AsyncClient(base_url=bff_url + "/api", headers={"Origin": origin}) as admin,
                httpx.AsyncClient(base_url=bff_url + "/api", headers={"Origin": origin}) as staff,
            ):
                admin_record = (await authority.get("/control/users", params={"email": ADMIN_EMAIL})).json()["items"][0]

                async def login(client, user):
                    raw = secrets.token_hex(32)
                    issue = await authority.post(
                        "/control/login-challenges",
                        json={
                            "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
                            "user_id": user["id"],
                            "auth_version": user["auth_version"],
                            "ttl_seconds": 60,
                        },
                    )
                    assert issue.status_code == 200
                    return await client.get("/verify-magiclink", params={"token": raw})

                assert (await login(admin, admin_record)).status_code == 200
                assert (await admin.get("/me")).json()["user"]["isAdmin"] is True
                assert (
                    await staff.post("/register", json={"email": "staff@example.test", "role": "practitioner"})
                ).status_code == 201
                assert (await staff.post("/login", json={"email": "staff@example.test"})).status_code == 403
                staff_record = (await authority.get("/control/users", params={"email": "staff@example.test"})).json()[
                    "items"
                ][0]
                approved = await admin.patch(
                    f"/admin/users/{staff_record['id']}", json={"roles": ["practitioner"], "status": "approved"}
                )
                assert approved.status_code == 200, approved.text
                staff_record = (await authority.get(f"/control/users/{staff_record['id']}")).json()
                assert (await login(staff, staff_record)).status_code == 200
                assert (await staff.get("/patients")).json() == []
                assert (await staff.get(f"/cases/{case_id}")).status_code == 403
                body = {
                    "expected_revision": 0,
                    "active": True,
                    "purpose": "clinical-reference",
                    "scopes": ["read"],
                    "reason": "Synthetic case review",
                }
                assert (
                    await staff.put(f"/admin/case-access/{case_id}/{staff_record['id']}", json=body)
                ).status_code == 403
                saved = await admin.put(f"/admin/case-access/{case_id}/{staff_record['id']}", json=body)
                assert saved.status_code == 200, saved.text
                assert (await staff.get(f"/cases/{case_id}")).json()["caseToken"] is None
                assert (await staff.get(f"/patients/{patient_id}")).json()["birthDate"] is None
                assert len((await staff.get("/cases")).json()) == 1
                assert (
                    await admin.put(f"/admin/case-access/{case_id}/{staff_record['id']}", json=body)
                ).status_code == 409
                assert (await staff.get("/extraction/v1/measurements")).status_code == 410
                await stop(bff_process)
                bff_process = await start_bff()
                assert (await staff.get("/me")).status_code == 200  # Stored accounts survive a new BFF process.
                body.update(expected_revision=1, active=False)
                assert (
                    await admin.put(f"/admin/case-access/{case_id}/{staff_record['id']}", json=body)
                ).status_code == 200
                assert (await staff.get(f"/cases/{case_id}")).status_code == 403
                assert (await staff.get("/patients")).json() == []
                cookie = staff.cookies.get("jwt")
                assert (await staff.post("/logout")).status_code == 200
                assert (await staff.get("/me", headers={"Cookie": f"jwt={cookie}"})).status_code == 401
                assert (
                    await staff.post(
                        "/login", json={"email": ADMIN_EMAIL}, headers={"Origin": "https://foreign.example.test"}
                    )
                ).status_code == 403
                no_proof = await staff.post("/login", json={"email": ADMIN_EMAIL})
                assert no_proof.status_code == 200
                assert "jwt=;" in no_proof.headers.get("set-cookie", "")

        finally:
            await stop(bff_process)
            await stop(db_process)
