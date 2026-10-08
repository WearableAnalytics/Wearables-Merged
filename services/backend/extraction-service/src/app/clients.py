from __future__ import annotations

import httpx

from .settings import settings


def create_db_lord_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.db_lord_base_url, timeout=settings.db_lord_timeout_seconds)
