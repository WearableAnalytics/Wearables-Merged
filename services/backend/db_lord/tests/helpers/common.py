import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

from strawberry.relay.utils import from_base64, to_base64


async def eventually[T](
    producer: Callable[[], Awaitable[T]],
    *,
    retries: int = 20,
    delay_seconds: float = 0.25,
    predicate: Callable[[T], bool] = bool,
    message: str | None = None,
) -> T:
    """Poll a producer until its result matches the predicate or retries are exhausted."""
    last_value: T | None = None
    for _ in range(retries):
        last_value = await producer()
        if predicate(last_value):
            return last_value
        await asyncio.sleep(delay_seconds)

    default_message = f"eventually() timed out after {retries} retries; last value: {last_value!r}"
    raise RuntimeError(message or default_message)


def relay_node_id(global_id: str) -> str:
    return from_base64(global_id)[1]


def relay_global_id(type_name: str, node_id: str) -> str:
    return to_base64(type_name, node_id)


def extract_tag_param_values(captured_params: dict[str, object]) -> list[str]:
    values: list[str] = []
    for key, value in captured_params.items():
        if not (key.startswith("tag_val_") or key.startswith("tag_vals_")):
            continue
        if isinstance(value, list):
            values.extend(str(item) for item in value)
            continue
        values.append(str(value))
    return values


async def empty_async_iterator() -> AsyncIterator[None]:
    if False:
        yield None
