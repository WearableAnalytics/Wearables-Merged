import csv
import io
import json
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import jwt
import pytest
import yaml
from fastapi.testclient import TestClient

from src.app.auth import PRINCIPAL_HEADER
from src.app.fhir import category_for, default_mapping
from src.app.main import app, get_db_lord_api
from src.app.schemas import TelemetryPoint
from src.app.settings import settings

PATIENT = "01a117b8-513c-72c8-8428-094abe33dbd8"
OTHER = "019c62a0-0000-0000-0000-000000000000"
T0 = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def point(minutes_ago, measurement="steps", value=10.0, *, device_id=PATIENT, reference=True, host="a", ingested=1):
    tags = {"category": "measurements.cumulative", "host": f"telegraf-{host}", "version": "1.0.0"}
    if device_id:
        tags["device-id"] = device_id
    if reference:
        tags["device-id-reference"] = f"Patient/{device_id or PATIENT}"
    return TelemetryPoint(
        measurement=measurement,
        timestamp=T0 - timedelta(minutes=minutes_ago),
        tags=tags,
        fields={"value": value, "t_ingested": ingested},
    )


class FakeDbLord:
    """Mimics db_lord's tag filtering and newest-first ordering."""

    def __init__(self, points):
        self.points = points
        self.calls = []

    async def stream_telemetry(self, *, measurement, start, end=None, tags=None):
        self.calls.append({"measurement": measurement, "start": start, "end": end, "tags": tags})
        matching = [
            p
            for p in self.points
            if (measurement is None or p.measurement == measurement)
            and p.timestamp >= start
            and (end is None or p.timestamp < end)
            and all(p.tags.get(k) == v for k, v in (tags or {}).items())
        ]
        for p in sorted(matching, key=lambda p: p.timestamp, reverse=True):
            yield p

    async def list_measurements(self):
        return [{"measurement": "steps", "fieldKeys": ["t_ingested", "value"]}]

    async def get_fhir_mapping(self, mapping_id):
        raise LookupError(mapping_id)

    async def get_dot_dependency_file(self, file_id):
        raise LookupError(file_id)


@pytest.fixture
def db_lord():
    fake = FakeDbLord(
        [
            point(0, value=5),
            # Same reading ingested twice by different Telegraf pods.
            point(10, value=7, host="a", ingested=1),
            point(10, value=7, host="b", ingested=2),
            # Older point that only carries the patient reference.
            point(20, value=9, device_id=None),
            # Old point that only carries device-id.
            point(30, value=3, reference=False),
            point(5, measurement="heart-rate", value=72),
            point(15, value=100, device_id=OTHER),
        ]
    )
    app.dependency_overrides[get_db_lord_api] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


SECRET = "test-internal-secret-of-32-bytes-ok"


def principal_token(
    roles=("researcher",), *, auth="session", role_source="verified", secret=SECRET, expires_in=60, **extra
):
    now = datetime.now(UTC)
    claims = {
        "sub": "researcher@example.com",
        "aud": "extraction-service",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "roles": list(roles),
        "auth": auth,
        "role_source": role_source,
        **extra,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def internal_secret(monkeypatch):
    monkeypatch.setattr(settings, "extraction_internal_jwt_secret", SECRET)


@pytest.fixture
def anonymous(db_lord):
    return TestClient(app)


@pytest.fixture
def client(db_lord):
    return TestClient(app, headers={PRINCIPAL_HEADER: principal_token()})


def test_patient_filter_finds_points_with_either_tag_without_duplicates(client):
    r = client.get("/v1/measurements", params={"measurement": "steps", "patient_id": PATIENT})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["value"] for i in items] == [5, 7, 9, 3]
    assert {i["patient_id"] for i in items} == {PATIENT}
    assert all("host" not in i["tags"] and "t_ingested" not in i["fields"] for i in items)


