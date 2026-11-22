"""Semantic operators (LOTUS) behind one registry, so new kinds plug in without touching existing ones.

    @register_operator("agg")
    class SemAgg: ...          # a later PR: LOTUS sem_agg for "summarise these nights" questions

The worker only calls `build_operator(spec, columns)` and then `op(df, model)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from .model import LotusModel
from .spec import OperatorSpec, SpecError

_SUFFIX = "_sem"


@dataclass(frozen=True)
class OperatorResult:
    values: list[Any]  # filter: True / False / None (unparseable); map: text
    rationales: list[str | None]
    raw: list[str | None]


class SemanticOperator(Protocol):
    spec: OperatorSpec

    def __call__(self, df: pd.DataFrame, model: LotusModel) -> OperatorResult: ...


OPERATORS: dict[str, type] = {}


def register_operator(kind: str):
    def decorate(cls):
        OPERATORS[kind] = cls
        return cls

    return decorate


def build_operator(spec: OperatorSpec, columns: set[str]) -> SemanticOperator:
    if spec.kind not in OPERATORS:
        raise SpecError(f"unknown operator kind {spec.kind!r}; registered: {sorted(OPERATORS)}")
    spec.check_columns(columns)
    return OPERATORS[spec.kind](spec)


@register_operator("filter")
class SemFilter:
    """Natural-language predicate per row. An answer that is neither clearly true nor false becomes None."""

    def __init__(self, spec: OperatorSpec):
        self.spec = spec

    def __call__(self, df: pd.DataFrame, model: LotusModel) -> OperatorResult:
        from lotus.types import ReasoningStrategy

        if df.empty:
            return OperatorResult([], [], [])
        with model.session(self.spec.max_tokens):
            out = df.reset_index(drop=True).sem_filter(
                self.spec.instruction,
                return_all=True,
                return_raw_outputs=True,
                return_explanations=self.spec.reasoning,
                strategy=ReasoningStrategy.ZS_COT if self.spec.reasoning else None,
                default=True,
                suffix=_SUFFIX,
                progress_bar_desc=self.spec.ref,
            )
        raw = [None if r is None else str(r) for r in out[f"raw_output{_SUFFIX}"]]
        values = [_parse_bool(r) for r in raw]
        rationales = _column(out, f"explanation{_SUFFIX}", len(df))
        return OperatorResult(values=values, rationales=rationales, raw=raw)


@register_operator("map")
class SemMap:
    """Natural-language transformation per row (e.g. an explanation for the clinician)."""

    def __init__(self, spec: OperatorSpec):
        self.spec = spec

    def __call__(self, df: pd.DataFrame, model: LotusModel) -> OperatorResult:
        if df.empty:
            return OperatorResult([], [], [])
        with model.session(self.spec.max_tokens):
            out = df.reset_index(drop=True).sem_map(
                self.spec.instruction,
                return_raw_outputs=True,
                suffix=_SUFFIX,
                progress_bar_desc=self.spec.ref,
            )
        values = [None if v is None else str(v) for v in out[_SUFFIX]]
        raw = _column(out, f"raw_output{_SUFFIX}", len(df))
        return OperatorResult(values=values, rationales=[None] * len(df), raw=raw)


def _parse_bool(raw: str | None) -> bool | None:
    """Read the final answer only (after 'Answer:' when the model reasoned first); exactly one of true/false."""
    if raw is None:
        return None
    answer = raw.rsplit("Answer:", 1)[-1].lower()
    has_true, has_false = "true" in answer, "false" in answer
    if has_true == has_false:
        return None
    return has_true


def _column(df: pd.DataFrame, name: str, n: int) -> list[str | None]:
    if name not in df.columns:
        return [None] * n
    return [None if v is None or v == "" else str(v) for v in df[name]]
