"""Account authority and patient metadata deny rules. Synthetic identities only."""

from uuid import UUID, uuid7

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.postgres.orm import ControlAudit, ControlPassword, ControlUser
from app.services.password_service import PasswordService

pytestmark = pytest.mark.anyio

HEADERS = {"X-Control-Service-Token": "synthetic-account-writer"}
ADMIN_EMAIL = "admin@example.test"


@pytest.fixture(autouse=True)
def account_config(monkeypatch):
    monkeypatch.setattr(settings, "CONTROL_WRITE_TOKEN", HEADERS["X-Control-Service-Token"])
    monkeypatch.setattr(settings, "CONTROL_READ_TOKEN", "synthetic-account-reader")
    monkeypatch.setattr(settings, "CONTROL_BOOTSTRAP_ADMIN_EMAILS", ADMIN_EMAIL)


TEMP = "Synthetic-Staff-Setup-Password-2026!"
PERSONAL = "Synthetic-Staff-Personal-Password-2026!"
ADMIN_PASSWORD = "Synthetic-Admin-Password-2026!"


async def create(client, email="staff@example.test", roles=None):
    admin = (await client.get("/control/users", headers=HEADERS, params={"email": ADMIN_EMAIL})).json()["items"][0]
    response = await client.post(
        "/control/users",
        headers=HEADERS,
        json={
            **actor(admin),
            "email": email,
            "roles": roles or ["practitioner"],
            "temporary_password": TEMP,
        },
    )
    assert response.status_code == 201, response.text
    assert TEMP not in response.text and "password_hash" not in response.text
    return response.json()


def actor(user):
    return {"actor_id": user["id"], "actor_auth_version": user["auth_version"]}


async def patch(client, user, admin, **values):
    return await client.patch(
        f"/control/users/{user['id']}",
        headers=HEADERS,
        json={**actor(admin), "expected_revision": user["revision"], **values},
    )


@pytest.fixture
async def admin(db_session):
    return (await PasswordService(db_session).bootstrap(ADMIN_EMAIL, ADMIN_PASSWORD)).model_dump(mode="json")


@pytest.fixture
async def approved(client, admin):
    user = await create(client)
    response = await client.post(
        "/control/password/setup",
        headers=HEADERS,
        json={**actor(user), "current_password": TEMP, "new_password": PERSONAL},
    )
    assert response.status_code == 200 and response.json()["allowed"], response.text
    return response.json()["user"]


@pytest.fixture
async def case(patient_factory, case_factory):
    patient = await patient_factory(dob=None)
    return await case_factory(patient_id=patient["id"])


async def assign(client, admin, case, user, revision=0, **values):
    return await client.put(
        f"/control/case-access/{case['id']}/{user['id']}",
        headers=HEADERS,
        json={
            **actor(admin),
            "expected_revision": revision,
            "active": True,
            "purpose": "clinical-reference",
            "scopes": ["read"],
            "reason": "Synthetic access review",
            **values,
        },
    )


async def decision(client, user, case, scope="read"):
    return await client.post(
        "/control/decisions/case-access",
        headers=HEADERS,
        json={**actor(user), "case_id": str(case["id"]), "scope": scope},
    )


async def test_account_creation_requires_admin_and_bootstrap_is_not_http(client, admin, approved):
    for path in ["/control/users/bootstrap", "/control/login-challenges", "/control/login-challenges/consume"]:
        response = await client.post(path, headers=HEADERS, json={"email": "outsider@example.test"})
        assert response.status_code == 410
    actorless = await client.post(
        "/control/users",
        headers=HEADERS,
        json={"email": "outsider@example.test", "roles": ["practitioner"], "temporary_password": TEMP},
    )
    assert actorless.status_code == 422 and TEMP not in actorless.text
    response = await client.post(
        "/control/users",
        headers=HEADERS,
        json={
            **actor(approved),
            "email": "outsider@example.test",
            "roles": [],
            "is_admin": True,
            "temporary_password": TEMP,
        },
    )
    assert response.status_code == 403