def test_without_start_all_data_is_read(client, db_lord):
    client.get("/v1/measurements", params={"measurement": "steps"})
    assert db_lord.calls[0]["start"] == datetime(2020, 1, 1, tzinfo=UTC)


def test_naive_times_are_utc_and_start_must_precede_end(client, db_lord):
    client.get("/v1/measurements", params={"start": "2026-10-01T00:00:00"})
    assert db_lord.calls[0]["start"] == datetime(2026, 10, 1, tzinfo=UTC)
    r = client.get("/v1/measurements", params={"start": "2026-10-02T00:00:00Z", "end": "2026-10-01T00:00:00Z"})
    assert r.status_code == 422


def test_paging_keeps_timestamps_together(client):
    first = client.get("/v1/measurements", params={"measurement": "steps", "limit": 1}).json()
    assert [i["value"] for i in first["items"]] == [5]
    assert first["has_more"] is True
    second = client.get(
        "/v1/measurements", params={"measurement": "steps", "limit": 1, "end": first["next_end"]}
    ).json()
    assert [i["value"] for i in second["items"]] == [7]


def test_all_measurements_of_a_patient(client):
    items = client.get("/v1/measurements", params={"patient_id": PATIENT}).json()["items"]
    assert [i["measurement"] for i in items] == ["steps", "heart-rate", "steps", "steps", "steps"]


def test_csv_export(client):
    r = client.get("/v1/measurements/export.csv", params={"measurement": "steps", "patient_id": PATIENT})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert [row["value"] for row in rows] == ["5", "7", "9", "3"]
    assert rows[0]["patient_id"] == PATIENT
    assert rows[0]["category"] == "measurements.cumulative"


def test_fhir_category_falls_back_to_the_mapping_that_knows_the_measurement():
    config = default_mapping()
    assert category_for(config, point(0, measurement="heart-rate")) == "measurements.instantaneous"
    assert category_for(config, point(0, measurement="steps")) == "measurements.cumulative"
    assert category_for(config, point(0, measurement="unknown")) == "measurements.cumulative"


def test_fhir_export_uses_default_mapping(client):
    r = client.get("/v1/measurements/export.fhir", params={"patient_id": PATIENT})
    assert r.status_code == 200
    bundle = json.loads(r.text)
    assert bundle["resourceType"] == "Bundle"
    observations = [e["resource"] for e in bundle["entry"]]
    assert len(observations) == 5
    heart_rate = next(o for o in observations if o["id"] == "heart-rate")
    assert heart_rate["resourceType"] == "Observation"
    assert heart_rate["subject"] == {"reference": f"Patient/{PATIENT}"}
    assert heart_rate["valueQuantity"]["value"] == 72
    assert heart_rate["valueQuantity"]["unit"] == "bpm"
    assert heart_rate["code"]["coding"][0]["code"] == "8867-4"
    assert heart_rate["effectiveDateTime"] == "2026-10-08T11:55:00Z"
    assert len({e["fullUrl"] for e in bundle["entry"]}) == 5


def test_measurement_types(client):
    assert client.get("/v1/measurements/types").json() == [{"measurement": "steps", "field_keys": ["value"]}]


def test_openapi_documents_auth(client):
    spec = client.get("/openapi.json").json()
    assert set(spec["components"]["securitySchemes"]) == {"researcherToken", "session"}
    assert "/v1/measurements/export.csv" in spec["paths"]
    assert client.get("/docs").status_code == 200


def test_docs_pages_are_branded(client):
    for path in ("/docs", "/redoc"):
        page = client.get(path).text
        assert "<title>Extraction API | Charité Wearables platform</title>" in page
        assert "data:image/png;base64," in page
        assert "/openapi.json" in page


