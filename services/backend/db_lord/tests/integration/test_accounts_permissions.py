"""Independent PostgreSQL proof. Each test uses a disposable database, never Compose data."""

import asyncio
import os
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
from app.schemas.control import UserPatch
from app.schemas.passwords import PasswordChange, StaffCreate
from app.services.control_service import ControlService
from app.services.password_service import PasswordService

pytestmark = [pytest.mark.integration, pytest.mark.anyio]
ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[2]
HEADERS = {"X-Control-Service-Token": "synthetic-e2e-account-writer"}
ADMIN_EMAIL = "admin@example.test"
ADMIN_PASSWORD = "Synthetic-Admin-Personal-Password-2026!"
TEMP = "Synthetic-Staff-Temporary-Password-2026!"
PERSONAL = "Synthetic-Staff-Personal-Password-2026!"


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
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        admin = await PasswordService(db).bootstrap(ADMIN_EMAIL, ADMIN_PASSWORD)
        prior_version = admin.auth_version
    # Re-applying the credential migration invalidates old sessions without inferring a password.
    await asyncio.to_thread(command.downgrade, config, "a8e3b9d47f20")
    await asyncio.to_thread(command.upgrade, config, "head")
    async with engine.connect() as connection:
        assert (
            await connection.execute(text("SELECT auth_version FROM control_users WHERE id=:id"), {"id": admin.id})
        ).scalar_one() == prior_version + 1
        assert (await connection.execute(text("SELECT count(*) FROM control_passwords"))).scalar_one() == 0
    await asyncio.to_thread(command.downgrade, config, "7c2e9d4b1a6f")
    await check_case()
    await asyncio.to_thread(command.upgrade, config, "head")
    await check_case()


