from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.app.settings import settings

SECRET = "test-internal-secret-of-32-bytes-ok"


def principal_token(roles=("admin",), *, auth="session", secret=SECRET, expires_in=60, **extra):
    """A principal as the BFF signs it (see wearables-bff src/api/routes/extraction.ts)."""
    now = datetime.now(UTC)
    claims = {
        "sub": "caller@example.com",
        "aud": "extraction-service",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "roles": list(roles),
        "auth": auth,
        **extra,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def internal_secret(monkeypatch):
    monkeypatch.setattr(settings, "extraction_internal_jwt_secret", SECRET)
