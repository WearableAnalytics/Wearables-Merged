import copy
from typing import Any

from line_protocol_parser import parse_line

from src.fhir_serde.dot_parser import Node
from src.fhir_serde.model import FhirYamlConfig, FieldDef, MappingDef


def tokenize_path(path: str) -> list[tuple[str, str | int]]:

    tokens: list[tuple[str, str | int]] = []
    i = 0
    n = len(path)
    buf: list[str] = []

    def flush_field():
        nonlocal buf
        if buf:
            tokens.append(("field", "".join(buf)))
            buf = []

    while i < n:
        c = path[i]

        if c == ".":
            flush_field()
            i += 1
            continue

        if c == "[":
            flush_field()
            i += 1  # move past '['
            if i >= n:
                raise ValueError(f"Unclosed '[' in path: {path!r}")

            # read digits
            start = i
            while i < n and path[i].isdigit():
                i += 1

            if start == i:
                raise ValueError(f"Empty or non-numeric index in brackets in path: {path!r}")

            if i >= n or path[i] != "]":
                raise ValueError(f"Unclosed or malformed index in path: {path!r}")

            idx_str = path[start:i]
            tokens.append(("index", int(idx_str)))
            i += 1  # move past ']'
            continue

        if c == "]":
            # stray closing bracket
            raise ValueError(f"Stray ']' in path: {path!r}")

        # normal field character
        buf.append(c)
        i += 1

    flush_field()
    return tokens


def _resolve_mapping(field_name: str, key: str, mappings: list[MappingDef] | None) -> str | None:
    """Look up a value in the mappings table for a given field and key."""
    if not mappings:
        return None
    for m in mappings:
        if m.fieldName == field_name:
            for entry in m.map:
                if entry.key == key:
                    return entry.value
    return None


def _apply_transforms(
    value: Any,
    field_def: FieldDef,
    fhir_dict: dict,
    mappings: list[MappingDef] | None,
) -> Any:
    """Apply the transform chain defined on a FieldDef."""
    if not field_def.transform:
        return value

    result = value
    for t in field_def.transform:
        if t.type == "toLowerCase" and isinstance(result, str):
            result = result.lower()
        elif t.type == "replace" and isinstance(result, str) and t.params and len(t.params) >= 2:
            result = result.replace(t.params[0], t.params[1])
        elif t.type == "append" and isinstance(result, str) and t.params:
            result = result + t.params[0]
        elif t.type == "prepend" and isinstance(result, str) and t.params:
            result = t.params[0] + result
        elif t.type == "map":
            mapped = _resolve_mapping(field_def.name, str(result), mappings)
            if mapped is not None:
                result = mapped
    return result


def _read_fhir_path(fhir_dict: dict, path: str) -> Any:
    """Read a value from a nested dict using a dot/bracket path."""
    tokens = tokenize_path(path)
    current: Any = fhir_dict
    for tok_type, tok_val in tokens:
        if current is None:
            return None
        if tok_type == "field":
            if isinstance(current, dict):
                current = current.get(tok_val)
            else:
                return None
        elif tok_type == "index":
            if isinstance(current, list) and tok_val < len(current):
                current = current[tok_val]
            else:
                return None
    return current


