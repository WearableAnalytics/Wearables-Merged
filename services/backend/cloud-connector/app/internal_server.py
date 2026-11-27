import json
import logging
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .config import get_settings
from .outbox import get_outbox
from .storage import get_store

logger = logging.getLogger(__name__)

_internal_server: Optional[ThreadingHTTPServer] = None


class _InternalHandler(BaseHTTPRequestHandler):
    """Cluster-internal read-only endpoints"""

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "scope": "internal",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            return

        if parsed.path in ("/connections", "/internal/connections"):
            query = parse_qs(parsed.query)
            provider = query.get("provider", [None])[0]
            connections = get_store().list_connections(provider=provider)
            self._send_json(200, {"connections": connections})
            return

        if parsed.path in ("/garmin/readiness", "/internal/garmin/readiness"):
            settings = get_settings()
            self._send_json(
                200,
                {
                    "provider": "garmin",
                    "environment": settings.garmin_environment,
                    "client_configured": bool(
                        settings.garmin_client_id.strip() and settings.garmin_client_secret.strip()
                    ),
                    "backfill_enabled": settings.garmin_backfill_enabled,
                    "allow_pre_auth_history": settings.garmin_allow_pre_auth_history,
                    "verify_client_id": settings.garmin_verify_client_id,
                    "webhook_path": "/webhooks/garmin",
                    "oauth_redirect_uri": settings.oauth_redirect_uri,
                    "outbox": get_outbox().stats(),
                },
            )
            return

        if parsed.path in ("/outbox", "/internal/outbox"):
            self._send_json(200, get_outbox().stats())
            return

        self._send_json(404, {"detail": "Not found"})

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        logger.debug("Internal server: " + format, *args)


def start_internal_server() -> None:
    """Starts the internal admin HTTP server on INTERNAL_PORT if enabled"""
    global _internal_server
    if _internal_server is not None:
        return

    port = get_settings().internal_port
    if port <= 0:
        return

    try:
        ThreadingHTTPServer.allow_reuse_address = True
        server = ThreadingHTTPServer(("0.0.0.0", port), _InternalHandler)
    except OSError as exc:
        logger.warning("Could not bind internal admin port %d: %s", port, exc)
        return

    _internal_server = server
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="internal-admin")
    thread.start()
    logger.info("Serving internal admin endpoints on :%d", port)
