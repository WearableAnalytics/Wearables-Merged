import logging
from typing import Any, Dict

from authlib.jose import JsonWebToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

logger = logging.getLogger(__name__)

_http_bearer = HTTPBearer(auto_error=True)
_jwt_hs256 = JsonWebToken(["HS256"])


def extract_patient_id(claims: Dict[str, Any]) -> str:
    """Resolves the canonical patient identifier carried by a verification JWT"""
    for key in ("patientId", "caseId", "sub"):
        val = claims.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token missing patientId claim",
    )


def verify_case_verification_token(
    credentials: HTTPAuthorizationCredentials = Depends(_http_bearer),
) -> Dict[str, Any]:
    """Verify JWT from wearables-bff (HS256). Returns decoded claims"""
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
        claims = _jwt_hs256.decode(token, settings.jwt_secret)
        claims.validate()
    except Exception as ex:
        logger.warning("Case-verification token decode failed: %s", ex)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if claims.get("iss") != settings.jwt_issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid issuer")
    if claims.get("type") != "case-verification":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    case_id = claims.get("caseId")
    sub = claims.get("sub")
    if sub is not None and case_id is not None and sub != case_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Subject does not match caseId",
        )

    extract_patient_id(claims)
    return dict(claims)


def assert_patient_matches(claims: Dict[str, Any], target_patient_id: str) -> str:
    """Ensures the caller's JWT belongs to target_patient_id."""
    token_patient_id = extract_patient_id(claims)
    if target_patient_id != token_patient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is not authorized for this patient_id",
        )
    return token_patient_id
