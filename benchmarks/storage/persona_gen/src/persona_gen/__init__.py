"""Synthetic wearable persona generator.

Layers: persona -> behaviour -> physiology -> devices -> delivery -> output. Platform rules are parameters
(``params/platforms.toml``), not a package.
Ground truth and device observations are stored separately and linked by
``truth_kind``/``truth_seq``. Parameters live in versioned TOML files under ``params/``.

    from persona_gen import SyntheticRecipe, generate_dataset
    manifest = generate_dataset(Path(".local/personas"), SyntheticRecipe(date(2026, 1, 1), 28, 100, seed=42))
"""

from .api import GENERATOR_VERSION, TABLES, SyntheticRecipe, estimate_rows, generate_dataset
from .config import PARAMS_DIR, Params, load_params
from .dataset import Dataset, open_dataset

__all__ = [
    "GENERATOR_VERSION",
    "PARAMS_DIR",
    "TABLES",
    "Dataset",
    "Params",
    "SyntheticRecipe",
    "estimate_rows",
    "generate_dataset",
    "load_params",
    "open_dataset",
]
