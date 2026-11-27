"""Operator specs: what a semantic operator should do, written in natural language (plan §7.3).

A spec is data, not code. The triage rule, the list of benign causes and the explanation style live in
`llm_worker/operators/*.yaml`; changing the clinical definition means editing a spec and bumping its version.
A data scientist or clinician can later write an ad-hoc spec (`OperatorSpec.adhoc`) and run it on the same engine.
"""

from __future__ import annotations

import re
from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_SLOT = re.compile(r"<<(\w+)>>")


class SpecError(ValueError):
    pass


class OperatorSpec(BaseModel):
    name: str
    version: int = 1
    kind: str  # filter | map | anything registered with register_operator
    description: str = ""
    instruction: str  # LOTUS langex: natural language with {column} placeholders
    reasoning: bool = False  # ask the model to reason before answering (LOTUS zero-shot chain of thought)
    max_tokens: int = Field(default=256, gt=0)

    @property
    def ref(self) -> str:
        return f"{self.name}@{self.version}"

    def columns(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.instruction))

    def check_columns(self, available: set[str]) -> None:
        unknown = self.columns() - available
        if unknown:
            raise SpecError(f"{self.ref} references unknown columns {sorted(unknown)}; available: {sorted(available)}")
        if not self.columns():
            raise SpecError(f"{self.ref} must reference at least one column, e.g. {{context}}")

    def fill(self, **slots: str) -> OperatorSpec:
        """Put request text (a question, a criterion) into the spec's <<slots>>.

        Slots carry meaning only: braces in the text are neutralised, so a question can never reference a column.
        """
        missing = set(_SLOT.findall(self.instruction)) - set(slots)
        if missing:
            raise SpecError(f"{self.ref} needs a value for {sorted(missing)}")

        def value(match: re.Match) -> str:
            text = str(slots[match.group(1)]).replace("{", "(").replace("}", ")")
            return _SLOT.sub("", text).strip()

        return self.model_copy(update={"instruction": _SLOT.sub(value, self.instruction)})

    @classmethod
    def adhoc(cls, kind: str, instruction: str, **kwargs) -> OperatorSpec:
        return cls(name=kwargs.pop("name", "adhoc"), kind=kind, instruction=instruction, **kwargs)

    @classmethod
    def from_file(cls, path: Path) -> OperatorSpec:
        return cls.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def load_spec(name: str) -> OperatorSpec:
    """Load a bundled spec from llm_worker/operators/<name>.yaml."""
    path = files("llm_worker.operators").joinpath(f"{name}.yaml")
    if not path.is_file():
        raise SpecError(f"no bundled operator spec named {name!r}")
    return OperatorSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
