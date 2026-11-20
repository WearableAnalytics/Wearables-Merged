"""Fit the Zepp/Amazfit companion-app device overlay from the public Kaggle Apple Health export.

``ensure_zepp_overlay`` converts and adapts the Kaggle CSV, fits the overlay and caches it
under ``<home>/calibration/generated/``. The cache key includes the CSV digest, fit version
and training cutoff. Use ``persona-gen fit-zepp-overlay --force`` to refit from the CSV.

Estimators (each reads the adapted Zepp rows before the training cut):

- HR grid: the most common gap of at least 30 s; record length: the most common positive duration.
- Bursts: a 5-minute block is dense when it holds at least four times the grid's samples; the day, block and
  spacing parameters follow from the dense blocks (see ``fit_zepp``).
- Steps and energy: the most common record duration sets the chunk grid and its end offset.
- Sleep: epoch from the boundary alignment, awake merge from the median awake bout, relabel interval from the
  median asleep bout.
- Write lag: three-component lognormal mixtures of positive ``created - end`` lags for HR, steps and sleep.

Anything the data cannot tell (ownership share, charging, step bias, sleep confusion, write bucket) is an
assumption written into the overlay with that label.
"""

import hashlib
import json
import os
import shutil
import warnings
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import duckdb
import numpy as np
import tomli_w

from ..sources.observations import adapt_observations
from ..sources.raw import convert_kaggle
from ..util import fit_lognormal_mixture

MODEL = "zepp_amazfit"
OVERLAY_NAME = "devices-zepp-amazfit.toml"
DATASET_URL = "https://www.kaggle.com/datasets/pacific28/apple-health-data"
LICENSE = "CC BY-NC-SA 4.0"
TRAIN_BEFORE = "2025-01-01"
FIT_VERSION = 1  # bump when an estimator or the overlay layout changes
KAGGLE_CSV = Path("Sample_Health_data/Kaggle_Apple_Health_Data/health_data.csv")
ENV_DISABLE = "PERSONA_GEN_FITTED_DEFAULTS"
ENV_HOME = "PERSONA_GEN_HOME"
ENV_CSV = "PERSONA_GEN_KAGGLE_CSV"
MIN_ROWS = {"heart_rate": 1000, "steps": 100, "sleep": 50}
BLOCK_SECONDS = 300.0
DEFAULT_OWNERSHIP_SHARE = 0.05


def default_home() -> Path:
    """Cache root: ``$PERSONA_GEN_HOME``, ``$BENCH_HOME`` or ``.local``."""
    return Path(os.environ.get(ENV_HOME) or os.environ.get("BENCH_HOME") or ".local")


def find_kaggle_csv(explicit: Path | None = None) -> Path | None:
    """The explicit path, ``$PERSONA_GEN_KAGGLE_CSV``, or the download location above the working directory."""
    if explicit is not None:
        return explicit if explicit.is_file() else None
    if given := os.environ.get(ENV_CSV):
        return Path(given) if Path(given).is_file() else None
    here = Path.cwd().resolve()
    for folder in (here, *here.parents[:6]):
        if (folder / KAGGLE_CSV).is_file():
            return folder / KAGGLE_CSV
    return None


def _mode(values: np.ndarray) -> float:
    return float(Counter(values.tolist()).most_common(1)[0][0])


