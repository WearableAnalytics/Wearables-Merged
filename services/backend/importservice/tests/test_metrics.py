from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app


def _count(route, status):
    value = REGISTRY.get_sample_value(
        "importservice_http_requests_total",
        {"route": route, "method": "POST", "status": status},
    )
    return value or 0


def test_counts_requests_by_route_template_and_status():
    client = TestClient(app)
    before = _count("/ingest", "403")
    response = client.post("/ingest", json={})  # no bearer token
    assert response.status_code == 403
    assert _count("/ingest", "403") == before + 1


def test_unknown_paths_share_one_label_and_health_is_ignored():
    client = TestClient(app)
    client.post("/does-not-exist-1")
    client.post("/does-not-exist-2")
    assert _count("unmatched", "404") >= 2
    client.get("/health")
    assert REGISTRY.get_sample_value(
        "importservice_http_requests_total",
        {"route": "/health", "method": "GET", "status": "200"},
    ) is None
