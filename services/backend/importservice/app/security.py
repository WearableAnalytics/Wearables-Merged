import logging
from uuid import UUID

from authlib.jose import JsonWebToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

logger = logging.getLogger(__name__)

_http_bearer = HTTPBearer(auto_error=True)
_jwt_hs256 = JsonWebToken(["HS256"])


def verify_case_verification_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
):
    """Verify JWT from registration-service (HS256). Returns claims with patientId, caseId, etc."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="JWT verification not configured (JWT_SECRET)",
        )
    token = credentials.credentials
    if not token or len(token.split(".")) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format: expected a JWT (Authorization: Bearer <jwt>)",
        )
    try:
        claims = _jwt_hs256.decode(token, settings.jwt_secret, claims_options={"exp": {"essential": True}})
        claims.validate()
    except Exception as ex:
        logger.warning("Case-verification token decode failed: %s", ex)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from ex

    if claims.get("iss") != settings.registration_issuer:
        raise HTTPException(status_code=401, detail="Invalid issuer")
    if claims.get("type") != "case-verification":
        raise HTTPException(status_code=401, detail="Invalid token type")

    case_id = claims.get("caseId")
    sub = claims.get("sub")
    if sub is not None and case_id is not None and sub != case_id:
        raise HTTPException(status_code=401, detail="Subject does not match caseId")

    try:
        claims["caseId"] = str(UUID(claims["caseId"]))
        claims["patientId"] = str(UUID(claims["patientId"]))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid case or participant identity") from exc

    return claims
