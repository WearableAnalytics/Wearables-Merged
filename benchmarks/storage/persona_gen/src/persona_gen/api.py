"""Public library API: recipes, dataset generation, sharding and row estimates.

Generate once, store, then load: datasets are written to Parquet (partitioned by persona
shard, and by month for large tables) with a manifest recording the recipe, parameter
versions and checksums.
"""

import json
import os
import shutil
import time
from collections import Counter
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from multiprocessing import get_context
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import numpy as np

from .config import PARAMS_DIR, Params, load_params
from .persona.sampler import PersonaContext, assign_roster
from .persona.synthea import load_roster, roster_identity
from .rng import global_stream
from .simulate import SimulationContext, simulate_persona
from .timeutil import utc_seconds

GENERATOR = "wearable-personas"
GENERATOR_VERSION = "2.1.0"
TABLES = (
    "personas",
    "devices",
    "events",
    "observations",
    "workouts",
    "app_sync",
    "truth_intervals",
    "truth_days",
    "truth_nights",
    "truth_workouts",
    "truth_wear",
    "truth_hrv",
    "routes",
    "ecg",
)


@dataclass(frozen=True, slots=True)
class SyntheticRecipe:
    """A UTC date window and a contiguous range of zero-based persona indices."""

    start: date
    days: int
    personas: int
    seed: int
    first_persona: int = 0
    twins: bool = False  # leading persona indices use comparison anchors
    metrics: tuple[str, ...] | None = None  # optional whitelist to control density
    # Wearable-only runs are plain (no illness, injury, mood episodes or travel) unless True. Clinical (Synthea) and
    # anchor runs always have them; False is rejected there. None lets the mode decide.
    everyday_events: bool | None = None

    def __post_init__(self) -> None:
        if self.days < 1 or self.personas < 1 or self.first_persona < 0 or self.seed < 0:
            raise ValueError("days and personas must be positive; first_persona and seed nonnegative")

    @property
    def end(self) -> date:
        return self.start + timedelta(days=self.days)

    def indices(self) -> range:
        return range(self.first_persona, self.first_persona + self.personas)

    def describe(self) -> dict[str, Any]:
        """Recipe as a JSON-serializable dict for the manifest (``everyday_events`` is recorded separately)."""
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["metrics"] = list(self.metrics) if self.metrics else None
        del data["everyday_events"]  # resolved per dataset and recorded at the top level of the manifest
        return data


@dataclass(frozen=True, slots=True)
class _Job:
    recipe: SyntheticRecipe
    shard: int
    indices: tuple[int, ...]
    params_dir: str
    overlays: tuple[str, ...]
    synthea_dir: str | None
    store_rr: bool
    root: str


def resolve_everyday_events(recipe: SyntheticRecipe, params: Params, synthea_dir: str | Path | None) -> bool:
    """Whether illness, injury, mood episodes and travel are simulated.

    Clinical (Synthea) and anchor runs always have them. Wearable-only runs are plain unless asked for.
    """
    if synthea_dir is not None or recipe.twins or params["cohorts"]["anchors"]["share"]:
        if recipe.everyday_events is False:
            raise ValueError(
                "everyday_events=False needs a wearable-only dataset (no Synthea roster, twins or anchors)"
            )
        return True
    return recipe.everyday_events is True


def _context(recipe: SyntheticRecipe, params: Params, synthea_dir: str | None, store_rr: bool) -> SimulationContext:
    everyday_events = resolve_everyday_events(recipe, params, synthea_dir)
    roster = assignment = None
    if synthea_dir is not None:
        if recipe.twins or params["cohorts"]["anchors"]["share"]:
            raise ValueError("Synthea runs require anchor share 0 and twins disabled")
        roster = load_roster(Path(synthea_dir))
        order = global_stream(recipe.seed, "synthea-roster").permutation(len(roster))
        assignment = assign_roster(
            params, recipe.seed, recipe.twins, (recipe.start, recipe.end), roster, order, recipe.indices()
        )
    persona_ctx = PersonaContext(
        params,
        recipe.seed,
        (recipe.start, recipe.end),
        recipe.twins,
        roster,
        assignment,
        wearable_only=synthea_dir is None,
    )
    return SimulationContext(
        params,
        recipe.seed,
        recipe.start,
        recipe.days,
        recipe.twins,
        persona_ctx,
        store_rr,
        frozenset(recipe.metrics) if recipe.metrics else None,
        everyday_events,
    )


