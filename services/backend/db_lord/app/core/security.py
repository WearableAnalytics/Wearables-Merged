"""JWT validation for db_lord.

db_lord is an internal service called exclusively by the wearables-bff.
The BFF signs a short-lived service token with the shared JWT_SECRET (HS256)
and passes it as a Bearer token in the Authorization header.
"""

from dataclasses import dataclass

import jwt
from fastapi import HTTPException, status

from app.core.config import settings

_ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    email: str | None = None
    is_service_account: bool = False


def decode_token(token: str) -> TokenPayload:
    """Validate and decode a JWT.  Raises HTTP 401 on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub = payload.get("sub") or payload.get("userId")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPayload(
        sub=str(sub),
        email=payload.get("email"),
        is_service_account=payload.get("service", False),
    )
