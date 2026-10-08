from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.model_constants import API_TOKEN_HASH_LEN, API_TOKEN_NAME_MAX_LEN, API_TOKEN_OWNER_MAX_LEN

from .common import TunedBase

TOKEN_HASH_PATTERN = rf"^[0-9a-f]{{{API_TOKEN_HASH_LEN}}}$"


class ApiTokenCreate(TunedBase):
    token_hash: str = Field(..., pattern=TOKEN_HASH_PATTERN, description="Lowercase hex sha256 of the token.")
    token_hint: str = Field(..., min_length=1, max_length=8, description="Last characters of the token.")
    owner_email: str = Field(..., min_length=3, max_length=API_TOKEN_OWNER_MAX_LEN)
    name: str = Field(..., min_length=1, max_length=API_TOKEN_NAME_MAX_LEN)


class ApiTokenVerify(TunedBase):
    token_hash: str = Field(..., pattern=TOKEN_HASH_PATTERN)


class ApiTokenRevoke(TunedBase):
    revoked_by: str = Field(..., min_length=3, max_length=API_TOKEN_OWNER_MAX_LEN)


class ApiTokenResponse(TunedBase):
    """A token without its hash."""

    id: UUID
    token_hint: str
    owner_email: str
    name: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
    revoked_by: str | None
