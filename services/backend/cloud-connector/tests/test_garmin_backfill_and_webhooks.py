import json
import socket
import time
import urllib.request
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from authlib.jose import JsonWebToken
from fastapi.testclient import TestClient

from app.config import get_settings
from app.kafka_publisher import CloudKafkaPublisher, get_publisher
from app.main import app
from app.outbox import OutboxQueue, get_outbox
from app.providers.garmin import GarminProvider
from app.storage import ConnectionStore, get_store

_JWT = JsonWebToken(["HS256"])
_SECRET = "garmin-test-secret"


def _make_jwt(patient_id: str = "patient-1") -> str:
    now = int(time.time())
    return _JWT.encode(
        {"alg": "HS256"},
        {
            "iss": "wearables-bff",
            "sub": "case-1",
            "caseId": "case-1",
            "patientId": patient_id,
            "type": "case-verification",
            "iat": now,
            "exp": now + 3600,
        },
        _SECRET,
    ).decode("utf-8")


@pytest.fixture()
def garmin_env(monkeypatch, tmp_path):
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", _SECRET)
    monkeypatch.setenv("JWT_ISSUER", "wearables-bff")
    monkeypatch.setenv("INTERNAL_PORT", "0")
    monkeypatch.setenv("GARMIN_CLIENT_ID", "client-abc")
    monkeypatch.setenv("GARMIN_CLIENT_SECRET", "secret-xyz")
    monkeypatch.setenv("GARMIN_BACKFILL_DELAY_SECONDS", "0")
    monkeypatch.setenv("CLOUD_CONNECTOR_OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("CLOUD_CONNECTOR_OUTBOX_POLL_INTERVAL", "0.1")
    get_settings.cache_clear()

    import app.outbox as outbox_mod

    outbox_mod._outbox_instance = None
    store = ConnectionStore(storage_path=str(tmp_path / "connections.json"))
    outbox = OutboxQueue(outbox_dir=str(tmp_path / "outbox"))
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_outbox] = lambda: outbox
    yield store
    app.dependency_overrides.clear()
    outbox_mod._outbox_instance = None
    get_settings.cache_clear()


class _FakeProducer:
    def __init__(self, remaining: int):
        self.remaining = remaining
        self.messages = []
        self.flush_calls = 0

    def produce(self, topic, key, value):
        self.messages.append((topic, key, value))

    def poll(self, timeout):
        return 0

    def flush(self, timeout=5.0):
        self.flush_calls += 1
        return self.remaining


def test_kafka_publisher_returns_false_when_flush_has_remaining_messages():
    pub = CloudKafkaPublisher()
    pub.producer = _FakeProducer(remaining=1)
    assert pub.publish_payload({"participantId": "p1", "measurements": {}}) is False

    pub.producer = _FakeProducer(remaining=0)
    assert pub.publish_payload({"participantId": "p1", "measurements": {}}) is True

    batch_prod = _FakeProducer(remaining=0)
    pub.producer = batch_prod
    delivered = pub.publish_batch(
        [
            {"participantId": "p1", "measurements": {}},
            {"participantId": "p2", "measurements": {}},
        ],
        flush_timeout=2.5,
    )
    assert delivered == 2
    assert len(batch_prod.messages) == 2
    assert batch_prod.flush_calls == 1


