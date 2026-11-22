import asyncio
from urllib.request import urlopen

import httpx
import pytest
from fastapi.testclient import TestClient
from prometheus_client import start_http_server
from starlette.middleware import Middleware
from test_export_api import PATIENT, FakeDbLord, point

from src.app import metrics as instrumentation
from src.app.main import app, get_db_lord_api
from src.app.metrics import ExportMetrics, ExportMonitoring


@pytest.fixture
def metrics(monkeypatch):
    instance = ExportMetrics()
    monkeypatch.setattr(app, "middleware_stack", None)
    monkeypatch.setattr(app, "user_middleware", [Middleware(ExportMonitoring, metrics=instance)])
    unsupported = point(2, measurement="unmapped")
    unsupported.tags.pop("category")
    monkeypatch.setitem(app.dependency_overrides, get_db_lord_api, lambda: FakeDbLord([
        point(0), point(0, host="duplicate"), unsupported
    ]))
    return instance


def value(metrics, name, **labels):
    return metrics.registry.get_sample_value("wearables_export_" + name, labels)


@pytest.mark.parametrize(("fmt", "serialized"), [("csv", 2), ("fhir", 1)])
def test_success_and_counts(metrics, fmt, serialized):
    client = TestClient(app)
    assert client.get(f"/v1/measurements/export.{fmt}").status_code == 200
    assert value(metrics, "measurements_considered_total", format=fmt) == 2
    assert value(metrics, "measurements_exported_total", format=fmt) == serialized
    assert value(metrics, "completed_total", format=fmt, outcome="success") == 1
    assert value(metrics, "active", format=fmt) == 0
    if fmt == "fhir":
        assert value(metrics, "measurements_omitted_total", format=fmt, reason="unsupported_mapping") == 1


def test_empty_rejected_and_timing(metrics, monkeypatch):
    times = iter([10, 13, 20, 21])
    monkeypatch.setattr(instrumentation, "monotonic", lambda: next(times))
    client = TestClient(app)
    assert client.get("/v1/measurements/export.csv?measurement=absent").status_code == 200
    assert client.get("/v1/measurements/export.csv?start=invalid").status_code == 422
    assert value(metrics, "requests_total", format="csv") == 2
    assert value(metrics, "duration_seconds_sum", format="csv", outcome="success") == 3
    assert value(metrics, "completed_total", format="csv", outcome="rejected") == 1
    assert value(metrics, "measurements_exported_total", format="csv") == 0


@pytest.mark.parametrize("failure", ["http", "partial", "mapping", "dependency"])
def test_failures(metrics, monkeypatch, failure):
    class BrokenDb(FakeDbLord):
        async def stream_telemetry(self, **kwargs):
            if failure == "mapping":
                reading = point(0)
                reading.tags["mapping_id"] = "missing"
                yield reading
                return
            if failure == "partial":
                yield point(0)
                yield point(1)
            request = httpx.Request("GET", "http://db/telemetry/stream")
            raise httpx.HTTPStatusError("upstream unavailable", request=request,
                                        response=httpx.Response(503, request=request))

    def backend():
        if failure == "dependency":
            raise RuntimeError("dependency failed")
        return BrokenDb([])

    monkeypatch.setitem(app.dependency_overrides, get_db_lord_api, backend)
    fmt = "fhir" if failure == "mapping" else "csv"
    with pytest.raises((RuntimeError, LookupError, httpx.HTTPStatusError)):
        TestClient(app).get(f"/v1/measurements/export.{fmt}")
    assert value(metrics, "completed_total", format=fmt, outcome="failed") == 1
    assert value(metrics, "active", format=fmt) == 0
    if failure == "partial":
        assert value(metrics, "measurements_exported_total", format=fmt) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", ["receive", "send", "task"])
async def test_parallel_exports_and_disconnect(metrics, disconnect):
    entered = asyncio.Queue()
    release = asyncio.Event()
    closed = []

    class SlowDb(FakeDbLord):
        async def stream_telemetry(self, **kwargs):
            entered.put_nowait(True)
            try:
                await release.wait()
                yield point(0)
            finally:
                closed.append(True)

    app.dependency_overrides[get_db_lord_api] = lambda: SlowDb([])

    async def export(abort):
        scope = {"type": "http", "method": "GET", "path": "/v1/measurements/export.csv", "headers": [],
                 "query_string": b"", "asgi": {"spec_version": "2.3" if disconnect == "receive" else "2.4"}}

        async def receive():
            await abort.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if disconnect == "send" and abort.is_set() and message["type"] == "http.response.body":
                raise OSError("peer closed")

        await app(scope, receive, send)

    abort, keep = asyncio.Event(), asyncio.Event()
    first, second = asyncio.create_task(export(abort)), asyncio.create_task(export(keep))
    await asyncio.wait_for(entered.get(), 2)
    await asyncio.wait_for(entered.get(), 2)
    assert value(metrics, "active", format="csv") == 2
    abort.set()
    if disconnect == "task":
        first.cancel()
    if disconnect == "send":
        release.set()
    await asyncio.wait_for(asyncio.gather(first, return_exceptions=True), 2)
    release.set()
    await asyncio.wait_for(second, 2)
    assert len(closed) == 2
    assert value(metrics, "active", format="csv") == 0
    assert value(metrics, "completed_total", format="csv", outcome="success") == 1
    assert value(metrics, "completed_total", format="csv", outcome="cancelled") == 1


def test_private_metrics_listener_and_labels(metrics):
    client = TestClient(app)
    client.get("/v1/measurements/export.csv", params={"patient_id": PATIENT})
    assert client.get("/metrics").status_code == 404
    server, thread = start_http_server(0, addr="127.0.0.1", registry=metrics.registry)
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/metrics", timeout=2) as response:
            exposition = response.read().decode()
        assert 'wearables_export_requests_total{format="csv"} 1.0' in exposition
        assert PATIENT not in exposition
        for family in metrics.registry.collect():
            for sample in family.samples:
                assert set(sample.labels) <= {"format", "outcome", "reason", "le"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
