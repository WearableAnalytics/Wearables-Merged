"""Prepare privacy downloads so exact counts can be sent before the response body."""

from collections.abc import AsyncIterator
from contextlib import aclosing
from tempfile import SpooledTemporaryFile

from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from .privacy import ExportPrivacy

EXPORT_HEADERS = {
    name: {"schema": {"type": "integer", "minimum": 0}, "description": description}
    for name, description in {
        "X-Export-Considered": "Matching readings after deduplication, before privacy filtering. Privacy mode only.",
        "X-Export-Exported": "Readings included in this pseudonymized download.",
        "X-Export-Omitted": "Readings omitted by privacy filtering; does not count duplicate copies.",
        "X-Export-Omitted-Unsupported": "Omitted because the measurement type is unsupported.",
        "X-Export-Omitted-Invalid-Value": "Known measurement type with missing, nonnumeric or nonfinite value.",
    }.items()
}


class PreparedExportResponse(StreamingResponse):
    def __init__(self, file, **kwargs):
        self.file = file
        super().__init__(self.chunks(), **kwargs)

    async def chunks(self):
        while chunk := await run_in_threadpool(self.file.read, 65536):
            yield chunk

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Also close on disconnect or a failed response send.
            self.file.close()


async def prepare_export(
    content: AsyncIterator[str], privacy: ExportPrivacy, *, media_type: str, suffix: str
) -> PreparedExportResponse:
    # Ownership transfers to PreparedExportResponse; its ASGI lifecycle closes the file.
    file = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")  # noqa: SIM115
    try:
        buffer = bytearray()
        async with aclosing(content):
            async for piece in content:
                buffer.extend(piece.encode("utf-8"))
                if len(buffer) >= 65536:
                    await run_in_threadpool(file.write, bytes(buffer))
                    buffer.clear()
        if buffer:
            await run_in_threadpool(file.write, bytes(buffer))
        size = file.tell()
        await run_in_threadpool(file.seek, 0)
        warning = f"-{privacy.omitted}-omitted" if privacy.omitted else ""
        filename = f"measurements-pseudonymized{warning}.{suffix}"
        return PreparedExportResponse(
            file,
            media_type=media_type,
            headers={
                **privacy.response_headers(),
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
                "Content-Length": str(size),
            },
        )
    except BaseException:
        file.close()
        raise
