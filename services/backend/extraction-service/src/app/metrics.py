"""Export instrumentation at the ASGI response boundary."""
import asyncio
from contextlib import aclosing
from time import monotonic

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse

FORMATS = {
    "/v1/measurements/export.csv": "csv",
    "/v1/measurements/export.fhir": "fhir",
}
OUTCOMES = ("success", "failed", "rejected", "cancelled")


class ExportMetrics:
    def __init__(self):
        self.registry = CollectorRegistry()

        def counter(name, help_text, *labels):
            return Counter(f"wearables_export_{name}", help_text, labels, registry=self.registry)

        self.requests = counter("requests", "Export requests reaching extraction.", "format")
        self.completed = counter("completed", "Terminal export outcomes.", "format", "outcome")
        self.duration = Histogram(
            "wearables_export_duration_seconds", "Time from request to terminal outcome.",
            ("format", "outcome"), registry=self.registry,
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
        )
        self.active = Gauge("wearables_export_active", "Active export requests.", ("format",), registry=self.registry)
        self.considered = counter("measurements_considered", "Readings after filtering and reconciliation.", "format")
        self.exported = counter("measurements_exported", "Successfully serialized readings.", "format")
        self.omitted = counter("measurements_omitted", "Readings deliberately omitted.", "format", "reason")
        for fmt in FORMATS.values():
            for metric in (self.requests, self.active, self.considered, self.exported):
                metric.labels(fmt)
            for outcome in OUTCOMES:
                self.completed.labels(fmt, outcome)
                self.duration.labels(fmt, outcome)
        self.omitted.labels("fhir", "unsupported_mapping")


class ExportResponse(StreamingResponse):
    async def stream_response(self, send):
        async with aclosing(self.body_iterator):
            await super().stream_response(send)


class ExportMonitoring:
    def __init__(self, app, metrics):
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope, receive, send):
        root = scope.get("root_path", "").rstrip("/")
        path = scope.get("path", "")
        if root and path.startswith(root + "/"):
            path = path[len(root):]
        fmt = FORMATS.get(path)
        if scope["type"] != "http" or not fmt:
            return await self.app(scope, receive, send)

        metrics = self.metrics
        start = monotonic()
        status = None
        finished = disconnected = False
        outcome = "failed"
        metrics.requests.labels(fmt).inc()
        active = metrics.active.labels(fmt)
        active.inc()
        scope.setdefault("state", {})["export_metrics"] = metrics

        async def observe_receive():
            nonlocal disconnected
            message = await receive()
            if message["type"] == "http.disconnect" and not finished:
                disconnected = True
            return message

        async def observe_send(message):
            nonlocal status, finished, disconnected
            try:
                await send(message)
            except OSError:
                disconnected = True
                raise
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body" and not message.get("more_body"):
                finished = True

        try:
            await self.app(scope, observe_receive, observe_send)
            if disconnected:
                outcome = "cancelled"
            elif finished and status is not None:
                if 200 <= status < 300:
                    outcome = "success"
                elif 400 <= status < 500:
                    outcome = "rejected"
        except (asyncio.CancelledError, ClientDisconnect, GeneratorExit):
            outcome = "cancelled"
            raise
        except Exception:
            if disconnected:
                outcome = "cancelled"
            raise
        finally:
            active.dec()
            metrics.completed.labels(fmt, outcome).inc()
            metrics.duration.labels(fmt, outcome).observe(monotonic() - start)