def _run_shard(job: _Job) -> dict[str, Any]:
    from .output.writer import ShardWriter

    params = load_params(Path(job.params_dir), [Path(p) for p in job.overlays])
    ctx = _context(job.recipe, params, job.synthea_dir, job.store_rr)
    writer = ShardWriter(Path(job.root), job.shard)
    started = time.perf_counter()
    archetype_rows: Counter[str] = Counter()
    archetype_personas: Counter[str] = Counter()
    for index in job.indices:
        tables = simulate_persona(index, ctx)
        devices = tables["devices"]
        archetypes = {
            a for a, r in zip(devices.get("archetype", []), devices.get("role", []), strict=True) if r == "wearable"
        }
        label = "native" if "native" in archetypes else "companion" if "companion" in archetypes else "phone_only"
        archetype_personas[label] += 1
        archetype_rows[label] += len(tables["observations"].get("start", ()))
        for name in TABLES:
            writer.add(name, tables.get(name, {}))
    report = writer.close()
    report["seconds"] = time.perf_counter() - started
    report["personas"] = len(job.indices)
    report["archetype_personas"] = dict(archetype_personas)
    report["archetype_rows"] = dict(archetype_rows)
    return report


def _with_fitted(
    overlays: Iterable[Path], fitted_defaults: bool, home: Path | None, kaggle_csv: Path | None
) -> tuple[Path, ...]:
    """Caller overlays after the fitted defaults, so a caller can still override them."""
    chosen = tuple(Path(p) for p in overlays)
    if not fitted_defaults:
        return chosen
    from .calibration.zepp import fitted_overlays

    return (*fitted_overlays(home=home, kaggle_csv=kaggle_csv), *chosen)


def generate_dataset(
    out: Path,
    recipe: SyntheticRecipe,
    *,
    params_dir: Path = PARAMS_DIR,
    overlays: Iterable[Path] = (),
    synthea_dir: Path | None = None,
    personas_per_shard: int = 250,
    workers: int = 1,
    store_rr: bool = False,
    scenario: str | None = None,
    fitted_defaults: bool = False,
    home: Path | None = None,
    kaggle_csv: Path | None = None,
) -> Path:
    """Generate a dataset offline and return the path to its manifest.

    ``fitted_defaults`` enables the Zepp/Amazfit overlay fitted from the Kaggle export and
    cached under ``home``. Caller overlays are applied after fitted defaults.

    Persona ``i`` is identical whether generated alone, in any shard, or in a full run.
    Parallel workers use the ``spawn`` start method; call from a ``__main__`` guard.
    """
    if personas_per_shard < 1 or workers < 1:
        raise ValueError("personas_per_shard and workers must be positive")
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    overlays = _with_fitted(overlays, fitted_defaults, home, kaggle_csv)
    params = load_params(params_dir, overlays)  # validate before spawning workers
    everyday_events = resolve_everyday_events(recipe, params, synthea_dir)
    roster = roster_identity(Path(synthea_dir)) if synthea_dir is not None else None
    if synthea_dir is not None:
        mode, clinical_source = "clinical", "synthea"
    elif recipe.twins or params["cohorts"]["anchors"]["share"]:
        mode, clinical_source = "anchor_comparison", "anchor"
    else:
        mode, clinical_source = "wearable_only", "none"
    out.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        jobs = []
        indices = list(recipe.indices())
        for offset in range(0, len(indices), personas_per_shard):
            chunk = tuple(indices[offset : offset + personas_per_shard])
            jobs.append(
                _Job(
                    recipe,
                    chunk[0] // personas_per_shard,
                    chunk,
                    str(params_dir),
                    tuple(str(p) for p in overlays),
                    str(synthea_dir) if synthea_dir else None,
                    store_rr,
                    str(temp),
                )
            )
        started = time.perf_counter()
        if workers == 1 or len(jobs) == 1:
            reports = [_run_shard(job) for job in jobs]
        else:
            with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
                reports = list(pool.map(_run_shard, jobs))
        elapsed = time.perf_counter() - started
        rows: Counter[str] = Counter()
        personas: Counter[str] = Counter()
        arch_rows: Counter[str] = Counter()
        for report in reports:
            rows.update(report["rows"])
            personas.update(report["archetype_personas"])
            arch_rows.update(report["archetype_rows"])
        years = recipe.days / 365.25
        manifest = {
            "version": 2,
            "dataset": "synthetic",
            "origin": "synthetic",
            "generator": {"name": GENERATOR, "version": GENERATOR_VERSION},
            "recipe": recipe.describe(),
            "params": params.describe(),
            "mode": mode,
            **({"scenario": scenario} if scenario else {}),
            **({"everyday_events": everyday_events} if mode == "wearable_only" else {}),
            "clinical_source": clinical_source,
            **({"synthea_roster": roster} if roster else {}),
            "layout": {
                "partitioning": "hive",
                "large_tables": "shard/month",
                "other_tables": "shard",
                "timestamps": "UTC; offsets in minutes alongside",
                "row_order": "patient, time",
            },
            "tables": {name: rows.get(name, 0) for name in TABLES},
            "shards": [
                {k: v for k, v in r.items() if k not in ("seconds",)} for r in sorted(reports, key=lambda r: r["shard"])
            ],
            "observation_rows_per_persona_year": {
                label: arch_rows[label] / (personas[label] * years) for label in personas if personas[label]
            },
            "personas_by_device_archetype": dict(personas),
            "run": {  # Not part of the logical dataset; varies between machines.
                "seconds": round(elapsed, 3),
                "workers": workers,
                "observations_per_second": round(rows.get("observations", 0) / max(elapsed, 1e-9), 1),
                "personas_per_second": round(recipe.personas / max(elapsed, 1e-9), 3),
            },
        }
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, out)
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return out / "manifest.json"


