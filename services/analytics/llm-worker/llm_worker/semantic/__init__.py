"""Semantic operators over rendered evidence: natural-language specs, executed by LOTUS (plan §2, §7)."""

from .model import LLMUnavailable, LotusModel
from .operators import OPERATORS, OperatorResult, SemanticOperator, build_operator, register_operator
from .spec import OperatorSpec, SpecError, load_spec

__all__ = [
    "LLMUnavailable",
    "LotusModel",
    "OPERATORS",
    "OperatorResult",
    "OperatorSpec",
    "SemanticOperator",
    "SpecError",
    "build_operator",
    "load_spec",
    "register_operator",
]
