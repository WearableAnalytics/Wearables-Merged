"""Exercise the real db_lord HTTP adapter against a local synthetic NDJSON server."""

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from test_export_api import PATIENT, point

from src.app.main import app
from src.app.privacy import ExportPrivacy
from src.app.settings import settings


@pytest.fixture
def http_backend(monkeypatch):
    records = [point(0, value=10), point(0, value=10, host="b", ingested=2), point(1, value=20)]
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            requests.append(url)
            if url.path != "/telemetry/stream":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for record in records:
                self.wfile.write((record.model_dump_json() + "\n").encode())
                self.wfile.flush()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(settings, "db_lord_base_url", f"http://127.0.0.1:{server.server_port}")
    # Deliberately invalid deployment mapping: privacy exports must use the bundled one.
    monkeypatch.setattr(settings, "fhir_default_mapping_path", settings.fhir_default_mapping_path / "absent.yaml")
    try:
        with TestClient(app) as client:
            yield client, records, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("format", ["csv", "fhir"])
def test_real_http_adapter_and_concurrent_exports(http_backend, format):
    client, records, requests = http_backend
    for record in records:
        record.tags["mapping_id"] = "PRIVATE-MAPPING"
        record.tags["dot_dependency_file_id"] = "PRIVATE-GRAPH"
        record.fields["notes"] = "PRIVATE-NAME"

    def download(_):
        response = client.get(
            f"/v1/measurements/export.{format}",
            params={"pseudonymize": "true", "measurement": "steps", "start": "2026-10-08T00:00:00Z"},
        )
        assert response.status_code == 200
        assert PATIENT not in response.text
        assert "PRIVATE" not in response.text
        if format == "csv":
            rows = list(csv.DictReader(io.StringIO(response.text)))
            assert [float(row["value"]) for row in rows] == [10, 20]
            identities = {row["patient_id"] for row in rows}
        else:
            observations = [entry["resource"] for entry in response.json()["entry"]]
            assert [o["valueQuantity"]["value"] for o in observations] == [10, 20]
            identities = {o["subject"]["reference"] for o in observations}
        assert len(identities) == 1
        return identities.pop()

    with ThreadPoolExecutor(max_workers=4) as pool:
        identities = list(pool.map(download, range(8)))
    assert len(set(identities)) == 8
    assert len(requests) == 8
    assert all(request.path == "/telemetry/stream" for request in requests)
    assert all(parse_qs(request.query)["measurement"] == ["steps"] for request in requests)
    assert all("pseudonymize" not in parse_qs(request.query) for request in requests)


def test_all_supported_measurements_and_missing_patients(http_backend):
    client, records, _ = http_backend
    privacy = ExportPrivacy()
    measurement_names = list(privacy._categories)
    records[:] = [
        point(i, measurement=name, device_id=None, reference=False) for i, name in enumerate(measurement_names)
    ]
    response = client.get("/v1/measurements/export.fhir?pseudonymize=true")
    assert response.status_code == 200
    entries = response.json()["entry"]
    assert len(entries) == len(measurement_names)
    for entry in entries:
        resource = entry["resource"]
        assert resource["resourceType"] == "Observation"
        assert resource["status"] == "final"
        assert resource["code"]["coding"][0]["system"] == "http://loinc.org/"
        assert resource["valueQuantity"]["value"] == 10
        assert "subject" not in resource
        assert "device" not in resource
        assert entry["fullUrl"] == "urn:uuid:" + resource["id"]


def test_large_export_keeps_numeric_values_and_timestamps(http_backend):
    client, records, _ = http_backend
    records[:] = [point(i, value=i) for i in range(2000)]
    response = client.get("/v1/measurements/export.csv?pseudonymize=true")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 2000
    assert len({row["patient_id"] for row in rows}) == 1
    assert [int(row["value"]) for row in rows] == list(range(2000))
    assert [row["timestamp"] for row in rows] == [record.timestamp.isoformat() for record in records]


def test_openapi_exposes_option_and_rejects_invalid_boolean(http_backend):
    client, _, _ = http_backend
    schema = client.get("/openapi.json").json()
    for format in ("csv", "fhir"):
        path = f"/v1/measurements/export.{format}"
        params = schema["paths"][path]["get"]["parameters"]
        option = next(param for param in params if param["name"] == "pseudonymize")
        assert option["schema"]["type"] == "boolean"
        assert option["schema"]["default"] is False
        assert client.get(path, params={"pseudonymize": "invalid"}).status_code == 422
