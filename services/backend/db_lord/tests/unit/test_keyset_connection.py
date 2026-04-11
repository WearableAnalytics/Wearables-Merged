from uuid import UUID, uuid7

import pytest
from strawberry.relay.utils import to_base64

from app.graphql.cursor_codec import decode_base64_cursor
from app.graphql.keyset_connection import (
    KEYSET_CURSOR_PREFIX,
    derive_page_flags,
    resolve_pagination_window,
)


def test_encode_decode_keyset_cursor_round_trip() -> None:
    node_id = uuid7()
    encoded = to_base64(KEYSET_CURSOR_PREFIX, str(node_id))
    decoded = UUID(
        decode_base64_cursor(
            cursor=encoded,
            expected_prefix=KEYSET_CURSOR_PREFIX,
            argument_name="after",
        )
    )
    assert decoded == node_id


def test_decode_keyset_cursor_rejects_wrong_prefix() -> None:
    cursor = to_base64("wrong-prefix", str(uuid7()))
    with pytest.raises(TypeError, match="Argument 'after' contains a non-existing value."):
        decode_base64_cursor(
            cursor=cursor,
            expected_prefix=KEYSET_CURSOR_PREFIX,
            argument_name="after",
        )


def test_decode_keyset_cursor_rejects_invalid_uuid_payload() -> None:
    cursor = to_base64(KEYSET_CURSOR_PREFIX, "not-a-uuid")
    with pytest.raises(ValueError):
        UUID(
            decode_base64_cursor(
                cursor=cursor,
                expected_prefix=KEYSET_CURSOR_PREFIX,
                argument_name="after",
            )
        )


def test_decode_keyset_cursor_rejects_malformed_base64() -> None:
    with pytest.raises(TypeError, match="Argument 'after' contains a non-existing value."):
        decode_base64_cursor(
            cursor="not-a-valid-cursor",
            expected_prefix=KEYSET_CURSOR_PREFIX,
            argument_name="after",
        )


def test_resolve_pagination_window_first() -> None:
    window = resolve_pagination_window(first=5, last=None, max_allowed=10)
    assert window.page_size == 5
    assert window.fetch_backward is False


def test_resolve_pagination_window_last() -> None:
    window = resolve_pagination_window(first=None, last=3, max_allowed=10)
    assert window.page_size == 3
    assert window.fetch_backward is True


def test_resolve_pagination_window_defaults_to_max_allowed() -> None:
    window = resolve_pagination_window(first=None, last=None, max_allowed=10)
    assert window.page_size == 10
    assert window.fetch_backward is False


def test_resolve_pagination_window_rejects_first_and_last_together() -> None:
    with pytest.raises(ValueError, match="Arguments 'first' and 'last' cannot both be provided."):
        resolve_pagination_window(first=1, last=1, max_allowed=10)


@pytest.mark.parametrize("arg_name", ["first", "last"])
def test_resolve_pagination_window_rejects_negative_values(arg_name: str) -> None:
    kwargs = {"first": None, "last": None, "max_allowed": 10}
    kwargs[arg_name] = -1
    with pytest.raises(ValueError, match="non-negative integer"):
        resolve_pagination_window(**kwargs)


@pytest.mark.parametrize("arg_name", ["first", "last"])
def test_resolve_pagination_window_rejects_values_above_max(arg_name: str) -> None:
    kwargs = {"first": None, "last": None, "max_allowed": 10}
    kwargs[arg_name] = 11
    with pytest.raises(ValueError, match="cannot be higher than 10"):
        resolve_pagination_window(**kwargs)


def test_derive_page_flags_forward() -> None:
    has_next_page, has_previous_page = derive_page_flags(
        fetch_backward=False,
        has_extra=True,
        before=None,
        after="cursor",
    )
    assert has_next_page is True
    assert has_previous_page is True


def test_derive_page_flags_backward() -> None:
    has_next_page, has_previous_page = derive_page_flags(
        fetch_backward=True,
        has_extra=True,
        before="cursor",
        after=None,
    )
    assert has_next_page is True
    assert has_previous_page is True
