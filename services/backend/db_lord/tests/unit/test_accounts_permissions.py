"""Account authority and patient metadata deny rules. Synthetic identities only."""

from uuid import uuid7

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.postgres.orm import ControlAudit, LoginChallenge

pytestmark = pytest.mark.anyio

HEADERS = {"X-Control-Service-Token": "synthetic-account-writer"}
ADMIN_EMAIL = "admin@example.test"


@pytest.fixture(autouse=True)
def account_config(monkeypatch):
    monkeypatch.setattr(settings, "CONTROL_WRITE_TOKEN", HEADERS["X-Control-Service-Token"])
    monkeypatch.setattr(settings, "CONTROL_READ_TOKEN", "synthetic-account-reader")
    monkeypatch.setattr(settings, "CONTROL_BOOTSTRAP_ADMIN_EMAILS", ADMIN_EMAIL)


async def create(client, email="staff@example.test", roles=None, bootstrap=False):
    response = await client.post(
        "/control/users/bootstrap" if bootstrap else "/control/users",
        json={"email": email, "roles": roles or []},
        headers=HEADERS,
    )
    assert response.status_code in (200, 201), response.text
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
async def admin(client):
    return await create(client, ADMIN_EMAIL, bootstrap=True)


@pytest.fixture
async def approved(client, admin):
    pending = await create(client, roles=["practitioner"])
    response = await patch(client, pending, admin, status="approved", roles=["practitioner"])
    assert response.status_code == 200, response.text
    return response.json()


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


async def test_registration_never_grants_requested_role_or_admin(client):
    user = await create(client, roles=["practitioner", "researcher"])
    assert user["status"] == "pending" and not user["is_admin"] and user["roles"] == []
    assert user["request_state"]["roleRequestStatuses"] == {"practitioner": "pending", "researcher": "pending"}
    response = await client.post("/control/users/bootstrap", headers=HEADERS, json={"email": "outsider@example.test"})
    assert response.status_code == 403
    response = await client.post("/control/users", headers=HEADERS, json={"email": "a@example.test", "is_admin": True})
    assert response.status_code == 422
    assert "a@example.test" not in response.text


async def test_bootstrap_is_insert_only_and_normalized(client, admin):
    same = await create(client, " ADMIN@EXAMPLE.TEST ", bootstrap=True)
    assert same["id"] == admin["id"] and same["revision"] == 1
    assert (await patch(client, admin, admin, status="denied")).status_code == 409
    other = await create(client, "other-admin@example.test")
    other = (await patch(client, other, admin, status="approved", is_admin=True)).json()
    denied = (await patch(client, admin, other, status="denied")).json()
    same = await create(client, ADMIN_EMAIL, bootstrap=True)
    assert same["status"] == "denied" and same["auth_version"] == denied["auth_version"]


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


async def test_login_proof_one_use_reissue_and_authority_change(client, admin, approved, db_session):
    async def issue(digest):
        return await client.post(
            "/control/login-challenges",
            headers=HEADERS,
            json={
                "user_id": approved["id"],
                "auth_version": approved["auth_version"],
                "token_hash": digest,
                "ttl_seconds": 60,
            },
        )

    async def consume(digest):
        return await client.post("/control/login-challenges/consume", headers=HEADERS, json={"token_hash": digest})

    assert (await issue("a" * 64)).status_code == 200
    assert (await consume("a" * 64)).status_code == 200
    assert (await consume("a" * 64)).status_code == 403
    assert (await issue("b" * 64)).status_code == 200
    assert (await issue("c" * 64)).status_code == 200
    assert (await consume("b" * 64)).status_code == 403
    assert (await patch(client, approved, admin, status="denied")).status_code == 200
    assert (await consume("c" * 64)).status_code == 403
    records = list(await db_session.scalars(select(LoginChallenge)))
    assert len(records) == 1 and records[0].token_hash == "c" * 64


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