def fit_zepp(adapted: Path, *, before: str = TRAIN_BEFORE) -> dict[str, Any]:
    date.fromisoformat(before)
    con = duckdb.connect()
    try:
        con.execute(
            """create temp table o as
               select metric, category,
                      epoch(start) + start_offset_min * 60 as s,
                      epoch("end") + end_offset_min * 60 as e,
                      epoch("end") as u,
                      epoch(created_at) as c
               from read_parquet(?)
               where device_model = ? and start < ?::timestamptz""",
            [str(adapted / "observations" / "records.parquet"), MODEL, f"{before}T00:00:00+00:00"],
        )

        def column(metric: str, name: str) -> np.ndarray:
            rows = con.execute(f"select {name} from o where metric = ? order by s", [metric]).fetchnumpy()
            return np.asarray(rows[name], dtype=np.float64)

        hr_s, hr_e = column("heart_rate", "s"), column("heart_rate", "e")
        st_s, st_e = column("steps", "s"), column("steps", "e")
        sleep = con.execute("select category, s, e, c - u from o where metric = 'sleep' order by s").fetchall()
        # Creation is UTC, so lags use the UTC end, not the local-clock end used for durations and alignment.
        hr_lag = column("heart_rate", "c") - column("heart_rate", "u")
        st_lag = column("steps", "c") - column("steps", "u")
    finally:
        con.close()
    for name, count in (("heart_rate", len(hr_s)), ("steps", len(st_s)), ("sleep", len(sleep))):
        if count < MIN_ROWS[name]:
            raise ValueError(f"Too few Zepp {name} rows before {before} to fit an overlay ({count} < {MIN_ROWS[name]})")

    gaps = np.diff(hr_s)
    gaps = gaps[(gaps >= 30) & (gaps <= 600)]
    if not gaps.size:
        raise ValueError("No Zepp heart-rate gaps between 30 and 600 s")
    grid = _mode(np.rint(gaps))
    lengths = np.rint(hr_e - hr_s)
    interval = _mode(lengths[lengths > 0]) if np.any(lengths > 0) else 0.0

    blocks, counts = np.unique(np.floor(hr_s / BLOCK_SECONDS).astype(np.int64), return_counts=True)
    block_day = blocks * int(BLOCK_SECONDS) // 86400
    dense = counts >= 4 * BLOCK_SECONDS / grid
    days = np.unique(block_day)
    burst_days = np.unique(block_day[dense])
    hours = np.unique(np.floor(hr_s / 3600).astype(np.int64))
    hours_per_day = np.unique(hours // 24, return_counts=True)[1]
    burst: dict[str, float] | None = None
    if burst_days.size:
        in_dense = np.isin(np.floor(hr_s / BLOCK_SECONDS).astype(np.int64), blocks[dense])
        spacing = np.diff(hr_s[in_dense])
        spacing = spacing[(spacing > 0) & (spacing < 30)]
        burst = {
            "block_seconds": BLOCK_SECONDS,
            "block_probability": round(float(dense[np.isin(block_day, burst_days)].mean()), 2),
            "sample_seconds": max(1.0, round(2 * float(spacing.mean())) / 2),
            "day_probability": round(burst_days.size / days.size, 2),
        }

    step_length = _mode(np.rint(st_e - st_s)[st_e > st_s])
    step_grid = (
        float(round(step_length / 60) * 60) if abs(step_length - round(step_length / 60) * 60) <= 5 else step_length
    )

    categories = np.asarray([row[0] for row in sleep])
    starts = np.asarray([row[1] for row in sleep])
    lengths_s = np.asarray([row[2] - row[1] for row in sleep])
    awake = lengths_s[categories == "awake"]
    asleep = lengths_s[np.isin(categories, ["asleep_core", "asleep_deep", "asleep_rem"])]
    unspecified = int(np.sum(categories == "asleep_unspecified"))
    in_bed = int(np.sum(categories == "in_bed"))

    lags = {"heart_rate": hr_lag, "steps": st_lag, "sleep": np.asarray([row[3] for row in sleep])}
    return {
        "before": before,
        "rows": {"heart_rate": len(hr_s), "steps": len(st_s), "sleep": len(sleep)},
        "heart_rate": {
            "grid_seconds": grid,
            "grid_interval_seconds": interval,
            "active_hour_probability": round(float(hours_per_day.mean()) / 24, 2),
            "dense_share": round(float(dense.mean()), 3),
            "burst": burst,
        },
        "steps": {"grid_seconds": step_grid, "end_offset_seconds": step_length - step_grid, "length": step_length},
        "sleep": {
            "epoch_seconds": 60.0 if float(np.mean(starts % 60 == 0)) >= 0.9 else 30.0,
            "merge_awake_under_minutes": max(1.0, float(np.ceil(np.median(awake) / 60))) if awake.size else 1.0,
            "relabel_minutes": float(round(np.median(asleep) / 60)) if asleep.size else 10.0,
            "in_bed": in_bed > 0,
            "unspecified_probability": round(unspecified / (unspecified + in_bed), 4) if unspecified else 0.0,
        },
        "write_lag": {name: fit_lognormal_mixture(values[values > 0], 3) for name, values in lags.items()},
    }


def zepp_overlay(stats: dict[str, Any], *, version: str) -> dict[str, Any]:
    """The devices overlay: fitted values from ``stats``, labelled assumptions for the rest."""
    hr, steps, sleep = stats["heart_rate"], stats["steps"], stats["sleep"]
    before = stats["before"]
    chunks = {
        "mode": "chunks",
        "grid_seconds": steps["grid_seconds"],
        "end_offset_seconds": steps["end_offset_seconds"],
        "active_only": True,
    }
    heart: dict[str, Any] = {
        "mode": "samples",
        "grid_seconds": hr["grid_seconds"],
        **({"grid_interval_seconds": hr["grid_interval_seconds"]} if hr["grid_interval_seconds"] else {}),
        "grid_active_hour_probability": hr["active_hour_probability"],
        **({"grid_burst": hr["burst"]} if hr["burst"] else {}),
        "quality": True,
    }
    minute = "whole-minute " if sleep["epoch_seconds"] == 60.0 else ""
    dense = f"dense {BLOCK_SECONDS / 60:g}-minute blocks ({hr['dense_share']:.1%} of observed blocks), "
    return {
        "meta": {"target": "devices", "version": version},
        "ownership": {"ios_wearables": {MODEL: DEFAULT_OWNERSHIP_SHARE}},
        "models": {
            MODEL: {
                "source": "assumption: representative Amazfit optical tracker with shared signal errors; "
                "one Zepp iOS source in Kaggle Apple Health Data; the iOS ownership share is an assumption "
                "that includes this companion class in benchmark workloads",
                "kind": "tracker",
                "platform": "healthkit",
                "archetype": "companion",
                "source_name": "Zepp",
                "hardware": "Amazfit",
                "available_from": "2022-09-01",
                "features": [],
                "writes_rmssd": False,
                "charging_every_days": 6.0,
                "charge_minutes": [70.0, 0.4],
                "charge_hour": [19.0, 3.0],
                "auto_detect_workouts": False,
                "step_bias": [1.0, 0.10],
                "metrics": {
                    "source": f"calibrated: Kaggle Apple Health Data ({LICENSE}), Zepp rows before {before}; "
                    f"{hr['grid_seconds']:g} s HR grid, {dense}{steps['length']:g} s step and energy "
                    f"intervals, {minute}sleep stages",
                    "steps": chunks,
                    "active_energy": dict(chunks),
                    "sleep": {
                        "mode": "sleep",
                        "in_bed": sleep["in_bed"],
                        "unspecified_probability": sleep["unspecified_probability"],
                        "merge_awake_under_minutes": sleep["merge_awake_under_minutes"],
                        "epoch_seconds": sleep["epoch_seconds"],
                        "relabel_minutes": sleep["relabel_minutes"],
                        "naps": True,
                    },
                    "heart_rate": heart,
                },
                "sleep_confusion": {
                    "source": "assumption: generic wearable sleep classification in the absence of a reference PSG",
                    "labels": ["awake", "light", "deep", "rem"],
                    "matrix": [
                        [0.45, 0.45, 0.02, 0.08],
                        [0.07, 0.78, 0.08, 0.07],
                        [0.01, 0.50, 0.48, 0.01],
                        [0.06, 0.50, 0.04, 0.40],
                    ],
                },
                "delivery": {
                    "source": "calibrated: three-component fits to positive creation minus end lags for "
                    f"Zepp HR, steps and sleep before {before}; energy uses the step fit",
                    "write_bucket_seconds": 3600.0,  # assumption: batch boundaries vary, so round writes to the hour
                    "write_lag": {
                        "heart_rate": stats["write_lag"]["heart_rate"],
                        "steps": stats["write_lag"]["steps"],
                        "active_energy": stats["write_lag"]["steps"],
                        "sleep": stats["write_lag"]["sleep"],
                    },
                },
            }
        },
    }


def _header(csv: Path, digest: str) -> str:
    return (
        f"# Generated by persona-gen from Apple Health Data by pacific28 (Kaggle): {DATASET_URL}\n"
        f"# Input {csv.name} sha256 {digest[:16]}, fit version {FIT_VERSION}, "
        f"measurement dates before {TRAIN_BEFORE}.\n\n"
    )


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 << 20):
            sha.update(chunk)
    return sha.hexdigest()


