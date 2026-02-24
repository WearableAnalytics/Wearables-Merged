from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Any

import orjson
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, TypeAdapter

NDJSON_MEDIA_TYPE = "application/x-ndjson"


@lru_cache(maxsize=64)
def _schema_adapter(schema: type[BaseModel]) -> TypeAdapter[Any]:
    return TypeAdapter(schema)


async def iter_ndjson(items: AsyncIterator[Any], schema: type[BaseModel] | None = None) -> AsyncIterator[bytes]:
    if schema is None:
        async for item in items:
            yield orjson.dumps(item, option=orjson.OPT_APPEND_NEWLINE)
        return

    adapter = _schema_adapter(schema)
    async for item in items:
        validated = adapter.validate_python(item)
        yield adapter.dump_json(validated) + b"\n"


def stream_as_ndjson(items: AsyncIterator[Any], schema: type[BaseModel] | None = None) -> StreamingResponse:
    return StreamingResponse(iter_ndjson(items, schema=schema), media_type=NDJSON_MEDIA_TYPE)
