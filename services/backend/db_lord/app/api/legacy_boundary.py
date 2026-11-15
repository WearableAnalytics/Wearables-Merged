"""Separate privileged legacy tools from governed application case reads."""

from hmac import compare_digest

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings

LEGACY_ROOTS = frozenset(
    {
        "patients",
        "cases",
        "devices",
        "wearables",
        "contexts",
        "telemetry",
        "fhir-mappings",
        "graphql",
        "api-tokens",
    }
)


class LegacyBoundary:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        path, mount = scope.get("path", ""), scope.get("root_path", "")
        if mount and (path == mount or path.startswith(mount + "/")):
            path = path[len(mount) :]
        root = path.split("/", 2)[1:2]
        if kind not in {"http", "websocket"} or not root or root[0] not in LEGACY_ROOTS:
            await self.app(scope, receive, send)
            return
        # Legacy sockets have no current-authority continuation protocol.
        if kind == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        token_api = root[0] == "api-tokens"
        expected = settings.API_TOKEN_SERVICE_TOKEN if token_api else settings.LEGACY_OPERATOR_TOKEN
        header = b"x-api-token-service-token" if token_api else b"x-legacy-operator-token"
        valid_config = bool(expected) and settings.legacy_capabilities_valid()
        values = [v for k, v in scope.get("headers", []) if k.lower() == header]
        allowed = valid_config and len(values) == 1 and compare_digest(values[0], expected.encode("ascii"))
        if not allowed:
            response = JSONResponse(
                {"detail": "LEGACY_CAPABILITY_REQUIRED" if valid_config else "LEGACY_CAPABILITY_UNCONFIGURED"},
                status_code=401 if valid_config else 503,
                headers={"Cache-Control": "no-store"},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
