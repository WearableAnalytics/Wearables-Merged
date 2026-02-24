from typing import Annotated

from fastapi import Query

STREAM_BATCH_SIZE_DEFAULT = 500
STREAM_BATCH_SIZE_MAX = 10_000
StreamBatchSizeParam = Annotated[int, Query(ge=1, le=STREAM_BATCH_SIZE_MAX)]
