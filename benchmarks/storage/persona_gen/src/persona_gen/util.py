"""Small numeric helpers shared across layers."""

from collections.abc import Mapping, Sequence

import numpy as np


def interp_table(table: Sequence[Sequence[float]], x: float) -> float:
    """Linear interpolation in a table of ``(x, y)`` rows; clamps outside the range."""
    xs = [float(row[0]) for row in table]
    ys = [float(row[1]) for row in table]
    return float(np.interp(x, xs, ys))


def lognormal(rng: np.random.Generator, spec: Sequence[float], size: int | None = None):
    median, sigma = float(spec[0]), float(spec[1])
    return rng.lognormal(np.log(median), sigma, size)


def uniform(rng: np.random.Generator, spec: Sequence[float]) -> float:
    return float(rng.uniform(float(spec[0]), float(spec[1])))


def choice(rng: np.random.Generator, weights: Mapping[str, float]) -> str:
    names = list(weights)
    p = np.asarray([float(weights[n]) for n in names])
    return names[int(rng.choice(len(names), p=p / p.sum()))]


def mixture(rng: np.random.Generator, components: Sequence[Sequence[float]], size: int) -> np.ndarray:
    weights = np.asarray([c[0] for c in components], dtype=float)
    medians = np.log(np.asarray([c[1] for c in components], dtype=float))
    sigmas = np.asarray([c[2] for c in components], dtype=float)
    which = (
        rng.choice(len(components), size=size, p=weights / weights.sum())
        if len(components) > 1
        else np.zeros(size, dtype=int)
    )
    return np.exp(medians[which] + sigmas[which] * rng.standard_normal(size))


def mixture_mean(components: Sequence[Sequence[float]]) -> float:
    total = sum(c[0] for c in components)
    return sum(c[0] * c[1] * np.exp(c[2] ** 2 / 2) for c in components) / total


def logistic(x):
    return 1.0 / (1.0 + np.exp(-x))


def fit_lognormal_mixture(gaps: np.ndarray, components: int = 2, iterations: int = 200) -> list[list[float]]:
    """EM fit of a lognormal mixture to positive gaps -> [[weight, median_s, log_sigma], ...]."""
    x = np.log(gaps[gaps > 0])
    if x.size < 20:
        return [[1.0, float(np.exp(np.median(x))) if x.size else 60.0, float(x.std()) if x.size > 1 else 0.5]]
    k = components
    mu = np.quantile(x, np.linspace(0.15, 0.85, k))
    sigma = np.full(k, x.std() / k + 1e-3)
    w = np.full(k, 1 / k)
    for _ in range(iterations):
        dens = w * np.exp(-0.5 * ((x[:, None] - mu) / sigma) ** 2) / sigma
        resp = dens / np.maximum(dens.sum(axis=1, keepdims=True), 1e-300)
        nk = resp.sum(axis=0) + 1e-9
        w = nk / nk.sum()
        mu = (resp * x[:, None]).sum(axis=0) / nk
        sigma = np.sqrt((resp * (x[:, None] - mu) ** 2).sum(axis=0) / nk) + 1e-3
    order = np.argsort(-w)
    return [
        [round(float(w[i]), 4), round(float(np.exp(mu[i])), 3), round(float(sigma[i]), 4)] for i in order if w[i] > 0.02
    ]
