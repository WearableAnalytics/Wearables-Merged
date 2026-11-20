"""Internal, platform-neutral record model shared by all layers.

Truth and observations are separate. Every observation carries ``truth_kind`` and
``truth_seq`` pointing to the ground-truth row it was derived from, plus patient,
device and wearable identifiers that stay stable across a dataset.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

# Behaviour states (truth). Sleep stages are states, so HR can be evaluated uniformly.
SEDENTARY, LIGHT, WALK, COMMUTE, WORKOUT, BED_AWAKE, SLEEP_LIGHT, SLEEP_DEEP, SLEEP_REM = range(9)
STATE_NAMES = (
    "sedentary",
    "light",
    "walk",
    "commute",
    "workout",
    "bed_awake",
    "sleep_light",
    "sleep_deep",
    "sleep_rem",
)
SLEEP_STATES = frozenset({BED_AWAKE, SLEEP_LIGHT, SLEEP_DEEP, SLEEP_REM})
ASLEEP_STATES = frozenset({SLEEP_LIGHT, SLEEP_DEEP, SLEEP_REM})

# Measurement contexts used by device policies.
CONTEXTS = ("workout", "sleep", "still", "moving")
CTX_WORKOUT, CTX_SLEEP, CTX_STILL, CTX_MOVING = range(4)

# Truth tables an observation can reference.
TRUTH_KINDS = ("interval", "night", "workout", "day", "hrv_window", "event", "manual")


@dataclass(slots=True)
class Event:
    kind: str
    start: float
    end: float | None = None
    code: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Medication:
    cls: str
    name: str
    start: date
    stop: date | None
    rhr_delta: float = 0.0
    source: str = "sampled"
    params: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Condition:
    name: str
    onset: date
    stop: date | None = None
    code: str | None = None
    source: str = "sampled"


@dataclass(frozen=True, slots=True)
class Coded:
    """Dictionary-encoded column: integer codes (-1 = null) into a small list of values."""

    codes: np.ndarray
    values: list[Any]

    def __len__(self) -> int:
        return int(self.codes.size)

    def take(self, index: np.ndarray) -> Coded:
        return Coded(self.codes[index], self.values)

    @staticmethod
    def concat(parts: list[Coded]) -> Coded:
        values: list[Any] = []
        lookup: dict[Any, int] = {}
        out = []
        for part in parts:
            remap = np.asarray([lookup.setdefault(v, len(lookup)) for v in part.values] + [-1], dtype=np.int32)
            out.append(remap[np.where(part.codes < 0, len(part.values), part.codes)])
        values = list(lookup)
        return Coded(np.concatenate(out) if out else np.zeros(0, dtype=np.int32), values)