class FhirParser:
    def __init__(self, yaml_basis: FhirYamlConfig, category_name: str, nodes: list[Node] | None = None):
        copy_yaml = yaml_basis.model_copy(deep=True)

        yaml_basis.measurement.paths = [
            p for p in copy_yaml.measurement.paths
            if p.path == category_name
        ]

        if len(yaml_basis.measurement.paths) != 1:
            raise RuntimeError(f"there should be exactly one applicable category, but there are {yaml_basis.measurement.paths}")

        self._measurement_path = yaml_basis.measurement.paths[0]
        measurement_fields = self._measurement_path.fields
        metadata_fields = yaml_basis.metadata.fields
        self._mappings = self._measurement_path.mappings

        self.all_fields: list[FieldDef] = measurement_fields + metadata_fields
        self.nodes = nodes or []
        self.fhir_dict: dict = {}

    def build_fhir(self, lp_record: str) -> dict:
        lp_dict = parse_line(lp_record)

        fields: dict[str, str | int | float] = lp_dict["fields"]
        tags: dict[str, str] = lp_dict["tags"]
        measurement: str = lp_dict["measurement"]
        time: int = lp_dict["time"]

        self.fhir_dict = {}

        # 1) Set constant-value fields
        for field_def in self.all_fields:
            if field_def.value is not None:
                self.build_path(field_def.target, field_def.value)

        # 2) Set fields from raw source (line protocol fields + tags)
        all_raw = {**tags, **fields}
        for field_def in self.all_fields:
            if field_def.rawSource is not None or field_def.lineProtocol is not None:
                raw_value = self._resolve_raw_value(field_def, all_raw)
                if raw_value is not None:
                    transformed = _apply_transforms(raw_value, field_def, self.fhir_dict, self._mappings)
                    self.build_path(field_def.target, transformed)

        # 3) Set fields derived from other FHIR fields (fhirSource)
        self._resolve_derived_fields()

        return self.fhir_dict

    def build_fhir_from_telemetry(
        self,
        *,
        fields: dict[str, Any],
        tags: dict[str, str],
        measurement: str,
        timestamp: str,
    ) -> dict:
        """Build a FHIR resource from a db_lord telemetry record (already parsed JSON)."""
        self.fhir_dict = {}

        # 1) Set constant-value fields
        for field_def in self.all_fields:
            if field_def.value is not None:
                self.build_path(field_def.target, field_def.value)

        # 2) Set fields from raw data (fields + tags)
        all_raw: dict[str, Any] = {**tags, **fields}
        # Also inject measurement name and timestamp for fields that reference them
        all_raw["__measurement__"] = measurement
        all_raw["__timestamp__"] = timestamp

        for field_def in self.all_fields:
            if field_def.value is not None:
                continue  # already handled
            if field_def.fhirSource is not None:
                continue  # handled in pass 3

            raw_value = self._resolve_raw_value(field_def, all_raw)
            if raw_value is not None:
                transformed = _apply_transforms(raw_value, field_def, self.fhir_dict, self._mappings)
                self.build_path(field_def.target, transformed)

        # 3) Set fields derived from other FHIR fields (fhirSource)
        self._resolve_derived_fields()

        return self.fhir_dict

    def _resolve_derived_fields(self) -> None:
        """Set fhirSource fields. A field can derive from another derived field that comes later
        in the mapping (e.g. valueUnit from code.coding[0].code), so repeat until nothing changes."""
        pending = [f for f in self.all_fields if f.fhirSource is not None]
        while pending:
            remaining = []
            for field_def in pending:
                source_val = _read_fhir_path(self.fhir_dict, field_def.fhirSource)
                if source_val is None:
                    remaining.append(field_def)
                    continue
                transformed = _apply_transforms(source_val, field_def, self.fhir_dict, self._mappings)
                self.build_path(field_def.target, transformed)
            if len(remaining) == len(pending):
                return
            pending = remaining

    @staticmethod
    def _resolve_raw_value(field_def: FieldDef, all_raw: dict[str, Any]) -> Any:
        """Resolve the raw value for a field from the input data."""
        # Line protocol type hints which source key to use
        if field_def.lineProtocol:
            lp = field_def.lineProtocol
            if lp.type == "measurement":
                return all_raw.get("__measurement__")
            if lp.type == "timestamp":
                return all_raw.get("__timestamp__")
            if lp.name and lp.name in all_raw:
                return all_raw[lp.name]

        # Fall back to matching by field name
        if field_def.name in all_raw:
            return all_raw[field_def.name]

        return None

    def find_node_by_field_name(self, field_name: str) -> Node | None:

        for node in self.nodes:
            if node.name == field_name:
                return node

        return None

    def deduct_partial_fhir(self, node: Node | None, field_value: str | int | float):

        if node is None:
            return

        target_path = self.find_path_by_field_name(node.name)
        if target_path is None:
            raise RuntimeError("no target_path set for field")

        self.build_path(target_path, field_value)


    def find_path_by_field_name(self, field_name: str) -> str | None:

        for f in self.all_fields:
            if f.name == field_name:

                return f.target

        return None


    def build_path(self, path: str, field_value: str | int | float):

        tokens = tokenize_path(path)
        if not tokens:
            raise ValueError(f"No tokens were generated for path {path!r}")

        current: Any = self.fhir_dict
        parent: Any = None
        parent_key: Any = None

        for i, (tok_type, tok_val) in enumerate(tokens):
            last = (i == len(tokens) - 1)
            next_type = tokens[i + 1][0] if not last else None

            if tok_type == "field":
                field_name = tok_val

                if not isinstance(current, dict):
                    new_obj: dict = {}
                    if parent is None:
                        raise TypeError(f"Root must be a dict to set field {field_name!r} in path {path!r}")
                    if isinstance(parent, dict):
                        parent[parent_key] = new_obj
                    else:
                        parent[parent_key] = new_obj
                    current = new_obj

                if last:
                    current[field_name] = copy.deepcopy(field_value)
                else:
                    if field_name not in current or current[field_name] is None:
                        current[field_name] = [] if next_type == "index" else {}
                    parent, parent_key = current, field_name
                    current = current[field_name]

            elif tok_type == "index":
                index = tok_val

                if not isinstance(current, list):
                    new_arr: list = []
                    if parent is None:
                        raise TypeError(f"Root must be a list to set index {index} in path {path!r}")
                    if isinstance(parent, dict):
                        parent[parent_key] = new_arr
                    else:  # parent is a list
                        parent[parent_key] = new_arr
                    current = new_arr


                while len(current) <= index:
                    current.append(None)

                if last:
                    current[index] = copy.deepcopy(field_value)
                else:
                    if current[index] is None:
                        current[index] = [] if next_type == "index" else {}
                    parent, parent_key = current, index
                    current = current[index]

            else:
                raise ValueError(f"Unknown token type: {tok_type!r}")
