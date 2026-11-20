"""Beat-to-beat (RR) windows and HRV metrics computed from them.

Each window's RR series combines respiratory sinus arrhythmia (HF), a 0.1 Hz baroreflex
component (LF) and white variability. The deviation is scaled so the window's true RMSSD
equals the latent target; SDNN then follows from the persona's LF/HF mix, so SDNN and
RMSSD are different (but mutually consistent) metrics from the same beats.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(slots=True)
class Windows:
    rr: np.ndarray  # (windows, beats) ms, NaN padded
    count: np.ndarray  # beats per window
    sdnn: np.ndarray
    rmssd: np.ndarray


def rmssd_of(rr: np.ndarray) -> np.ndarray:
    diff = np.diff(rr, axis=1)
    return np.sqrt(np.nanmean(diff**2, axis=1))


def sdnn_of(rr: np.ndarray) -> np.ndarray:
    return np.nanstd(rr, axis=1, ddof=1)


def simulate(
    mean_hr: np.ndarray,
    target_rmssd: np.ndarray,
    respiratory_rate: np.ndarray,
    lf_hf: float,
    params: Mapping[str, Any],
    rng: np.random.Generator,
) -> Windows:
    """Simulate RR windows from mean heart rate, target RMSSD, respiratory rate and LF/HF ratio."""
    spec = params["physiology"]["hrv"]
    window = float(spec["window_seconds"])
    m = mean_hr.size
    if m == 0:
        empty = np.zeros(0)
        return Windows(np.zeros((0, 0)), empty.astype(int), empty, empty)
    rr_mean = 60_000.0 / np.clip(mean_hr, 35, 200)
    beats = np.ceil(window * 1000 / rr_mean).astype(int) + 1
    width = int(beats.max())
    k = np.arange(width)[None, :]
    t = k * rr_mean[:, None] / 1000.0
    phase_hf = rng.uniform(0, 2 * np.pi, (m, 1))
    phase_lf = rng.uniform(0, 2 * np.pi, (m, 1))
    f_resp = (respiratory_rate / 60.0)[:, None] * np.exp(rng.normal(0, 0.05, (m, 1)))
    hf = np.sin(2 * np.pi * f_resp * t + phase_hf)
    lf = np.sqrt(lf_hf) * 3.2 * np.sin(2 * np.pi * spec["lf_frequency_hz"] * t + phase_lf)
    white = rng.standard_normal((m, width)) * spec["white_fraction"]
    dev = hf + lf + white
    mask = k < beats[:, None]
    dev = np.where(mask, dev, np.nan)
    scale = target_rmssd / rmssd_of(dev)
    rr = rr_mean[:, None] + dev * scale[:, None]
    rr = np.clip(rr, spec["rr_min_ms"], spec["rr_max_ms"])
    return Windows(rr, beats, sdnn_of(rr), rmssd_of(rr))