def test_webhook_queues_to_outbox_without_kafka_timeout_and_drains_on_recovery(garmin_env, tmp_path):
    garmin_env.save_connection(
        provider="garmin",
        patient_id="patient-1",
        provider_user_id="garmin-u1",
        access_token="tok-1",
        permissions=["HEALTH_EXPORT"],
    )

    outbox = app.dependency_overrides[get_outbox]()
    state = {"kafka_up": False, "published": []}

    class _FlakyPublisher:
        def publish_payload(self, payload, flush_timeout=5.0):
            if not state["kafka_up"]:
                return False
            state["published"].append(payload)
            return True

    app.dependency_overrides[get_publisher] = lambda: _FlakyPublisher()

    webhook_payload = {
        "dailies": [
            {
                "userId": "garmin-u1",
                "startTimeInSeconds": 1730203417,
                "durationInSeconds": 86400,
                "steps": 4200,
            }
        ]
    }
    with TestClient(app) as client:
        # Even when Kafka is down, webhook persists atomically and returns 200 without timeout
        resp = client.post("/webhooks/garmin", json=webhook_payload)
        assert resp.status_code == 200
        assert resp.json()["queued_batches"] == 1
        assert outbox.stats()["pending_count"] == 1
        assert len(state["published"]) == 0

        # Once Kafka recovers, background worker drains the persisted file automatically
        state["kafka_up"] = True
        deadline = time.time() + 2.5
        while time.time() < deadline and outbox.stats()["pending_count"] > 0:
            time.sleep(0.05)

        assert outbox.stats()["pending_count"] == 0
        assert len(state["published"]) == 1

        # Empty deregistration without health batches also returns 200
        assert client.post("/webhooks/garmin", json={}).status_code == 200
        dereg = client.post("/webhooks/garmin", json={"deregistrations": [{"userId": "garmin-u1"}]})
        assert dereg.status_code == 200
        assert dereg.json()["deregistered_users"] == 1
        assert garmin_env.get_connection("garmin", "patient-1") is None


def test_webhook_returns_503_when_outbox_capacity_exceeded(garmin_env, tmp_path):
    garmin_env.save_connection(
        provider="garmin",
        patient_id="patient-1",
        provider_user_id="garmin-u1",
        access_token="tok-1",
    )
    tiny_outbox = OutboxQueue(outbox_dir=str(tmp_path / "tiny_outbox"), max_bytes=10)
    app.dependency_overrides[get_outbox] = lambda: tiny_outbox

    client = TestClient(app)
    resp = client.post(
        "/webhooks/garmin",
        json={
            "dailies": [
                {
                    "userId": "garmin-u1",
                    "startTimeInSeconds": 1730203417,
                    "durationInSeconds": 86400,
                    "steps": 1200,
                }
            ]
        },
    )
    assert resp.status_code == 503


