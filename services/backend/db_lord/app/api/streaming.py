from __future__ import annotations

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


def _resolve_adapter(schema: type[BaseModel] | TypeAdapter[Any] | None) -> TypeAdapter[Any] | None:
    if schema is None:
        return None
    if isinstance(schema, TypeAdapter):
        return schema
    return _schema_adapter(schema)


async def iter_ndjson(
    items: AsyncIterator[Any], schema: type[BaseModel] | TypeAdapter[Any] | None = None
) -> AsyncIterator[bytes]:
    adapter = _resolve_adapter(schema)

    async for item in items:
        if adapter is None:
            yield orjson.dumps(item, option=orjson.OPT_APPEND_NEWLINE)
            continue

        validated = adapter.validate_python(item)
        yield adapter.dump_json(validated) + b"\n"


def stream_as_ndjson(
    items: AsyncIterator[Any],
    schema: type[BaseModel] | TypeAdapter[Any] | None = None,
) -> StreamingResponse:
    return StreamingResponse(iter_ndjson(items, schema=schema), media_type=NDJSON_MEDIA_TYPE)
