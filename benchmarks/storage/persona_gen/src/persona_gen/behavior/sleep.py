"""Sleep architecture: latency, ~90-minute cycles, front-loaded deep, back-loaded REM,
brief awakenings, and time in bed before and after sleep."""

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..model import BED_AWAKE, SLEEP_DEEP, SLEEP_LIGHT, SLEEP_REM
from ..util import interp_table, lognormal

MINUTE = 60.0


# TODO(realism): Fit stage transitions and bout duration from staged nights.
def night(
    in_bed: float,
    wake: float,
    *,
    age: float,
    awakenings_multiplier: float,
    latency_extra_minutes: float,
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> list[tuple[float, float, int]]:
    spec = params["behavior"]["sleep"]
    latency = (float(lognormal(rng, spec["latency_minutes"])) + latency_extra_minutes) * MINUTE
    onset = in_bed + latency
    out_of_bed = wake + float(lognormal(rng, spec["in_bed_after_minutes"])) * MINUTE
    segments: list[tuple[float, float, int]] = []
    if onset >= wake - 20 * MINUTE:  # too short to sleep: lie awake
        return [(in_bed, out_of_bed, BED_AWAKE)]
    segments.append((in_bed, onset, BED_AWAKE))
    deep_by_cycle = spec["deep_first_cycle_fraction"]
    rem_by_cycle = spec["rem_fraction_by_cycle"]
    cursor, cycle = onset, 0
    while cursor < wake:
        length = max(50.0, rng.normal(*spec["cycle_minutes"])) * MINUTE
        if wake - cursor < 1.3 * length:
            length = wake - cursor
        k = min(cycle, len(deep_by_cycle) - 1)
        deep = deep_by_cycle[k] * rng.uniform(0.7, 1.3) * max(0.4, 1.2 - age / 100)
        rem = rem_by_cycle[k] * rng.uniform(0.8, 1.2)
        light = max(0.1, 1 - deep - rem)
        first_light = light * 0.6
        bounds = np.cumsum([0, first_light, deep, light - first_light, rem]) / (
            first_light + deep + light - first_light + rem
        )
        states = (SLEEP_LIGHT, SLEEP_DEEP, SLEEP_LIGHT, SLEEP_REM)
        for state, a, b in zip(states, bounds[:-1], bounds[1:], strict=True):
            if b > a:
                segments.append((cursor + a * length, cursor + b * length, state))
        cursor += length
        cycle += 1
    segments.append((wake, out_of_bed, BED_AWAKE))

    # Brief awakenings, more frequent with age and conditions such as sleep apnea.
    hours = (wake - onset) / 3600
    rate = interp_table(spec["awakenings_per_hour_by_age"], age) * awakenings_multiplier
    count = rng.poisson(rate * hours)
    if count:
        times = np.sort(rng.uniform(onset + 15 * MINUTE, wake - 5 * MINUTE, count))
        lengths = lognormal(rng, spec["awakening_minutes"], count) * MINUTE
        segments = _insert(segments, times, lengths)
    return _merge_short(segments, spec["min_stage_minutes"] * MINUTE)


def _insert(
    segments: list[tuple[float, float, int]], times: np.ndarray, lengths: np.ndarray
) -> list[tuple[float, float, int]]:
    result: list[tuple[float, float, int]] = []
    queue = list(zip(times.tolist(), lengths.tolist(), strict=True))
    for start, end, state in segments:
        cursor = start
        while queue and queue[0][0] < end and state != BED_AWAKE:
            t, length = queue.pop(0)
            if t < cursor:
                continue
            stop = min(end, t + length)
            if t > cursor:
                result.append((cursor, t, state))
            result.append((t, stop, BED_AWAKE))
            cursor = stop
        if cursor < end:
            result.append((cursor, end, state))
        while queue and queue[0][0] < end:
            queue.pop(0)
    return result


def _merge_short(segments: list[tuple[float, float, int]], minimum: float) -> list[tuple[float, float, int]]:
    merged: list[list[float]] = []
    for start, end, state in segments:
        if merged and (merged[-1][2] == state or end - start < minimum):
            merged[-1][1] = end
        else:
            merged.append([start, end, state])
    return [(a, b, int(s)) for a, b, s in merged]
