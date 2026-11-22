"""Who is calling the API, and may they export.

The BFF checks the session or personal API token and then sends the caller to this service as a short-lived
HS256 JWT in the `X-Extraction-Principal` header, signed with `EXTRACTION_INTERNAL_JWT_SECRET`. Every data route
reads the principal from here: admins, practitioners and researchers may export, and everyone without a raw role
(researchers) only gets pseudonymized data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import jwt
from fastapi import HTTPException, Request

from .settings import settings

PRINCIPAL_HEADER = "X-Extraction-Principal"
AUDIENCE = "extraction-service"
ALGORITHM = "HS256"
LEEWAY_SECONDS = 10

@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]
    auth: Literal["session", "api_token"]
    token_id: str | None = None


def decode_principal(token: str) -> Principal:
    claims = jwt.decode(
        token,
        settings.extraction_internal_jwt_secret,
        algorithms=[ALGORITHM],
        audience=AUDIENCE,
        leeway=LEEWAY_SECONDS,
        options={"require": ["exp", "aud", "sub"]},
    )
    auth = claims.get("auth")
    roles = claims.get("roles", [])
    if auth not in ("session", "api_token"):
        raise jwt.InvalidTokenError("unknown auth")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise jwt.InvalidTokenError("roles must be a list of strings")
    return Principal(
        subject=claims["sub"],
        roles=frozenset(roles),
        auth=auth,
        token_id=claims.get("token_id"),
    )


def may_export(principal: Principal) -> bool:
    return not principal.roles.isdisjoint(settings.export_roles)


def must_pseudonymize(principal: Principal) -> bool:
    """Only admins and practitioners see real patient ids; researchers do not."""
    return principal.roles.isdisjoint(settings.raw_export_roles)


def require_export_access(request: Request) -> Principal:
    """Dependency for every data route. The principal is also kept on `request.state.principal`."""
    if not settings.extraction_internal_jwt_secret:
        raise HTTPException(status_code=503, detail="Extraction API authentication is not configured")
    token = request.headers.get(PRINCIPAL_HEADER)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        principal = decode_principal(token)
    except jwt.InvalidTokenError as error:
        raise HTTPException(status_code=401, detail="Invalid or expired credentials") from error
    if not may_export(principal):
        raise HTTPException(status_code=403, detail="Admin, practitioner or researcher access required")
    request.state.principal = principal
    return principal
