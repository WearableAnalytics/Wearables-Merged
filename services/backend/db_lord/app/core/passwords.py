"""Argon2id password verification with bounded off-thread work."""

import asyncio
import secrets
import unicodedata
from collections.abc import Callable

from argon2 import PasswordHasher, Type, extract_parameters
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

# Above the OWASP Argon2id minimum; fixed parameters make the resource budget explicit.
HASHER = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=1, hash_len=32, salt_len=16, type=Type.ID)
SLOTS = asyncio.Semaphore(2)  # At most 128 MiB of KDF memory per API worker, plus overhead.
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
BLOCKED = frozenset(
    {
        "passwordpassword",
        "passwordpasswordpassword",
        "123456789012345",
        "1234567890123456",
        "qwertyuiopasdfgh",
        "adminadminadmin",
        "adminadminadminadmin",
        "wearableswearables",
        "charitecharitecharite",
        "changemechangeme",
        "letmeinletmeinletmein",
    }
)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def validate_new(value: str, email: str) -> str:
    value = normalize(value)
    local = email.split("@", 1)[0].casefold()
    try:
        encoded_length = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise HTTPException(422, "PASSWORD_INVALID_UNICODE") from None
    if not 15 <= len(value) <= 256 or encoded_length > 1024:
        raise HTTPException(422, "PASSWORD_LENGTH_15_TO_256")
    if value.casefold() in BLOCKED or value.casefold() in {email.casefold(), local}:
        raise HTTPException(422, "PASSWORD_TOO_COMMON")
    return value


async def _work[T](operation: Callable[[], T]) -> T:
    if SLOTS.locked():
        raise HTTPException(503, "PASSWORD_CAPACITY")
    async with SLOTS:
        task = asyncio.create_task(asyncio.to_thread(operation))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # A cancelled HTTP request cannot release its memory slot while Argon2 still runs.
            await task
            raise


async def hash_password(value: str, email: str) -> str:
    normalized = validate_new(value, email)
    return await _work(lambda: HASHER.hash(normalized))


def _verify(encoded: str, value: str) -> bool:
    try:
        params = extract_parameters(encoded)
        if (
            params.version != 19
            or params.type != Type.ID
            or params.memory_cost != 65_536
            or params.time_cost != 3
            or params.parallelism != 1
            or params.hash_len != 32
            or params.salt_len != 16
        ):
            return False
        return HASHER.verify(encoded, normalize(value))
    except InvalidHashError, VerificationError, ValueError:
        return False


async def verify_password(encoded: str | None, value: str) -> bool:
    valid = await _work(lambda: _verify(encoded or DUMMY_HASH, value))
    return encoded is not None and valid
