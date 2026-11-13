import json
import time
import urllib.request

import pytest
from authlib.jose import JsonWebToken
from fastapi.testclient import TestClient

from app.config import get_settings
from app.internal_server import start_internal_server
from app.main import app
from app.storage import ConnectionStore, get_store

_JWT = JsonWebToken(["HS256"])
_SECRET = "unit-test-secret-value"


def _make_case_jwt(
    *,
    patient_id: str = "patient-a",
    case_id: str = "case-a",
    sub: str = "case-a",
    issuer: str = "wearables-bff",
    token_type: str = "case-verification",
    exp_offset: int = 3600,
    secret: str = _SECRET,
) -> str:
    now = int(time.time())
    header = {"alg": "HS256"}
    payload = {
        "iss": issuer,
        "sub": sub,
        "caseId": case_id,
        "patientId": patient_id,
        "type": token_type,
        "iat": now,
        "exp": now + exp_offset,
    }
    return _JWT.encode(header, payload, secret).decode("utf-8")


@pytest.fixture()
def isolated_env(monkeypatch, tmp_path):
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", _SECRET)
    monkeypatch.setenv("JWT_ISSUER", "wearables-bff")
    monkeypatch.setenv("INTERNAL_PORT", "0")
    get_settings.cache_clear()

    store = ConnectionStore(storage_path=str(tmp_path / "connections.json"))
    store.save_connection(
        provider="garmin",
        patient_id="patient-a",
        provider_user_id="garmin-user-a",
        access_token="tok-a",
        refresh_token="ref-a",
        expires_in=86400,
        permissions=["HEALTH_EXPORT"],
    )
    store.save_connection(
        provider="garmin",
        patient_id="patient-b",
        provider_user_id="garmin-user-b",
        access_token="tok-b",
        refresh_token="ref-b",
        expires_in=86400,
        permissions=["ACTIVITY_EXPORT"],
    )

    app.dependency_overrides[get_store] = lambda: store
    yield store
    app.dependency_overrides.clear()
    get_settings.cache_clear()


def test_connections_requires_auth_and_blocks_missing_secret(monkeypatch, tmp_path):
    store = ConnectionStore(storage_path=str(tmp_path / "connections.json"))
    app.dependency_overrides[get_store] = lambda: store
    try:
        get_settings.cache_clear()
        monkeypatch.setenv("JWT_SECRET", _SECRET)
        monkeypatch.setenv("INTERNAL_PORT", "0")
        get_settings.cache_clear()

        client = TestClient(app)
        resp = client.get("/connections")
        assert resp.status_code in (401, 403)

        bad_issuer = _make_case_jwt(issuer="wrong-issuer")
        assert (
            client.get(
                "/connections", headers={"Authorization": f"Bearer {bad_issuer}"}
            ).status_code
            == 401
        )

        expired = _make_case_jwt(exp_offset=-60)
        assert (
            client.get(
                "/connections", headers={"Authorization": f"Bearer {expired}"}
            ).status_code
            == 401
        )

        # Unconfigured JWT_SECRET must fail closed with 503
        monkeypatch.setenv("JWT_SECRET", "")
        get_settings.cache_clear()
        valid_token = _make_case_jwt()
        assert (
            client.get(
                "/connections", headers={"Authorization": f"Bearer {valid_token}"}
            ).status_code
            == 503
        )
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_connections_and_mutations_scoped_to_authenticated_patient(isolated_env):
    client = TestClient(app)
    token_a = _make_case_jwt(patient_id="patient-a", case_id="case-a", sub="case-a")

    # Patient A only sees Patient A, never Patient B
    resp = client.get("/connections", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    conns = resp.json()["connections"]
    assert len(conns) == 1
    assert conns[0]["patient_id"] == "patient-a"
    assert "access_token" not in conns[0]

    # Patient A cannot delete, refresh, or sync Patient B
    assert (
        client.delete(
            "/connections/garmin/patient-b",
            headers={"Authorization": f"Bearer {token_a}"},
        ).status_code
        == 403
    )
    assert isolated_env.get_connection("garmin", "patient-b") is not None

    assert (
        client.post(
            "/connections/garmin/patient-b/refresh",
            headers={"Authorization": f"Bearer {token_a}"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/sync/garmin",
            json={"patient_id": "patient-b"},
            headers={"Authorization": f"Bearer {token_a}"},
        ).status_code
        == 403
    )

    # Patient A can delete their own connection
    del_resp = client.delete(
        "/connections/garmin/patient-a",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert del_resp.status_code == 200
    assert isolated_env.get_connection("garmin", "patient-a") is None


def test_public_endpoints_and_internal_admin_server(monkeypatch, tmp_path):
    import app.internal_server as internal_mod
    import app.storage as storage_mod

    store = ConnectionStore(storage_path=str(tmp_path / "connections.json"))
    store.save_connection(
        provider="garmin",
        patient_id="patient-a",
        provider_user_id="garmin-a",
        access_token="secret-tok-a",
    )
    store.save_connection(
        provider="garmin",
        patient_id="patient-b",
        provider_user_id="garmin-b",
        access_token="secret-tok-b",
    )

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/providers").status_code == 200

    monkeypatch.setattr(internal_mod, "get_store", lambda: store)
    monkeypatch.setattr(storage_mod, "_store_instance", store)
    monkeypatch.setattr(internal_mod, "_internal_server", None)

    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]

    get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_PORT", str(free_port))
    get_settings.cache_clear()

    try:
        start_internal_server()
        assert internal_mod._internal_server is not None

        with urllib.request.urlopen(f"http://127.0.0.1:{free_port}/connections") as res:
            assert res.status == 200
            data = json.loads(res.read().decode("utf-8"))

        patient_ids = {c["patient_id"] for c in data["connections"]}
        assert patient_ids == {"patient-a", "patient-b"}
        for c in data["connections"]:
            assert "access_token" not in c
            assert "refresh_token" not in c
    finally:
        if internal_mod._internal_server is not None:
            internal_mod._internal_server.shutdown()
            internal_mod._internal_server.server_close()
            internal_mod._internal_server = None
        get_settings.cache_clear()
