import pytest

from src.app import export_response
from src.app.privacy import ExportPrivacy


@pytest.mark.asyncio
async def test_preparation_failure_closes_source_and_temp_file(monkeypatch):
    files = []
    factory = export_response.SpooledTemporaryFile

    def track(**kwargs):
        file = factory(**kwargs)
        files.append(file)
        return file

    monkeypatch.setattr(export_response, "SpooledTemporaryFile", track)
    closed = []

    async def broken():
        try:
            yield "some data"
            raise RuntimeError("upstream failed")
        finally:
            closed.append(True)

    with pytest.raises(RuntimeError, match="upstream failed"):
        await export_response.prepare_export(broken(), ExportPrivacy(), media_type="text/csv", suffix="csv")
    assert closed == [True]
    assert files[0].closed


@pytest.mark.asyncio
@pytest.mark.parametrize("disconnect", [False, True])
async def test_large_download_and_disconnect_close_temporary_file(disconnect):
    async def large():
        for _ in range(144):
            yield "x" * 65536

    response = await export_response.prepare_export(large(), ExportPrivacy(), media_type="text/csv", suffix="csv")
    assert response.file._rolled  # Above the 8 MiB memory threshold.
    received = 0

    async def send(message):
        nonlocal received
        if message["type"] == "http.response.body":
            if disconnect:
                raise OSError("client disconnected")
            received += len(message.get("body", b""))

    async def receive():
        return {"type": "http.disconnect"}

    scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    if disconnect:
        from starlette.requests import ClientDisconnect

        with pytest.raises(ClientDisconnect):
            await response(scope, receive, send)
    else:
        await response(scope, receive, send)
        assert received == 144 * 65536
    assert response.file.closed