async def test_postgres_serializes_admin_and_initial_password_changes(account_engine):
    engine, _, _, _ = account_engine
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def call(service, method, *args, **kwargs):
        async with factory() as db:
            return await getattr(service(db), method)(*args, **kwargs)

    first = await call(PasswordService, "bootstrap", ADMIN_EMAIL, ADMIN_PASSWORD)
    second = await call(PasswordService, "bootstrap", "second@example.test", ADMIN_PASSWORD)
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                call(
                    ControlService,
                    "patch_user",
                    user.id,
                    UserPatch(
                        actor_id=user.id,
                        actor_auth_version=user.auth_version,
                        expected_revision=user.revision,
                        is_admin=False,
                    ),
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
        actor_id, version = current.id, current.auth_version
    staff = await call(
        PasswordService,
        "create_staff",
        StaffCreate(
            actor_id=actor_id,
            actor_auth_version=version,
            email="staff@example.test",
            roles=["practitioner"],
            temporary_password=TEMP,
        ),
    )
    results = await asyncio.wait_for(
        asyncio.gather(
            *(
                call(
                    PasswordService,
                    "change",
                    PasswordChange(
                        actor_id=staff.id,
                        actor_auth_version=staff.auth_version,
                        current_password=TEMP,
                        new_password="Synthetic-New-Personal-Password-" + suffix,
                    ),
                    initial=True,
                )
                for suffix in ("First!", "Second!")
            ),
            return_exceptions=True,
        ),
        10,
    )
    assert sum(isinstance(result, HTTPException) and result.status_code == 403 for result in results) == 1
    assert sum(not isinstance(result, Exception) and result.allowed for result in results) == 1


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


async def test_real_bff_closed_accounts_password_setup_permissions_reset_restart_and_logout(account_engine, tmp_path):
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
        "TOKEN_ISSUER": "synthetic-account-test",
        "JWT_SECRET": "synthetic-account-signing-key-at-least-32",
        "ALLOW_DEV_AUTH_BYPASS": "false",
        "BFF_TEST_MODE": "false",
    }
    db_process = bff_process = None
    with (tmp_path / "db.log").open("w") as db_log, (tmp_path / "bff.log").open("w") as bff_log:
        try:
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
            await wait_http(db_url + "/livez", db_process)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                await PasswordService(db).bootstrap(ADMIN_EMAIL, ADMIN_PASSWORD)

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
                await wait_http(bff_url + "/api/health", process)
                return process

            bff_process = await start_bff()
            async with (
                httpx.AsyncClient(base_url=db_url, headers=HEADERS) as authority,
                httpx.AsyncClient(base_url=bff_url + "/api", headers={"Origin": origin}) as admin,
                httpx.AsyncClient(base_url=bff_url + "/api", headers={"Origin": origin}) as staff,
            ):
                assert (
                    await staff.post("/register", json={"email": "outsider@example.test", "role": "practitioner"})
                ).status_code == 410
                assert (await staff.get("/verify-magiclink", params={"token": "a" * 64})).status_code == 410
                assert (await staff.post("/login", json={"email": ADMIN_EMAIL})).status_code == 400
                assert (
                    await staff.post("/login", json={"email": ADMIN_EMAIL, "password": "wrong-password"})
                ).status_code == 401
                result = await admin.post("/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
                assert result.status_code == 200 and result.json()["authenticated"]
                assert (await admin.get("/me")).json()["user"]["isAdmin"]
                creation = {
                    "email": "staff@example.test",
                    "isAdmin": False,
                    "roles": ["practitioner"],
                    "temporaryPassword": TEMP,
                }
                assert (await staff.post("/admin/users", json=creation)).status_code == 401
                created = await admin.post("/admin/users", json=creation)
                assert created.status_code == 201, created.text
                assert TEMP not in created.text and "password_hash" not in created.text
                staff_id = created.json()["user"]["id"]
                assert (await admin.post("/admin/users", json=creation)).status_code == 409
                result = await staff.post("/login", json={"email": "staff@example.test", "password": TEMP})
                assert result.status_code == 200 and result.json()["passwordChangeRequired"]
                setup_cookie = staff.cookies.get("password_setup")
                assert (await staff.get("/me")).status_code == 401
                assert (await staff.get("/patients")).status_code == 401
                result = await staff.post("/password/setup", json={"currentPassword": TEMP, "newPassword": PERSONAL})
                assert result.status_code == 200 and result.json()["authenticated"], result.text
                assert (await staff.get("/me")).json()["user"]["roles"] == ["practitioner"]
                assert (
                    await staff.post(
                        "/password/setup",
                        json={"currentPassword": TEMP, "newPassword": PERSONAL},
                        headers={"Cookie": f"password_setup={setup_cookie}"},
                    )
                ).status_code == 401
                assert (
                    await staff.post("/admin/users", json={**creation, "email": "forbidden@example.test"})
                ).status_code == 403
                assert (await staff.get("/patients")).json() == []
                assert (await staff.get(f"/cases/{case_id}")).status_code == 403
                body = {
                    "expected_revision": 0,
                    "active": True,
                    "purpose": "clinical-reference",
                    "scopes": ["read"],
                    "reason": "Synthetic case review",
                }
                assert (await staff.put(f"/admin/case-access/{case_id}/{staff_id}", json=body)).status_code == 403
                assert (await admin.put(f"/admin/case-access/{case_id}/{staff_id}", json=body)).status_code == 200
                assert (await staff.get(f"/patients/{patient_id}")).json()["birthDate"] is None
                assert (await staff.get(f"/cases/{case_id}")).json()["caseToken"] is None
                assert len((await staff.get("/cases")).json()) == 1
                assert (await staff.get("/extraction/v1/measurements")).status_code == 410
                await stop(bff_process)
                bff_process = await start_bff()
                assert (await staff.get("/me")).status_code == 200
                old_cookie = staff.cookies.get("jwt")
                record = (await authority.get(f"/control/users/{staff_id}")).json()
                reset_temp = "Synthetic-Reset-Temporary-Password-2026!"
                reset = await admin.post(
                    f"/admin/users/{staff_id}/password-reset",
                    json={"expectedRevision": record["revision"], "temporaryPassword": reset_temp},
                )
                assert reset.status_code == 200, reset.text
                assert (await staff.get("/me", headers={"Cookie": f"jwt={old_cookie}"})).status_code == 401
                assert (
                    await staff.post("/login", json={"email": "staff@example.test", "password": PERSONAL})
                ).status_code == 401
                assert (
                    await staff.post("/login", json={"email": "staff@example.test", "password": reset_temp})
                ).json()["passwordChangeRequired"]
                assert (await staff.get("/cases")).status_code == 401
                new_personal = "Synthetic-Reset-Personal-Password-2026!"
                assert (
                    await staff.post(
                        "/password/setup", json={"currentPassword": reset_temp, "newPassword": new_personal}
                    )
                ).json()["authenticated"]
                assert (
                    await staff.post(
                        "/account/password", json={"currentPassword": "incorrect-password", "newPassword": PERSONAL}
                    )
                ).status_code == 400
                assert (await staff.get("/me")).status_code == 200
                prior = staff.cookies.get("jwt")
                assert (
                    await staff.post(
                        "/account/password", json={"currentPassword": new_personal, "newPassword": PERSONAL}
                    )
                ).json()["authenticated"]
                assert (await staff.get("/me", headers={"Cookie": f"jwt={prior}"})).status_code == 401
                body.update(expected_revision=1, active=False)
                assert (await admin.put(f"/admin/case-access/{case_id}/{staff_id}", json=body)).status_code == 200
                assert (await staff.get(f"/cases/{case_id}")).status_code == 403
                assert (await staff.get("/patients")).json() == []
                cookie = staff.cookies.get("jwt")
                assert (await staff.post("/logout")).status_code == 200
                assert (await staff.get("/me", headers={"Cookie": f"jwt={cookie}"})).status_code == 401
                assert (
                    await staff.post(
                        "/login",
                        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                        headers={"Origin": "https://foreign.example.test"},
                    )
                ).status_code == 403
        finally:
            await stop(bff_process)
            await stop(db_process)
