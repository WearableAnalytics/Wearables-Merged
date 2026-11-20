"""Single-lead ECG waveforms (Apple Watch style, ~30 s at 512 Hz).

Each beat is a sum of Gaussian P, Q, R, S and T waves placed at simulated beat times
(McSharry et al. 2003 use the same wave set in a dynamical model). Atrial fibrillation
drops P waves, makes RR intervals irregular and adds fibrillatory f-waves. Baseline wander
and sensor noise depend on signal quality. Amplitudes are illustrative, not diagnostic.
"""

import numpy as np

# (offset seconds relative to R, amplitude mV, width seconds); T offset scales with RR.
WAVES = (
    ("P", -0.20, 0.15, 0.025),
    ("Q", -0.035, -0.12, 0.010),
    ("R", 0.0, 1.10, 0.011),
    ("S", 0.035, -0.25, 0.012),
    ("T", 0.26, 0.30, 0.050),
)


def waveform(
    mean_hr: float, *, seconds: float, hz: float, afib: bool, quality: float, rng: np.random.Generator
) -> np.ndarray:
    """Synthetic single-lead ECG for ``seconds`` at ``hz`` in microvolts: P, QRS and T waves on jittered RR intervals
    (irregular and without P waves if ``afib``), noisier at low ``quality``.
    """
    n = int(seconds * hz)
    t = np.arange(n) / hz
    rr_mean = 60.0 / float(np.clip(mean_hr, 35, 190))
    count = int(seconds / rr_mean) + 3
    if afib:
        rr = rr_mean * np.exp(rng.normal(0, 0.18, count))
    else:
        phase = rng.uniform(0, 2 * np.pi)
        k = np.arange(count)
        rr = rr_mean * (1 + 0.04 * np.sin(2 * np.pi * 0.25 * k * rr_mean + phase) + rng.normal(0, 0.01, count))
    beats = rng.uniform(0, rr_mean) + np.concatenate([[0.0], np.cumsum(rr[:-1])])
    signal = np.zeros(n)
    scale = float(np.exp(rng.normal(0, 0.12)))
    for name, offset, amplitude, width in WAVES:
        if afib and name == "P":
            continue
        for beat, interval in zip(beats, rr, strict=True):
            center = beat + (offset * np.sqrt(interval / 0.8) if name == "T" else offset)
            lo, hi = int((center - 5 * width) * hz), int((center + 5 * width) * hz) + 1
            if hi <= 0 or lo >= n:
                continue
            sl = slice(max(lo, 0), min(hi, n))
            signal[sl] += amplitude * scale * np.exp(-0.5 * ((t[sl] - center) / width) ** 2)
    if afib:
        signal += 0.05 * np.sin(2 * np.pi * rng.uniform(4, 8) * t + rng.uniform(0, 2 * np.pi)) * rng.uniform(0.5, 1.5)
    signal += 0.06 * np.sin(2 * np.pi * rng.uniform(0.15, 0.4) * t + rng.uniform(0, 2 * np.pi))
    signal += rng.normal(0, 0.01 + 0.08 * (1 - quality), n)
    return (signal * 1000.0).astype(np.float32)  # microvolts


def classify(mean_hr: float, afib: bool, quality: float) -> str:
    if quality < 0.55:
        return "inconclusive_poor_reading"
    if mean_hr > 120:
        return "inconclusive_high_heart_rate"
    if mean_hr < 50:
        return "inconclusive_low_heart_rate"
    return "atrial_fibrillation" if afib else "sinus_rhythm"
