"""Deterministic, order-independent random streams.

Every stream is derived from ``SeedSequence(recipe_seed, spawn_key=(persona, *names))``.
Names are hashed to stable integers, so adding a new stream never shifts existing ones,
and persona ``i`` draws the same numbers whether it is generated alone, in a shard or in
a full run.
"""

from functools import lru_cache
from hashlib import blake2b

import numpy as np

type Key = str | int


@lru_cache(maxsize=4096)
def _word(name: str) -> int:
    return int.from_bytes(blake2b(name.encode("utf-8"), digest_size=4).digest(), "little")


def _key(part: Key) -> int:
    if isinstance(part, int):
        if part < 0:
            raise ValueError("Stream keys must be nonnegative")
        return part
    return _word(part)


def stream(seed: int, persona: int, *names: Key) -> np.random.Generator:
    if seed < 0 or persona < 0:
        raise ValueError("Seed and persona index must be nonnegative")
    sequence = np.random.SeedSequence(seed, spawn_key=(persona, *map(_key, names)))
    return np.random.Generator(np.random.PCG64(sequence))


class Streams:
    __slots__ = ("persona", "seed")

    def __init__(self, seed: int, persona: int) -> None:
        self.seed = seed
        self.persona = persona

    def __call__(self, *names: Key) -> np.random.Generator:
        return stream(self.seed, self.persona, *names)


def global_stream(seed: int, *names: Key) -> np.random.Generator:
    sequence = np.random.SeedSequence(seed, spawn_key=(2**32 - 1, *map(_key, names)))
    return np.random.Generator(np.random.PCG64(sequence))