def test_webhook_verifies_garmin_client_id_when_enabled(monkeypatch, garmin_env):
    monkeypatch.setenv("GARMIN_VERIFY_CLIENT_ID", "true")
    get_settings.cache_clear()

    client = TestClient(app)
    assert client.post("/webhooks/garmin", json={}).status_code == 401
    assert (
        client.post(
            "/webhooks/garmin",
            json={},
            headers={"garmin-client-id": "wrong-id"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/webhooks/garmin",
            json={},
            headers={"garmin-client-id": "client-abc"},
        ).status_code
        == 200
    )


@pytest.mark.asyncio
async def test_delete_connection_refreshes_expired_token_before_deregister(monkeypatch, garmin_env):
    garmin_env.save_connection(
        provider="garmin",
        patient_id="patient-1",
        provider_user_id="garmin-u1",
        access_token="expired-tok",
        refresh_token="refresh-tok",
        expires_in=1,
    )
    # Force expired timestamp
    garmin_env._connections["garmin:patient-1"]["expires_at"] = 1

    calls = []

    async def fake_refresh(self, refresh_token):
        calls.append(("refresh", refresh_token))
        return {"access_token": "fresh-tok", "refresh_token": "refresh-tok-2", "expires_in": 3600}

    async def fake_deregister(self, access_token):
        calls.append(("deregister", access_token))
        return True

    monkeypatch.setattr(GarminProvider, "refresh_access_token", fake_refresh)
    monkeypatch.setattr(GarminProvider, "deregister_user", fake_deregister)

    client = TestClient(app)
    resp = client.delete(
        "/connections/garmin/patient-1",
        headers={"Authorization": f"Bearer {_make_jwt('patient-1')}"},
    )
    assert resp.status_code == 200
    assert calls == [("refresh", "refresh-tok"), ("deregister", "fresh-tok")]
    assert garmin_env.get_connection("garmin", "patient-1") is None


def test_history_backfill_gates_and_pre_auth_clamping(monkeypatch, garmin_env):
    now = datetime.now(timezone.utc)
    linked_at = now - timedelta(hours=2)
    garmin_env.save_connection(
        provider="garmin",
        patient_id="patient-1",
        provider_user_id="garmin-u1",
        access_token="tok-1",
        refresh_token="ref-1",
        expires_in=86400,
        permissions=["HEALTH_EXPORT"],
        allow_pre_auth_history=False,
    )
    garmin_env._connections["garmin:patient-1"]["linked_at"] = linked_at.isoformat()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {_make_jwt('patient-1')}"}

    #  Disabled in evaluation/starter mode
    resp_disabled = client.post(
        "/sync/garmin/history",
        json={"patient_id": "patient-1", "days": 7},
        headers=headers,
    )
    assert resp_disabled.status_code == 503

    # Missing HISTORICAL_DATA_EXPORT permission
    monkeypatch.setenv("GARMIN_BACKFILL_ENABLED", "true")
    get_settings.cache_clear()

    async def fake_user_info_no_hist(self, access_token):
        return {"provider_user_id": "garmin-u1", "permissions": ["HEALTH_EXPORT"]}

    monkeypatch.setattr(GarminProvider, "fetch_user_info", fake_user_info_no_hist)
    resp_no_perm = client.post(
        "/sync/garmin/history",
        json={"patient_id": "patient-1", "days": 7},
        headers=headers,
    )
    assert resp_no_perm.status_code == 403

    # Grant HISTORICAL_DATA_EXPORT, test pre-auth window strictly BEFORE linked_at gets skipped
    garmin_env.update_permissions("garmin", "garmin-u1", ["HEALTH_EXPORT", "HISTORICAL_DATA_EXPORT"])
    resp_before_link = client.post(
        "/sync/garmin/history",
        json={
            "patient_id": "patient-1",
            "start_time": (linked_at - timedelta(days=5)).isoformat(),
            "end_time": (linked_at - timedelta(minutes=5)).isoformat(),
            "allow_pre_auth": True,
        },
        headers=headers,
    )
    assert resp_before_link.status_code == 200
    body_skipped = resp_before_link.json()
    assert body_skipped["status"] == "skipped"
    assert body_skipped["pre_auth_applied"] is False

    # Enable global + per-patient pre-auth opt-in -> pre-auth backfill allowed
    monkeypatch.setenv("GARMIN_ALLOW_PRE_AUTH_HISTORY", "true")
    get_settings.cache_clear()
    toggle = client.put(
        "/connections/garmin/patient-1/pre-auth",
        json={"allow_pre_auth_history": True},
        headers=headers,
    )
    assert toggle.status_code == 200
    assert toggle.json()["allow_pre_auth_history"] is True

    captured = {}

    async def fake_request_backfill(self, **kwargs):
        captured.update(kwargs)
        return {
            "status": "triggered",
            "triggered": ["dailies"],
            "already_requested": [],
            "skipped": {},
            "failed": {},
            "auth_failed": False,
            "rate_limited": False,
        }

    monkeypatch.setattr(GarminProvider, "request_backfill", fake_request_backfill)
    pre_start = linked_at - timedelta(days=5)
    resp_allowed = client.post(
        "/sync/garmin/history",
        json={
            "patient_id": "patient-1",
            "start_time": pre_start.isoformat(),
            "end_time": now.isoformat(),
            "data_types": ["dailies"],
            "allow_pre_auth": True,
        },
        headers=headers,
    )
    assert resp_allowed.status_code == 200
    body_ok = resp_allowed.json()
    assert body_ok["status"] == "triggered"
    assert body_ok["pre_auth_applied"] is True
    assert captured["start_time"] == pre_start


@pytest.mark.asyncio
async def test_garmin_request_backfill_handles_202_409_403_and_prevents_retry_loops(tmp_path):
    store = ConnectionStore(storage_path=str(tmp_path / "store.json"))
    provider = GarminProvider()

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/backfill/dailies"):
            return httpx.Response(202)
        if request.url.path.endswith("/backfill/sleeps"):
            return httpx.Response(409)
        if request.url.path.endswith("/backfill/hrv"):
            return httpx.Response(403, text="HISTORICAL_DATA_EXPORT not allowed")
        return httpx.Response(202)

    orig_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_async_client(*args, **kwargs)

    # httpx.AsyncClient locally
    mp = pytest.MonkeyPatch()
    mp.setattr(httpx, "AsyncClient", patched_client)
    try:
        start = datetime(2026, 11, 1, tzinfo=timezone.utc)
        end = datetime(2026, 11, 3, tzinfo=timezone.utc)

        res1 = await provider.request_backfill(
            patient_id="patient-1",
            access_token="tok",
            start_time=start,
            end_time=end,
            data_types=["dailies", "sleeps", "hrv", "activities"],
            chunk_days=7,
            delay_seconds=0,
            max_attempts=3,
            should_skip_window=lambda k: store.should_skip_sync_window(k, max_attempts=3),
            record_window=store.record_sync_window,
        )
        assert res1["triggered"] == ["dailies"]
        assert res1["already_requested"] == ["sleeps"]
        assert "hrv" in res1["failed"]
        # Stopped on 403
        assert len(calls) == 3

        # Rerunning the exact same window must skip all 3 stored keys
        calls.clear()
        res2 = await provider.request_backfill(
            patient_id="patient-1",
            access_token="tok",
            start_time=start,
            end_time=end,
            data_types=["dailies", "sleeps", "hrv"],
            chunk_days=7,
            delay_seconds=0,
            max_attempts=3,
            should_skip_window=lambda k: store.should_skip_sync_window(k, max_attempts=3),
            record_window=store.record_sync_window,
        )
        assert calls == []
        assert res2["status"] == "skipped"
        assert set(res2["skipped"].keys()) == {"dailies", "sleeps", "hrv"}
    finally:
        mp.undo()


@pytest.mark.asyncio
async def test_fetch_telemetry_chunks_upload_window_at_24h():
    provider = GarminProvider()
    seen_windows = set()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/dailies"):
            s = int(request.url.params["uploadStartTimeInSeconds"])
            e = int(request.url.params["uploadEndTimeInSeconds"])
            assert e - s <= 86400
            seen_windows.add((s, e))
        return httpx.Response(200, json=[])

    orig_async_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    mp = pytest.MonkeyPatch()
    mp.setattr(httpx, "AsyncClient", lambda *a, **kw: orig_async_client(*a, transport=transport, **kw))
    try:
        start = datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=49)
        await provider.fetch_telemetry(
            patient_id="p1",
            credentials={"token": "tok"},
            start_time=start,
            end_time=end,
        )
        assert len(seen_windows) == 3
    finally:
        mp.undo()


def test_internal_garmin_readiness_endpoint(monkeypatch, garmin_env):
    import app.internal_server as internal_mod

    monkeypatch.setattr(internal_mod, "_internal_server", None)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]

    get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_PORT", str(free_port))
    monkeypatch.setenv("GARMIN_ENVIRONMENT", "production")
    monkeypatch.setenv("GARMIN_BACKFILL_ENABLED", "true")
    get_settings.cache_clear()

    try:
        internal_mod.start_internal_server()
        with urllib.request.urlopen(f"http://127.0.0.1:{free_port}/internal/garmin/readiness") as res:
            assert res.status == 200
            data = json.loads(res.read().decode("utf-8"))
        assert data["provider"] == "garmin"
        assert data["environment"] == "production"
        assert data["client_configured"] is True
        assert data["backfill_enabled"] is True
        assert "garmin_client_secret" not in json.dumps(data)
    finally:
        if internal_mod._internal_server is not None:
            internal_mod._internal_server.shutdown()
            internal_mod._internal_server.server_close()
            internal_mod._internal_server = None
        get_settings.cache_clear()