async def test_bootstrap_never_replaces_existing_authority_or_password(client, admin, db_session):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        await PasswordService(db_session).bootstrap(ADMIN_EMAIL, "Another-long-synthetic-password!")
    assert error.value.status_code == 409
    assert (await patch(client, admin, admin, status="denied")).status_code == 409
    other = await create(client, "other-admin@example.test")
    other = (await patch(client, other, admin, is_admin=True)).json()
    # Admin authority also requires completion of that named person's password setup.
    assert (await patch(client, admin, other, status="denied")).status_code == 403
    setup = await client.post(
        "/control/password/setup",
        headers=HEADERS,
        json={**actor(other), "current_password": TEMP, "new_password": "Other-Synthetic-Admin-Personal-Password!"},
    )
    assert setup.status_code == 200 and setup.json()["allowed"]
    other = setup.json()["user"]
    response = await patch(client, admin, other, status="denied")
    assert response.status_code == 200, response.text
    denied = response.json()
    with pytest.raises(HTTPException):
        await PasswordService(db_session).bootstrap(ADMIN_EMAIL, ADMIN_PASSWORD)
    persisted = (await client.get(f"/control/users/{admin['id']}", headers=HEADERS)).json()
    assert persisted["status"] == "denied" and persisted["auth_version"] == denied["auth_version"]


async def test_persisted_authority_revision_and_stale_actor(client, admin, approved):
    old = approved
    changed = await patch(client, approved, admin, status="denied")
    assert changed.status_code == 200
    assert changed.json()["auth_version"] == old["auth_version"] + 1
    stale = await patch(client, old, admin, status="approved")
    assert stale.status_code == 409
    response = await client.post(
        "/control/decisions/user", headers=HEADERS, json={"user_id": old["id"], "auth_version": old["auth_version"]}
    )
    assert response.json()["allowed"] is False
    stale_self = await patch(client, changed.json(), old, name="Cannot update")
    assert stale_self.status_code == 403
    self_grant = await patch(client, admin, approved, is_admin=True)
    assert self_grant.status_code == 403


async def test_logout_revokes_all_current_sessions(client, approved):
    response = await client.post(
        f"/control/users/{approved['id']}/revoke-sessions",
        headers=HEADERS,
        json={**actor(approved), "expected_auth_version": approved["auth_version"]},
    )
    assert response.status_code == 200 and response.json()["auth_version"] == approved["auth_version"] + 1
    replay = await client.post(
        f"/control/users/{approved['id']}/revoke-sessions",
        headers=HEADERS,
        json={**actor(approved), "expected_auth_version": approved["auth_version"]},
    )
    assert replay.status_code == 403


@pytest.mark.parametrize("who", ["admin", "staff"])
async def test_no_implicit_case_access_even_for_admin(client, admin, approved, case, who):
    user = admin if who == "admin" else approved
    assert (await decision(client, user, case)).json()["allowed"] is False
    response = await client.get("/control/clinical-cases", headers=HEADERS, params=actor(user))
    assert response.status_code == 200 and response.json()["items"] == []
    response = await client.get(f"/control/clinical-cases/{case['id']}", headers=HEADERS, params=actor(user))
    assert response.status_code == 403


async def test_case_assignment_metadata_export_scope_and_revocation(client, admin, approved, case, db_session):
    result = await assign(client, admin, case, approved)
    assert result.status_code == 200, result.text
    assert (await decision(client, approved, case)).json()["allowed"] is True
    assert (await decision(client, approved, case, "export")).json()["allowed"] is False
    metadata = await client.get(f"/control/clinical-cases/{case['id']}", headers=HEADERS, params=actor(approved))
    assert metadata.status_code == 200 and metadata.json()["patient"]["dob"] is None
    stale = await assign(client, admin, case, approved)
    assert stale.status_code == 409
    updated = await assign(client, admin, case, approved, revision=1, scopes=["read", "export"])
    assert updated.status_code == 200 and (await decision(client, approved, case, "export")).json()["allowed"] is True
    revoked = await assign(client, admin, case, approved, revision=2, active=False)
    assert revoked.status_code == 200 and (await decision(client, approved, case)).json()["allowed"] is False
    logs = list(await db_session.scalars(select(ControlAudit).where(ControlAudit.operation == "case.access")))
    assert len(logs) == 3 and all(log.reason == "Synthetic access review" for log in logs)


async def test_relinked_patient_role_loss_and_stale_admin_deny(client, admin, approved, case, patient_factory):
    assert (await assign(client, admin, case, approved)).status_code == 200
    replacement = await patient_factory()
    assert (await client.patch(f"/cases/{case['id']}", json={"patient_id": str(replacement["id"])})).status_code == 200
    assert (await decision(client, approved, case)).json()["allowed"] is False
    assert (await assign(client, admin, case, approved, revision=1)).status_code == 200
    changed = (await patch(client, approved, admin, roles=["researcher"])).json()
    assert (await decision(client, changed, case)).json()["allowed"] is False
    newer_admin = await client.post(
        f"/control/users/{admin['id']}/revoke-sessions",
        headers=HEADERS,
        json={**actor(admin), "expected_auth_version": admin["auth_version"]},
    )
    assert newer_admin.status_code == 200
    assert (await assign(client, admin, case, changed, revision=2)).status_code == 403