def estimate_rows(
    recipe: SyntheticRecipe,
    *,
    params_dir: Path = PARAMS_DIR,
    overlays: Iterable[Path] = (),
    synthea_dir: Path | None = None,
    pilot_personas: int = 40,
    pilot_days: int = 14,
    fitted_defaults: bool = False,
    home: Path | None = None,
    kaggle_csv: Path | None = None,
) -> dict[str, Any]:
    """Estimate dataset size from a small pilot simulation before a large run."""
    params = load_params(params_dir, _with_fitted(overlays, fitted_defaults, home, kaggle_csv))
    pilot = replace(
        recipe,
        personas=min(pilot_personas, recipe.personas),
        days=min(pilot_days, recipe.days),
        first_persona=recipe.first_persona,
    )
    ctx = _context(recipe, params, str(synthea_dir) if synthea_dir is not None else None, False)
    ctx = replace(ctx, days=pilot.days)
    rows: Counter[str] = Counter()
    initial_devices = 0
    window_start = utc_seconds(pilot.start)
    per_arch: dict[str, list[float]] = {}
    for index in pilot.indices():
        tables = simulate_persona(index, ctx)
        for name in TABLES:
            cols = tables.get(name, {})
            rows[name] += len(next(iter(cols.values()))) if cols else 0
        devices = tables["devices"]
        initial_devices += sum(t <= window_start for t in devices.get("start", ()))
        archetypes = {
            a for a, r in zip(devices.get("archetype", []), devices.get("role", []), strict=True) if r == "wearable"
        }
        label = "native" if "native" in archetypes else "companion" if "companion" in archetypes else "phone_only"
        per_arch.setdefault(label, []).append(len(tables["observations"].get("start", ())) * 365.25 / pilot.days)
    persona_scale = recipe.personas / pilot.personas
    scale = persona_scale * (recipe.days / pilot.days)
    estimated = {name: round(count * scale) for name, count in rows.items()}
    estimated["personas"] = recipe.personas
    # Preserve the simulation's two padded truth days per persona.
    estimated["truth_days"] = recipe.personas * (recipe.days + 2)
    estimated["devices"] = round(initial_devices * persona_scale + (rows["devices"] - initial_devices) * scale)
    return {
        "pilot": pilot.describe(),
        "rows": estimated,
        "observation_rows_per_persona_year": {k: float(np.mean(v)) for k, v in per_arch.items()},
        "approx_observation_bytes": round(rows["observations"] * scale * 24),  # ~24 B/row zstd (assumption)
    }
