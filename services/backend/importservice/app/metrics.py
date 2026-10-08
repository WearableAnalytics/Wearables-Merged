"""Prometheus request metrics for the import service.

uvicorn runs several worker processes, so the counters use prometheus_client's
multiprocess mode (PROMETHEUS_MULTIPROC_DIR, set in the Dockerfile). Each worker
tries to bind the metrics port on startup; the first one wins and serves the
aggregated values of all workers. The port is separate from the API port so
/metrics is never reachable through the public /import ingress route.
"""

import logging
import os
import time

from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

METRICS_PORT = int(os.getenv("METRICS_PORT", "9102"))

# Probe traffic would drown out real uploads.
_IGNORED_PATHS = {"/health"}

REQUESTS = Counter(
    "importservice_http_requests_total",
    "HTTP requests handled, by route template, method and status code.",
    ["route", "method", "status"],
)
LATENCY = Histogram(
    "importservice_http_request_duration_seconds",
    "HTTP request duration, by route template.",
    ["route"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


def _route_template(request: Request) -> str:
    # Use the matched route path, not the raw URL, so scanners hitting random
    # paths can't create unbounded label values.
    route = request.scope.get("route")
    return getattr(route, "path", None) or "unmatched"


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _IGNORED_PATHS:
            return await call_next(request)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = _route_template(request)
            REQUESTS.labels(route, request.method, str(status)).inc()
            LATENCY.labels(route).observe(time.perf_counter() - start)


def start_metrics_server() -> None:
    registry = None
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    try:
        if registry is None:
            start_http_server(METRICS_PORT)
        else:
            start_http_server(METRICS_PORT, registry=registry)
        logger.info("Serving metrics on :%d", METRICS_PORT)
    except OSError:
        # Another worker already serves the shared metrics.
        pass