@pytest.mark.parametrize("scopes", [["export"], ["read", "read"], ["unknown"], []])
async def test_invalid_assignment_scopes_rejected(client, admin, approved, case, scopes):
    assert (await assign(client, admin, case, approved, scopes=scopes)).status_code == 422


async def test_workload_and_operator_boundaries(client, monkeypatch):
    # The standard test client has explicit operator credentials for old API tests.
    for path in ["/patients", "/cases", "/telemetry", "/graphql", "/api-tokens/"]:
        response = await client.get(path, headers={"X-Legacy-Operator-Token": "", "X-Api-Token-Service-Token": ""})
        assert response.status_code == 401, (path, response.text)
    assert (await client.get("/control/users")).status_code == 401
    assert (
        await client.get("/control/users", headers={"X-Control-Service-Token": "synthetic-account-reader"})
    ).status_code == 401
    monkeypatch.setattr(settings, "CONTROL_WRITE_TOKEN", settings.LEGACY_OPERATOR_TOKEN)
    assert (await client.get("/control/users", headers=HEADERS)).status_code == 503


async def test_non_admin_cannot_assign(client, admin, approved, case):
    assert (await assign(client, approved, case, approved)).status_code == 403
    assert (await assign(client, admin, {"id": str(uuid7())}, approved)).status_code == 404


async def test_control_requests_are_bounded_and_metadata_is_not_cacheable(client, admin):
    response = await client.get("/control/users", headers=HEADERS)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    response = await client.post("/control/users", headers=HEADERS, content=b"x" * 65_537)
    assert response.status_code == 413 and "xxxxx" not in response.text

    async def chunks():
        yield b"x" * 32_769
        yield b"y" * 32_769

    response = await client.post("/control/users", headers=HEADERS, content=chunks())
    assert response.status_code == 413


async def test_legacy_websocket_cannot_bypass_current_authority(app):
    messages = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        messages.append(message)

    await app({"type": "websocket", "path": "/graphql", "root_path": "", "headers": []}, receive, send)
    assert messages == [{"type": "websocket.close", "code": 1008}]


async def password_login(client, email, password):
    return await client.post("/control/password/login", headers=HEADERS, json={"email": email, "password": password})


async def test_passwords_are_hashed_and_first_change_invalidates_setup_authority(client, admin, db_session):
    approved = await create(client)
    row = await db_session.get(ControlPassword, UUID(approved["id"]))
    assert row.password_hash.startswith("$argon2id$") and TEMP not in row.password_hash and row.must_change
    assert (await password_login(client, approved["email"], "incorrect password")).json()["allowed"] is False
    result = (await password_login(client, approved["email"], TEMP)).json()
    assert result["allowed"] and result["password_change_required"]
    changed = await client.post(
        "/control/password/setup",
        headers=HEADERS,
        json={**actor(approved), "current_password": TEMP, "new_password": "Personal-Synthetic-New-Password-2026!"},
    )
    assert changed.status_code == 200 and changed.json()["allowed"]
    assert changed.json()["user"]["auth_version"] == approved["auth_version"] + 1
    assert not changed.json()["password_change_required"]
    assert (await password_login(client, approved["email"], TEMP)).json()["allowed"] is False
    result = (await password_login(client, approved["email"], "Personal-Synthetic-New-Password-2026!")).json()
    assert result["allowed"] and not result["password_change_required"]
    repeated = await client.post(
        "/control/password/setup",
        headers=HEADERS,
        json={**actor(approved), "current_password": TEMP, "new_password": "Another-Synthetic-New-Password-2026!"},
    )
    assert repeated.status_code == 403


