from strawberry.relay.utils import from_base64


def invalid_cursor_argument(argument_name: str) -> TypeError:
    return TypeError(f"Argument '{argument_name}' contains a non-existing value.")


def decode_base64_cursor(cursor: str, expected_prefix: str, argument_name: str) -> str:
    try:
        prefix, payload = from_base64(cursor)
    except ValueError as exc:
        raise invalid_cursor_argument(argument_name) from exc

    if prefix != expected_prefix:
        raise invalid_cursor_argument(argument_name)

    return payload
