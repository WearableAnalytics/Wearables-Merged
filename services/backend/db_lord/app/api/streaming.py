from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import orjson
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

NDJSON_MEDIA_TYPE = "application/x-ndjson"


async def iter_ndjson(items: AsyncIterator[Any]) -> AsyncIterator[bytes]:
    async for item in items:
        payload = jsonable_encoder(item)
        yield orjson.dumps(payload, option=orjson.OPT_APPEND_NEWLINE)


def stream_as_ndjson(items: AsyncIterator[Any]) -> StreamingResponse:
    return StreamingResponse(iter_ndjson(items), media_type=NDJSON_MEDIA_TYPE)