def test_patient_window_is_retried_when_db_lord_drops_the_connection(client, db_lord):
    real = db_lord.stream_telemetry
    failures = iter([True])

    async def flaky(**query):
        if next(failures, False):
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        async for p in real(**query):
            yield p

    db_lord.stream_telemetry = flaky
    items = client.get("/v1/measurements", params={"measurement": "steps", "patient_id": PATIENT}).json()["items"]
    assert [i["value"] for i in items] == [5, 7, 9, 3]


MAPPER_CONFIG_MAP = (
    Path(__file__).parents[4] / "gitops/apps/services/mapper-validator/templates/mappings-config-map.yaml"
)


@pytest.mark.skipif(not MAPPER_CONFIG_MAP.exists(), reason="gitops checkout not available")
def test_default_fhir_mapping_matches_the_mapper_validator():
    body = MAPPER_CONFIG_MAP.read_text().split("mapping.yaml: |\n", 1)[1]
    mapper = yaml.safe_load(textwrap.dedent(body))
    ours = yaml.safe_load(settings.fhir_default_mapping_path.read_text())
    assert ours == mapper


DATA_PATHS = [
    "/v1/measurements",
    "/v1/measurements/types",
    "/v1/measurements/export.csv",
    "/v1/measurements/export.fhir",
]


def get(client, path, token):
    return client.get(path, headers={PRINCIPAL_HEADER: token} if token else {})


def test_every_data_route_requires_export_access():
    data_routes = {r.path for r in app.routes if r.path.startswith("/v1")}
    assert data_routes == set(DATA_PATHS)
    for route in app.routes:
        if route.path.startswith("/v1"):
            assert any(d.call.__name__ == "require_export_access" for d in route.dependant.dependencies)


@pytest.mark.parametrize("path", DATA_PATHS)
def test_data_routes_refuse_callers_without_principal(anonymous, path):
    assert get(anonymous, path, None).status_code == 401


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        principal_token(secret="other-secret-also-32-bytes-long!"),
        principal_token(expires_in=-60),
        principal_token(aud="someone-else"),
        principal_token(auth="cookie"),
        principal_token(role_source="maybe"),
    ],
    ids=["garbage", "wrong-secret", "expired", "wrong-audience", "unknown-auth", "unknown-role-source"],
)
def test_invalid_principals_are_refused(anonymous, token):
    assert get(anonymous, "/v1/measurements/export.csv", token).status_code == 401


@pytest.mark.parametrize("roles", [["researcher"], ["admin"], ["admin", "practitioner"]])
def test_admins_and_researchers_may_export(anonymous, roles):
    assert get(anonymous, "/v1/measurements/export.csv", principal_token(roles)).status_code == 200


@pytest.mark.parametrize("roles", [[], ["practitioner"]])
def test_other_roles_may_not_export(anonymous, roles):
    r = get(anonymous, "/v1/measurements/export.csv", principal_token(roles))
    assert r.status_code == 403


def test_api_token_with_unknown_owner_is_accepted_unless_disabled(anonymous, monkeypatch):
    token = principal_token([], auth="api_token", role_source="unverified", token_id="t1")
    assert get(anonymous, "/v1/measurements/export.csv", token).status_code == 200
    monkeypatch.setattr(settings, "allow_unverified_token_owners", False)
    assert get(anonymous, "/v1/measurements/export.csv", token).status_code == 403


def test_unverified_sessions_are_refused(anonymous):
    token = principal_token([], auth="session", role_source="unverified")
    assert get(anonymous, "/v1/measurements/export.csv", token).status_code == 403


def test_without_configured_secret_data_routes_are_unavailable(client, monkeypatch):
    monkeypatch.setattr(settings, "extraction_internal_jwt_secret", "")
    assert client.get("/v1/measurements").status_code == 503


def test_health_and_docs_stay_open(anonymous):
    for path in ("/health", "/docs", "/openapi.json"):
        assert anonymous.get(path).status_code == 200


def test_principal_header_is_not_documented(client):
    spec = json.dumps(client.get("/openapi.json").json())
    assert PRINCIPAL_HEADER not in spec
