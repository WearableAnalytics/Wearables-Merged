from typing import TypeVar

from fastapi_pagination.bases import CursorRawParams
from fastapi_pagination.cursor import CursorPage, CursorParams
from fastapi_pagination.types import Cursor
from pydantic import Field

T = TypeVar("T")


class CursorParamsNoTotal(CursorParams):
    """Cursor params that disable total count computation and keep cursor values opaque."""

    def encode_cursor(self, cursor: Cursor | None) -> str | None:
        if cursor is None:
            return None
        return cursor.decode() if isinstance(cursor, bytes) else cursor

    def decode_cursor(self, cursor: str | None) -> Cursor | None:
        return cursor

    def to_raw_params(self) -> CursorRawParams:
        raw = super().to_raw_params()
        raw.include_total = False
        return raw


class CursorPageNoTotal[T](CursorPage[T]):
    """Cursor page with optional total."""
    total: int = Field(default=0, exclude=True)


CursorPageNoTotal.set_params(CursorParamsNoTotal)