def ensure_zepp_overlay(home: Path | None = None, csv: Path | None = None, *, force: bool = False) -> Path | None:
    """Return the fitted overlay, building it if needed.

    If the CSV is missing, reuse an existing overlay unless ``force`` is set.
    Return ``None`` if no overlay can be returned.
    """
    home = home or default_home()
    generated = home / "calibration" / "generated"
    overlay, meta = generated / OVERLAY_NAME, generated / "zepp.json"
    source = find_kaggle_csv(csv)
    if source is None:
        return overlay if overlay.is_file() and not force else None
    digest = _digest(source)
    key = f"{digest}:{FIT_VERSION}:{TRAIN_BEFORE}"
    if not force and overlay.is_file() and meta.is_file() and json.loads(meta.read_text())["key"] == key:
        return overlay
    work = generated / "zepp"
    shutil.rmtree(work, ignore_errors=True)
    raw, adapted = work / "raw", work / "adapted"
    convert_kaggle(source, raw)
    adapt_observations("kaggle", raw, adapted)
    stats = fit_zepp(adapted)
    text = _header(source, digest) + tomli_w.dumps(
        zepp_overlay(stats, version=f"kaggle-zepp-fit{FIT_VERSION}-{digest[:12]}")
    )
    generated.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", dir=generated, suffix=".tmp", delete=False, encoding="utf-8") as stream:
        stream.write(text)
    os.replace(stream.name, overlay)
    meta.write_text(json.dumps({"key": key, "stats": stats}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return overlay


def fitted_overlays(*, home: Path | None = None, kaggle_csv: Path | None = None, force: bool = False) -> Sequence[Path]:
    """Return fitted default overlays and warn if the enabled fit has no CSV or cached overlay.

    ``PERSONA_GEN_FITTED_DEFAULTS=0`` turns this off, e.g. for tests.
    """
    if os.environ.get(ENV_DISABLE, "1").lower() in {"0", "false", "off", "no"}:
        return ()
    path = ensure_zepp_overlay(home, kaggle_csv, force=force)
    if path is None:
        warnings.warn(
            f"The Kaggle Apple Health file was not found, so the Zepp/Amazfit device model is left out. "
            f"Download it from {DATASET_URL} (or run Sample_Health_data/Kaggle_Apple_Health_Data/download.sh) "
            f"and pass --kaggle-csv or set {ENV_CSV}. The default location is "
            f"{KAGGLE_CSV} in the working directory or one of its parent folders.",
            stacklevel=3,
        )
        return ()
    return (path,)