async def test_password_lockout_persists_and_admin_reset_revokes_sessions(client, admin, approved):
    for _ in range(5):
        assert not (await password_login(client, approved["email"], "Wrong-Synthetic-Password-2026!")).json()["allowed"]
    assert not (await password_login(client, approved["email"], TEMP)).json()["allowed"]
    response = await client.post(
        f"/control/users/{approved['id']}/password-reset",
        headers=HEADERS,
        json={
            **actor(admin),
            "expected_revision": approved["revision"],
            "temporary_password": "Reset-Synthetic-Temporary-Password-2026!",
        },
    )
    assert response.status_code == 200 and response.json()["auth_version"] == approved["auth_version"] + 1
    assert not (await password_login(client, approved["email"], TEMP)).json()["allowed"]
    result = (await password_login(client, approved["email"], "Reset-Synthetic-Temporary-Password-2026!")).json()
    assert result["allowed"] and result["password_change_required"]
    stale = await client.post(
        f"/control/users/{approved['id']}/password-reset",
        headers=HEADERS,
        json={**actor(admin), "expected_revision": approved["revision"], "temporary_password": TEMP},
    )
    assert stale.status_code == 409


async def test_credential_resets_require_current_admin_and_do_not_replace_self_password(client, admin, approved):
    body = {"expected_revision": admin["revision"], "temporary_password": TEMP}
    assert (
        await client.post(
            f"/control/users/{admin['id']}/password-reset", headers=HEADERS, json={**body, **actor(approved)}
        )
    ).status_code == 403
    assert (
        await client.post(
            f"/control/users/{admin['id']}/password-reset", headers=HEADERS, json={**body, **actor(admin)}
        )
    ).status_code == 403
    body.update(
        expected_revision=approved["revision"], actor_id=admin["id"], actor_auth_version=admin["auth_version"] - 1
    )
    assert (
        await client.post(f"/control/users/{approved['id']}/password-reset", headers=HEADERS, json=body)
    ).status_code == 403


async def test_missing_unknown_denied_and_expired_credentials_do_not_authenticate(client, admin, db_session):
    approved = await create(client)
    from datetime import UTC, datetime, timedelta

    assert not (await password_login(client, "unknown@example.test", TEMP)).json()["allowed"]
    row = await db_session.get(ControlPassword, UUID(approved["id"]))
    row.temporary_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.commit()
    assert not (await password_login(client, approved["email"], TEMP)).json()["allowed"]
    assert (await patch(client, approved, admin, status="denied")).status_code == 200
    assert not (await password_login(client, approved["email"], TEMP)).json()["allowed"]


async def test_password_capacity_is_bounded(client, admin, monkeypatch):
    import asyncio

    from app.core import passwords

    monkeypatch.setattr(passwords, "SLOTS", asyncio.Semaphore(0))
    response = await password_login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert response.status_code == 503 and ADMIN_PASSWORD not in response.text


async def test_operator_recovery_changes_credentials_without_restoring_authority(client, admin, db_session):
    from fastapi import HTTPException

    recovered = await PasswordService(db_session).bootstrap(
        ADMIN_EMAIL, TEMP, reset=True, reason="Synthetic administrator recovery"
    )
    assert recovered.auth_version == admin["auth_version"] + 1 and recovered.roles == [] and recovered.is_admin
    assert not (await password_login(client, ADMIN_EMAIL, ADMIN_PASSWORD)).json()["allowed"]
    assert (await password_login(client, ADMIN_EMAIL, TEMP)).json()["password_change_required"]
    # The operator tool also cannot silently restore a denied administrator.
    await db_session.rollback()
    user = await db_session.get(ControlUser, UUID(admin["id"]))
    user.status = "denied"
    await db_session.commit()
    with pytest.raises(HTTPException):
        await PasswordService(db_session).bootstrap(
            ADMIN_EMAIL, ADMIN_PASSWORD, reset=True, reason="Denied account remains denied"
        )


async def test_unfinished_admin_setup_does_not_replace_the_last_usable_admin(client, admin):
    other = await create(client, "second-admin@example.test")
    promoted = await patch(client, other, admin, is_admin=True)
    assert promoted.status_code == 200
    assert (await patch(client, admin, admin, status="denied")).status_code == 409


async def test_password_validation_does_not_echo_secrets_behind_a_proxy_prefix(app):
    from httpx import ASGITransport, AsyncClient

    secret = "Synthetic-secret-that-must-not-be-returned-" * 12
    async with AsyncClient(
        transport=ASGITransport(app=app, root_path="/database"), base_url="http://test/database"
    ) as prefixed:
        response = await prefixed.post(
            "/control/password/login", headers=HEADERS, json={"email": ADMIN_EMAIL, "password": secret}
        )
    assert response.status_code == 422 and secret not in response.text
    assert response.json() == {"detail": "CONTROL_INVALID_REQUEST"}
