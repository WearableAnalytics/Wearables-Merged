import time
from uuid import uuid4

import pytest
from authlib.jose import JsonWebToken
from fastapi.testclient import TestClient

from app import security
from app.main import create_app


class Archive:
    def __init__(self):
        self.upload = None
        self.fail = False

    async def accept(self, upload):
        if self.fail:
            raise OSError("simulated archive failure")
        self.upload = upload
        return upload["id"], False

    async def receipt(self, upload_id, claims):
        return {"acceptanceId": upload_id, "status": "archived", "brokerConfirmedCount": 0}


@pytest.fixture
def api(settings, claims, monkeypatch):
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    app = create_app(settings)
    archive = Archive()
    app.state.repository = archive
    token_claims = {
        "iss": settings.registration_issuer,
        "type": "case-verification",
        "exp": int(time.time()) + 600,
        "sub": claims["caseId"],
        **claims,
    }

    def token(changes=None):
        value = {**token_claims, **(changes or {})}
        return JsonWebToken(["HS256"]).encode({"alg": "HS256"}, value, settings.jwt_secret).decode()

    return TestClient(app), archive, token


def test_receipt_is_only_returned_after_archive_commit(api, batch):
    client, archive, token = api
    response = client.post("/ingest", json=batch, headers={"Authorization": "Bearer " + token()})
    assert response.status_code == 202
    assert response.json()["status"] == "archived"
    assert response.json()["brokerConfirmedCount"] == 0
    assert archive.upload is not None


def test_archive_failure_is_retryable_not_a_success(api, batch):
    client, archive, token = api
    archive.fail = True
    response = client.post("/ingest", json=batch, headers={"Authorization": "Bearer " + token()})
    assert response.status_code == 503 and "acceptanceId" not in response.json()


@pytest.mark.parametrize(
    "changes", [{"exp": 1}, {"exp": None}, {"type": "session"}, {"patientId": "not-an-id"}, {"caseId": str(uuid4())}]
)
def test_upload_requires_a_current_correctly_bound_case_token(api, batch, changes):
    client, archive, token = api
    response = client.post("/ingest", json=batch, headers={"Authorization": "Bearer " + token(changes)})
    assert response.status_code == 401
    assert archive.upload is None


def test_oversized_body_is_rejected_before_archival(api, batch, settings):
    client, archive, token = api
    batch["unused"] = "x" * settings.max_body_bytes
    response = client.post("/ingest", json=batch, headers={"Authorization": "Bearer " + token()})
    assert response.status_code == 413 and archive.upload is None
