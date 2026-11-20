"""Versioned parameter sets.

Parameters live in TOML files under ``params/``. Each file has a ``[meta]`` table with a
``version``. Tables containing parameter values declare or inherit a valid ``source`` label.

Calibration output can be layered on top as *overlays*: TOML files with the same
structure whose tables replace (deep-merge into) the base values.

- Bundled overlays in ``params/defaults/`` are applied in filename order. They include
  the LifeSnaps anchors and Fitbit timing calibration.
- Caller overlays are applied next, in the supplied order.

An overlay's ``[meta]`` may list ``replace = ["dotted.path", ...]``: those tables are
emptied before any overlay in the set is merged. For example,
``replace = ["anchors.profiles"]`` clears the bundled anchors before the supplied
profiles are loaded.
"""

import copy
import hashlib
import tomllib
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

PARAMS_DIR = Path(__file__).with_name("params")
DEFAULTS = "defaults"
FILES = (
    "population",
    "behavior",
    "physiology",
    "clinical",
    "cohorts",
    "devices",
    "platforms",
    "delivery",
    "references",
)
PROVENANCE = ("assumption", "calibrated", "reference", "platform", "spec")


class ParameterError(ValueError):
    pass


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _is_table_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(i, Mapping) for i in value)


def _valid_source(source: Any) -> bool:
    """``assumption`` may stand alone; other labels must say where the value came from."""
    if not isinstance(source, str):
        return False
    kind, _, detail = source.partition(":")
    return kind.strip() in PROVENANCE and (kind.strip() == "assumption" or bool(detail.strip()))


def _check_provenance(table: Mapping[str, Any], path: str, inherited: Any = None) -> None:
    source = table.get("source", inherited)
    if "source" in table and not _valid_source(table["source"]):
        raise ParameterError(f"{path}: invalid source label {table['source']!r}")
    has_values = any(k != "source" and not isinstance(v, Mapping) and not _is_table_list(v) for k, v in table.items())
    if has_values and not _valid_source(source):
        raise ParameterError(f"{path}: values need source = '<{'|'.join(PROVENANCE)}>: ...'")
    for key, value in table.items():
        if isinstance(value, Mapping):
            _check_provenance(value, f"{path}.{key}", source)
        elif _is_table_list(value):
            for index, item in enumerate(value):
                _check_provenance(item, f"{path}.{key}[{index}]", source)


def _reset(tables: dict[str, Any], target: str, dotted: str) -> None:
    """Empty the table at ``target.dotted`` (created if missing)."""
    node = tables[target]
    *parents, leaf = dotted.split(".")
    for part in parents:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise ParameterError(f"replace {target}.{dotted}: {part} is not a table")
    node[leaf] = {}


def _read_overlay(path: Path) -> tuple[bytes, dict[str, Any], Mapping[str, Any]]:
    raw = path.read_bytes()
    data = tomllib.loads(raw.decode("utf-8"))
    meta = data.pop("meta", {})
    return raw, data, meta


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _freeze(v) for k, v in value.items()}
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


@dataclass(frozen=True, slots=True)
class Params(Mapping[str, Any]):
    """Merged parameter set and its provenance. Treat as read-only (plain containers keep it picklable)."""

    tables: Mapping[str, Any]
    versions: Mapping[str, str]
    digest: str
    files: tuple[str, ...] = field(default=())
    recorded: Mapping[str, Any] = field(default_factory=dict)

    def __getitem__(self, name: str) -> Any:
        return self.tables[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self.tables)

    def __len__(self) -> int:
        return len(self.tables)

    def section(self, *path: str) -> Any:
        node: Any = self.tables
        for part in path:
            try:
                node = node[part]
            except KeyError:
                raise ParameterError(f"Missing parameter table {'.'.join(path)}") from None
        return node

    def describe(self) -> dict[str, object]:
        """Manifest entry: versions, SHA-256 digest, file names and the loaded values per file."""
        return {
            "versions": dict(self.versions),
            "sha256": self.digest,
            "files": list(self.files),
            "values": dict(self.recorded),
        }


