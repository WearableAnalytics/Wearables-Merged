from __future__ import annotations

from typing import TypeVar

from fastapi_pagination.bases import CursorRawParams
from fastapi_pagination.cursor import CursorPage, CursorParams, decode_cursor
from pydantic import Field

T = TypeVar("T")


class CursorParamsNoTotal(CursorParams):
    """Cursor params that disable total count computation."""

    def decode_cursor(self, cursor: str | None) -> str | None:
        return decode_cursor(cursor, to_str=True, quoted=self.quoted_cursor)

    def to_raw_params(self) -> CursorRawParams:
        raw = super().to_raw_params()
        raw.include_total = False
        return raw


class CursorPageNoTotal[T](CursorPage[T]):
    """Cursor page with optional total."""

    total: int | None = Field(default=None, exclude=True)


CursorPageNoTotal.set_params(CursorParamsNoTotal)
