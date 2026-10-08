import hashlib

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _create(client: AsyncClient, token: str, owner: str = "Researcher@Example.org", name: str = "laptop"):
    response = await client.post(
        "/api-tokens/",
        json={"token_hash": _hash(token), "token_hint": token[-4:], "owner_email": owner, "name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_list_verify_revoke(client: AsyncClient):
    created = await _create(client, "wrt_first-token-abcd")
    assert created["owner_email"] == "researcher@example.org"
    assert created["token_hint"] == "abcd"
    assert "token_hash" not in created
    await _create(client, "wrt_other-owner-token", owner="other@example.org")

    own = (await client.get("/api-tokens/", params={"owner_email": "RESEARCHER@example.org"})).json()
    assert [t["id"] for t in own] == [created["id"]]
    assert len((await client.get("/api-tokens/")).json()) == 2

    verified = await client.post("/api-tokens/verify", json={"token_hash": _hash("wrt_first-token-abcd")})
    assert verified.status_code == 200
    assert verified.json()["id"] == created["id"]
    assert verified.json()["last_used_at"] is not None

    unknown = await client.post("/api-tokens/verify", json={"token_hash": _hash("nope")})
    assert unknown.status_code == 404

    revoked = await client.post(f"/api-tokens/{created['id']}/revoke", json={"revoked_by": "Admin@example.org"})
    assert revoked.status_code == 200
    assert revoked.json()["revoked_by"] == "admin@example.org"
    assert revoked.json()["revoked_at"] is not None

    after = await client.post("/api-tokens/verify", json={"token_hash": _hash("wrt_first-token-abcd")})
    assert after.status_code == 404
    assert (await client.get("/api-tokens/", params={"owner_email": "researcher@example.org"})).json() == []
    with_revoked = await client.get(
        "/api-tokens/", params={"owner_email": "researcher@example.org", "include_revoked": "true"}
    )
    assert len(with_revoked.json()) == 1


async def test_rejects_bad_hash_and_duplicates(client: AsyncClient):
    bad = await client.post(
        "/api-tokens/", json={"token_hash": "plain-token", "token_hint": "x", "owner_email": "a@b.c", "name": "n"}
    )
    assert bad.status_code == 422
    await _create(client, "wrt_dup-token")
    dup = await client.post(
        "/api-tokens/",
        json={"token_hash": _hash("wrt_dup-token"), "token_hint": "oken", "owner_email": "a@b.c", "name": "n"},
    )
    assert dup.status_code in (400, 409)  # 409 on Postgres, sqlite maps it differently


async def test_revoke_unknown(client: AsyncClient):
    response = await client.post(
        "/api-tokens/00000000-0000-0000-0000-000000000000/revoke", json={"revoked_by": "a@b.c"}
    )
    assert response.status_code == 404