def load_params(
    base_dir: Path = PARAMS_DIR,
    overlays: Iterable[Path] = (),
    *,
    defaults: bool = True,
) -> Params:
    """Load, merge and validate parameter files: base files, ``defaults/`` overlays
    (unless ``defaults=False``), then ``overlays``."""
    digest = hashlib.sha256()
    tables: dict[str, Any] = {}
    versions: dict[str, str] = {}
    names: list[str] = []
    recorded: dict[str, Any] = {}
    for name in FILES:
        path = base_dir / f"{name}.toml"
        raw = path.read_bytes()
        digest.update(name.encode() + b"\0" + raw + b"\0")
        data = tomllib.loads(raw.decode("utf-8"))
        meta = data.pop("meta", None)
        if not isinstance(meta, Mapping) or not isinstance(meta.get("version"), str):
            raise ParameterError(f"{path.name}: missing [meta] version")
        versions[name] = meta["version"]
        names.append(path.name)
        tables[name] = data
        recorded[path.name] = copy.deepcopy(data)
    layers: list[tuple[str, list[Path]]] = []
    if defaults and (base_dir / DEFAULTS).is_dir():
        layers.append(("default", sorted((base_dir / DEFAULTS).glob("*.toml"))))
    layers.append(("overlay", [p for o in overlays for p in (sorted(o.glob("*.toml")) if o.is_dir() else [o])]))
    for label, paths in layers:
        loaded = []
        for path in paths:
            raw, data, meta = _read_overlay(path)
            target = meta.get("target", path.stem)
            if target not in tables:
                raise ParameterError(f"Overlay {path.name} targets unknown file {target!r}")
            digest.update(f"{label}:".encode() + path.name.encode() + b"\0" + raw + b"\0")
            loaded.append((path, data, meta, target))
        for _, _, meta, target in loaded:  # replaces first, so file order does not matter
            for dotted in meta.get("replace", ()):
                _reset(tables, target, dotted)
        for path, data, meta, target in loaded:
            tables[target] = _deep_merge(tables[target], data)
            versions[f"{label}:{path.name}"] = str(meta.get("version", "unversioned"))
            names.append(f"{label}:{path.name}")
            recorded[f"{label}:{path.name}"] = {"meta": dict(meta), "data": copy.deepcopy(data)}
    for name, data in tables.items():
        _check_provenance(data, name)
    return Params(_freeze(tables), dict(versions), digest.hexdigest(), tuple(names), recorded)


def build[T](cls: type[T], table: Mapping[str, Any], *, path: str = "") -> T:
    if not is_dataclass(cls):
        raise TypeError(cls)
    hints = get_type_hints(cls)
    names = {f.name for f in fields(cls)}
    provided = {k for k in table if k != "source"}
    unknown = provided - names
    if unknown:
        raise ParameterError(f"{path or cls.__name__}: unknown keys {sorted(unknown)}")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in table:
            continue
        kwargs[f.name] = _coerce(hints[f.name], table[f.name], f"{path}.{f.name}")
    try:
        return cls(**kwargs)
    except TypeError as error:
        raise ParameterError(f"{path or cls.__name__}: {error}") from None


def _coerce(hint: Any, value: Any, path: str) -> Any:
    origin = get_origin(hint)
    if is_dataclass(hint) and isinstance(value, Mapping):
        return build(hint, value, path=path)  # type: ignore[arg-type]
    if origin is tuple and isinstance(value, (list, tuple)):
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_coerce(args[0], v, path) for v in value)
        return tuple(_coerce(a, v, path) for a, v in zip(args, value, strict=True))
    if origin in (dict, Mapping) and isinstance(value, Mapping):
        _, value_type = get_args(hint)
        return {k: _coerce(value_type, v, f"{path}.{k}") for k, v in value.items()}
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value
