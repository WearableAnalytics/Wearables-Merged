"""Compare a twin with its input export using matplotlib from the ``plots`` extra.

Plots can contain measurements from the input export.
"""

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.compute as pc

from ..dataset import Dataset
from .checks import _col


def twin_daily(ds: Dataset, patient_id: str, source_name: str) -> dict[str, dict[str, float]]:
    obs = ds.table(
        "observations",
        columns=["patient_id", "source_name", "metric", "start", "end", "start_offset_min", "value", "category"],
        filter=(pc.field("patient_id") == patient_id) & (pc.field("source_name") == source_name),
    )
    days: dict[str, dict[str, float]] = defaultdict(lambda: {"hr_records": 0.0, "steps": 0.0, "asleep_hours": 0.0})
    metric, value, category = _col(obs, "metric"), _col(obs, "value"), _col(obs, "category")
    start, end, offset = _col(obs, "start"), _col(obs, "end"), _col(obs, "start_offset_min")
    local = (start + offset * 60).astype("datetime64[s]").astype("datetime64[D]").astype(str)
    wake_day = (end + offset * 60).astype("datetime64[s]").astype("datetime64[D]").astype(str)
    for m, v, c, d, w, a, b in zip(metric, value, category, local, wake_day, start, end, strict=True):
        if m == "heart_rate":
            days[d]["hr_records"] += 1
        elif m == "steps":
            days[d]["steps"] += float(v)
        elif m == "sleep" and c and str(c).startswith("asleep"):
            days[w]["asleep_hours"] += (b - a) / 3600
    return dict(sorted(days.items()))


def plot_twin(
    real: Mapping[str, Mapping[str, float]],
    twin: Mapping[str, Mapping[str, float]],
    path: Path,
    *,
    title: str,
    profile: Mapping[str, Any] | None = None,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    keys = (
        ("hr_records", "Heart-rate records per day"),
        ("steps", "Steps per day (wearable)"),
        ("asleep_hours", "Asleep hours (night ending that day)"),
    )
    fig, axes = plt.subplots(len(keys) + 1, 1, figsize=(10, 11), constrained_layout=True)
    all_days = sorted(set(real) | set(twin))
    span = (
        np.arange(np.datetime64(all_days[0], "D"), np.datetime64(all_days[-1], "D") + 1)
        if all_days
        else np.zeros(0, dtype="datetime64[D]")
    )
    for ax, (key, label) in zip(axes, keys, strict=False):
        for series, name, style in ((real, "real export", "-"), (twin, "synthetic twin", "--")):
            x = span  # days without records plot as zero, so gaps are visible
            y = np.asarray([series.get(str(d), {}).get(key, 0.0) for d in span])
            ax.plot(x, y, style, marker="o", markersize=3, label=name)
        ax.set_title(label)
        ax.legend(loc="upper right")
    ax = axes[-1]
    if profile is not None and "gap" in profile:
        q = ["p5", "p25", "p50", "p75", "p95"]
        width = 0.38
        positions = np.arange(len(q))
        ax.bar(positions - width / 2, profile["gap"]["real"], width, label="real export")
        ax.bar(positions + width / 2, profile["gap"]["synthetic"], width, label="synthetic twin")
        ax.set_xticks(positions, q)
        ax.set_yscale("log")
        ax.set_title("Heart-rate inter-sample gap quantiles (s)")
        ax.legend()
    else:
        ax.axis("off")
    fig.suptitle(title)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
