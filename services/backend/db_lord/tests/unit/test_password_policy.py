"""Password storage and policy checks use the actual Argon2 implementation."""

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.passwords import hash_password, validate_new, verify_password
from app.schemas.passwords import PasswordLogin

pytestmark = pytest.mark.anyio


async def test_salts_are_unique_and_nfc_equivalent_passwords_match():
    value = "An uncommon cafe\u0301 passphrase 2026!"
    first = await hash_password(value, "staff@example.test")
    second = await hash_password(value, "staff@example.test")
    assert first != second and first.startswith("$argon2id$")
    assert await verify_password(first, "An uncommon café passphrase 2026!")
    assert not await verify_password(first, "Another uncommon café passphrase!")
    assert not await verify_password("$argon2id$invalid", value)


async def test_password_whitespace_is_not_stripped():
    value = "  an uncommon long passphrase 2026  "
    request = PasswordLogin(email=" STAFF@EXAMPLE.TEST ", password=SecretStr(value))
    assert request.email == "staff@example.test" and request.password.get_secret_value() == value
    hashed = await hash_password(value, request.email)
    assert await verify_password(hashed, value)
    assert not await verify_password(hashed, value.strip())


@pytest.mark.parametrize("value", ["short", "passwordpassword", "staff@example.test", "x" * 257])
async def test_short_common_account_name_and_overlong_passwords_are_rejected(value):
    with pytest.raises(HTTPException) as error:
        validate_new(value, "staff@example.test")
    assert error.value.status_code == 422
