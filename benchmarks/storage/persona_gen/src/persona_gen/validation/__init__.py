"""Validation: structure and traceability, behaviour realism, shape against the exports,
statistical ranges, and recovery of injected effects."""

from .checks import (
    behaviour_report,
    dynamics_report,
    effect_report,
    shape_report,
    statistical_report,
    structure_report,
    validate,
)

__all__ = [
    "behaviour_report",
    "dynamics_report",
    "effect_report",
    "shape_report",
    "statistical_report",
    "structure_report",
    "validate",
]
