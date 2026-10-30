from __future__ import annotations

import httpx

from .settings import settings


def create_db_lord_client() -> httpx.AsyncClient:
    token = settings.db_lord_operator_token.get_secret_value()
    if not token:
        raise RuntimeError("DB_LORD_OPERATOR_TOKEN is required for the private database API")
    return httpx.AsyncClient(
        base_url=settings.db_lord_base_url,
        timeout=settings.db_lord_timeout_seconds,
        headers={"X-Legacy-Operator-Token": token},
    )
