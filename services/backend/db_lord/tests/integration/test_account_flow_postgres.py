"""Real PostgreSQL and two BFF instances; synthetic identities, no email delivery."""

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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.core.config import settings
from app.db.postgres.orm import ControlUser
from app.schemas.control import LoginChallengeCreate, UserCreate, UserPatch
from app.services.auth_attempts import AuthAttempts
from app.services.control_service import ControlService
from app.services.login_challenge import LoginChallengeService

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[2]
ADMIN_EMAIL = "admin@example.test"
HEADERS = {"X-Control-Service-Token": "synthetic-integration-account-writer-32"}
pytestmark = pytest.mark.anyio


@pytest.fixture
async def account_engine(monkeypatch):
    monkeypatch.setattr(settings, "CONTROL_BOOTSTRAP_ADMIN_EMAILS", ADMIN_EMAIL + ",second@example.test")
    with PostgresContainer("postgres:18", driver="asyncpg").with_bind_ports(5432, ("127.0.0.1", None)) as postgres:
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "alembic"))
        config.set_main_option("sqlalchemy.url", postgres.get_connection_url())
        await asyncio.to_thread(command.upgrade, config, "7c2e9d4b1a6f")
        engine = create_async_engine(postgres.get_connection_url())
        async with engine.begin() as db:
            patient = (
                await db.execute(
                    text("INSERT INTO patients(charite_id,name) VALUES(uuidv7(),'Synthetic Person') RETURNING id")
                )
            ).scalar_one()
            case = (
                await db.execute(
                    text("INSERT INTO cases(patient_id,status) VALUES(:patient,'ONGOING') RETURNING id"),
                    {"patient": patient},
                )
            ).scalar_one()
        await asyncio.to_thread(command.upgrade, config, "head")
        try:
            yield engine, config, patient, case
        finally:
            await engine.dispose()


async def test_account_migration_preserves_cases_and_is_reversible(account_engine):
    engine, config, patient, case = account_engine
    for revision in ("7c2e9d4b1a6f", "head"):
        await asyncio.to_thread(command.downgrade if revision != "head" else command.upgrade, config, revision)
        async with engine.connect() as db:
            assert await db.scalar(text("SELECT patient_id FROM cases WHERE id=:id"), {"id": case}) == patient
            tables = set(await db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname='public'")))
            assert "control_passwords" not in tables and "case_access" not in tables
            assert ("control_users" in tables) == (revision == "head")


async def test_shared_admin_guard_login_proof_and_auth_limits(account_engine):
    engine, _, _, _ = account_engine
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        a = await ControlService(db).create_user(UserCreate(email=ADMIN_EMAIL), bootstrap=True)
        b = await ControlService(db).create_user(UserCreate(email="second@example.test"), bootstrap=True)

    async def demote(actor, target):
        async with sessions() as db:
            try:
                await ControlService(db).patch_user(
                    target.id,
                    UserPatch(
                        actor_id=actor.id,
                        actor_auth_version=actor.auth_version,
                        expected_revision=target.revision,
                        is_admin=False,
                        roles=["practitioner"],
                    ),
                )
                return 200
            except HTTPException as error:
                return error.status_code
            except Exception as error:
                if "LAST_ACTIVE_ADMIN" in str(error):
                    return 409
                raise

    result = await asyncio.gather(demote(a, b), demote(b, a))
    assert result.count(200) == 1
    async with sessions() as db:
        active = (await db.scalars(select(ControlUser).where(ControlUser.is_admin.is_(True)))).one()
        active_id, version = active.id, active.auth_version
        await db.rollback()
        await LoginChallengeService(db).issue(
            LoginChallengeCreate(token_hash="a" * 64, user_id=active_id, auth_version=version, ttl_seconds=60)
        )

    async def consume():
        async with sessions() as db:
            try:
                await LoginChallengeService(db).consume("a" * 64)
                return 200
            except HTTPException as error:
                return error.status_code

    assert sorted(await asyncio.gather(consume(), consume())) == [200, 403]

    async def admit():
        async with sessions() as db:
            return (await AuthAttempts(db).admit("login", "b" * 64))["allowed"]

    allowed = await asyncio.gather(*(admit() for _ in range(12)))
    assert sum(allowed) == 10


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def stop(process):
    if process and process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()


async def wait_http(url, process):
    async with httpx.AsyncClient() as client:
        for _ in range(100):
            assert process.returncode is None, "Review process exited; inspect temporary logs"
            try:
                if (await client.get(url)).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.1)
    raise AssertionError("Review process readiness timeout")


