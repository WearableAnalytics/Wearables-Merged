import time
import logging
import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from authlib.jose import JsonWebToken
from .config import get_settings

logger = logging.getLogger(__name__)

_http_bearer = HTTPBearer(auto_error=True)
_jwt = JsonWebToken(["RS256"])  # Keycloak default alg
_cached_jwks = None
_jwks_fetched_at = 0.0


def _fetch_jwks():
    settings = get_settings()
    discovery_url = f"{settings.keycloak_issuer}/.well-known/openid-configuration"
    r = httpx.get(discovery_url, timeout=10.0)
    r.raise_for_status()
    jwks_uri = r.json()["jwks_uri"]
    r2 = httpx.get(jwks_uri, timeout=10.0)
    r2.raise_for_status()
    return r2.json()


def _get_jwks():
    global _cached_jwks, _jwks_fetched_at
    now = time.time()
    if _cached_jwks is None or (now - _jwks_fetched_at) > 21600:  # 6 hours
        _cached_jwks = _fetch_jwks()
        _jwks_fetched_at = now
    return _cached_jwks


def _validate_claims(claims: dict):
    settings = get_settings()

    if claims.get("iss") != settings.keycloak_issuer:
        raise HTTPException(status_code=401, detail="Invalid issuer")

    aud = claims.get("aud")
    if isinstance(aud, list):
        if settings.keycloak_client_id not in aud:
            raise HTTPException(status_code=401, detail="Invalid audience")
    else:
        if aud != settings.keycloak_client_id:
            raise HTTPException(status_code=401, detail="Invalid audience")

    roles = (claims.get("realm_access") or {}).get("roles", [])
    if settings.keycloak_required_role and settings.keycloak_required_role not in roles:
        raise HTTPException(status_code=403, detail="Missing required role")


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_http_bearer)):
    token = credentials.credentials
    try:
        claims = _jwt.decode(token, _get_jwks())
        claims.validate() 
    except Exception as ex:
        logger.warning("Token decode failed, refreshing JWKS: %s", ex)
        try:
            global _cached_jwks, _jwks_fetched_at
            _cached_jwks = _fetch_jwks()
            _jwks_fetched_at = time.time()
            claims = _jwt.decode(token, _cached_jwks)
            claims.validate()
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    _validate_claims(claims)
    return claims
