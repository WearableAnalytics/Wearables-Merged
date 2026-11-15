from hmac import compare_digest
from typing import Annotated

from fastapi import Header, HTTPException

from app.core.config import settings

ControlToken = Annotated[str | None, Header(alias="X-Control-Service-Token")]


def _matches(value: str | None, configured: str) -> bool:
    return bool(value and configured and compare_digest(value.encode(), configured.encode()))


async def require_control_read(x_control_service_token: ControlToken = None) -> None:
    if not settings.legacy_capabilities_valid() or (
        not settings.CONTROL_READ_TOKEN and not settings.CONTROL_WRITE_TOKEN
    ):
        raise HTTPException(503, "CONTROL_NOT_CONFIGURED")
    if not (
        _matches(x_control_service_token, settings.CONTROL_READ_TOKEN)
        or _matches(x_control_service_token, settings.CONTROL_WRITE_TOKEN)
    ):
        raise HTTPException(401, "INVALID_CONTROL_CREDENTIAL")


async def require_control_write(x_control_service_token: ControlToken = None) -> None:
    if not settings.CONTROL_WRITE_TOKEN or not settings.legacy_capabilities_valid():
        raise HTTPException(503, "CONTROL_NOT_CONFIGURED")
    if not _matches(x_control_service_token, settings.CONTROL_WRITE_TOKEN):
        raise HTTPException(401, "INVALID_CONTROL_CREDENTIAL")


class ControlBoundary:
    """Bound JSON parsing and prevent storage of account/case responses in caches."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        from starlette.responses import JSONResponse

        path = scope.get("path", "")
        mount = scope.get("root_path", "")
        if mount and path.startswith(mount + "/"):
            path = path[len(mount) :]
        if scope["type"] != "http" or not path.startswith("/control/"):
            await self.app(scope, receive, send)
            return
        # These APIs never accept bulk data. Count actual bytes, including chunked requests.
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 65_536:
                await JSONResponse(
                    {"detail": "CONTROL_BODY_TOO_LARGE"}, status_code=413, headers={"Cache-Control": "no-store"}
                )(scope, receive, send)
                return
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def private_send(message):
            if message["type"] == "http.response.start":
                message = {
                    **message,
                    "headers": [
                        (key, value) for key, value in message.get("headers", []) if key.lower() != b"cache-control"
                    ]
                    + [(b"cache-control", b"no-store")],
                }
            await send(message)

        await self.app(scope, bounded_receive, private_send)