async def test_real_bff_registration_approval_shared_sessions_and_existing_case_access(account_engine, tmp_path):
    engine, _, patient, case = account_engine
    db_port, first_port, second_port = port(), port(), port()
    db_url, first, second = (
        f"http://127.0.0.1:{db_port}",
        f"http://127.0.0.1:{first_port}",
        f"http://127.0.0.1:{second_port}",
    )
    origin = "http://127.0.0.1:5199"
    url = engine.url
    common = {
        **os.environ,
        "CONTROL_WRITE_TOKEN": HEADERS["X-Control-Service-Token"],
        "CONTROL_READ_TOKEN": "",
        "API_TOKEN_SERVICE_TOKEN": "synthetic-api-token-service-credential-32",
        "LEGACY_OPERATOR_TOKEN": "synthetic-private-database-operator-32",
        "CONTROL_BOOTSTRAP_ADMIN_EMAILS": ADMIN_EMAIL,
    }
    db_env = {
        **common,
        "POSTGRES_SERVER": url.host,
        "POSTGRES_PORT": str(url.port),
        "POSTGRES_DB": url.database,
        "POSTGRES_USER": url.username,
        "POSTGRES_PASSWORD": url.password,
    }
    bff_env = {
        **common,
        "NODE_ENV": "development",
        "API_PREFIX": "/api",
        "USE_MOCK_DATA": "false",
        "LOG_LEVEL": "error",
        "FRONTEND_REDIRECT_URL": origin,
        "FRONTEND_ORIGINS": origin,
        "DATABASE_API_URL": db_url,
        "DATABASE_API_TIMEOUT": "5000",
        "AUTH_SESSION_EXPIRY_SECONDS": "3600",
        "MAGIC_LINK_EXPIRY_SECONDS": "600",
        "TOKEN_ISSUER": "account-scope-integration",
        "JWT_SECRET": "synthetic-shared-session-signing-secret-32",
        "ALLOW_DEV_AUTH_BYPASS": "false",
        "ADMIN_EMAILS": ADMIN_EMAIL,
        "DATABASE_OPERATOR_TOKEN": common["LEGACY_OPERATOR_TOKEN"],
        "BREVO_API_KEY": "disabled",
    }
    processes = []
    with (tmp_path / "runtime.log").open("w") as log:
        try:
            process = await asyncio.create_subprocess_exec(
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
                stdout=log,
                stderr=log,
            )
            processes.append(process)
            await wait_http(db_url + "/livez", process)
            for api_port in (first_port, second_port):
                peer = f"http://127.0.0.1:{api_port}"
                process = await asyncio.create_subprocess_exec(
                    shutil.which("node"),
                    "--import",
                    "tsx",
                    "src/server.ts",
                    cwd=WORKSPACE / "services/backend/wearables-bff",
                    env={**bff_env, "PORT": str(api_port), "BACKEND_URL": peer},
                    stdout=log,
                    stderr=log,
                )
                processes.append(process)
                await wait_http(peer + "/api/health", process)
            async with (
                httpx.AsyncClient(base_url=db_url, headers=HEADERS) as authority,
                httpx.AsyncClient(base_url=first + "/api", headers={"Origin": origin}) as admin,
                httpx.AsyncClient(base_url=second + "/api", headers={"Origin": origin}) as staff,
            ):

                async def account(email):
                    return (await authority.get("/control/users", params={"email": email})).json()["items"][0]

                async def sign_in(client, email):
                    row = await account(email)
                    token = secrets.token_hex(32)
                    response = await authority.post(
                        "/control/login-challenges",
                        json={
                            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
                            "user_id": row["id"],
                            "auth_version": row["auth_version"],
                            "ttl_seconds": 60,
                        },
                    )
                    assert response.status_code == 200
                    response = await client.get("/verify-magiclink", params={"token": token})
                    assert response.status_code == 302
                    assert (await client.get("/me")).status_code == 200
                    replay = await client.get("/verify-magiclink", params={"token": token})
                    assert replay.status_code == 302 and replay.headers["location"].endswith("/error-magic_link")

                assert (await staff.get("/patients")).status_code == 401
                assert (
                    await staff.post(
                        "/register",
                        json={
                            "email": "clinical@example.test",
                            "role": "practitioner",
                            "isAdmin": True,
                            "status": "approved",
                        },
                    )
                ).status_code == 202
                row = await account("clinical@example.test")
                assert row["status"] == "pending" and row["roles"] == [] and not row["is_admin"]
                pending = await staff.post("/login", json={"email": row["email"]})
                unknown = await staff.post("/login", json={"email": "unknown@example.test"})
                assert pending.json() == unknown.json() and "jwt" not in staff.cookies
                await sign_in(admin, ADMIN_EMAIL)
                response = await admin.post(
                    "/admin/users/" + row["id"] + "/approve", json={"expectedRevision": row["revision"]}
                )
                assert response.status_code == 200, response.text
                stale = await admin.patch(
                    "/admin/users/" + row["id"], json={"roles": ["researcher"], "expectedRevision": row["revision"]}
                )
                assert stale.status_code == 409
                await sign_in(staff, row["email"])
                assert (await staff.get("/patients")).status_code == 200
                assert (await staff.get("/cases/" + str(case))).status_code == 200
                assert (await staff.get("/admin/pending-users")).status_code == 403
                assert (await staff.get("/extraction/test")).status_code == 403
                assert (
                    await staff.post("/cases/from-hospital-case", json={"hospitalCaseId": "C-123456"})
                ).status_code in (200, 201)
                # The second BFF accepts the first BFF's session from current shared authority.
                response = await staff.get(first + "/api/me")
                assert response.status_code == 200
                response = await staff.post("/request-role", json={"role": "researcher"})
                assert response.status_code == 200
                requests = (await admin.get("/admin/pending-access-requests")).json()["users"]
                assert any(r["email"] == row["email"] for r in requests)
                row = await account(row["email"])
                assert (
                    await admin.post("/admin/users/" + row["id"] + "/deny", json={"expectedRevision": row["revision"]})
                ).status_code == 200
                assert (await staff.get("/me")).status_code == 401
                assert (await authority.get("/cases")).status_code == 401
                assert (
                    await authority.get("/cases/", headers={"X-Legacy-Operator-Token": common["LEGACY_OPERATOR_TOKEN"]})
                ).status_code == 200
                assert (await admin.post("/logout")).status_code == 200
                assert (await admin.get("/me")).status_code == 401
                # Unblock returns a denied registration to pending; approval is still required.
                assert (
                    await staff.post("/register", json={"email": "rejected@example.test", "role": "researcher"})
                ).status_code == 202
                rejected = await account("rejected@example.test")
                await sign_in(admin, ADMIN_EMAIL)
                assert (
                    await admin.post(
                        "/admin/users/" + rejected["id"] + "/deny", json={"expectedRevision": rejected["revision"]}
                    )
                ).status_code == 200
                rejected = await account(rejected["email"])
                assert (
                    await admin.post(
                        "/admin/users/" + rejected["id"] + "/unblock", json={"expectedRevision": rejected["revision"]}
                    )
                ).status_code == 200
                rejected = await account(rejected["email"])
                assert rejected["status"] == "pending" and rejected["roles"] == []
                assert (
                    await admin.post(
                        "/admin/users/" + rejected["id"] + "/approve", json={"expectedRevision": rejected["revision"]}
                    )
                ).status_code == 200
                assert (await account(rejected["email"]))["roles"] == ["researcher"]
                assert (await admin.get("/me")).headers["cache-control"] == "no-store"
                # Restart one BFF. The account and its denied state survive startup/bootstrap.
                await stop(processes[-1])
                process = await asyncio.create_subprocess_exec(
                    shutil.which("node"),
                    "--import",
                    "tsx",
                    "src/server.ts",
                    cwd=WORKSPACE / "services/backend/wearables-bff",
                    env={**bff_env, "PORT": str(second_port), "BACKEND_URL": second},
                    stdout=log,
                    stderr=log,
                )
                processes.append(process)
                await wait_http(second + "/api/health", process)
                assert (await account(row["email"]))["status"] == "denied"
        finally:
            for process in reversed(processes):
                await stop(process)
