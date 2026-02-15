import copy
from typing import Any

from line_protocol_parser import parse_line

from src.fhir_serde.dot_parser import Node
from src.fhir_serde.model import FhirYamlConfig, FieldDef


class LPRecord:
    def __init__(self):
        fields: list[tuple[str, str]]
        tags: list[tuple[str, str]]
        measurement: str
        time: int


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


class FhirParser:
    def __init__(self, yaml_basis: FhirYamlConfig, category_name: str, nodes: list[Node]):
        copy_yaml = yaml_basis.model_copy(deep=True)

        yaml_basis.measurement.paths = [
            p for p in copy_yaml.measurement.paths
            if p.path == category_name
        ]

        if len(yaml_basis.measurement.paths) != 1:
            raise RuntimeError(f"there should be exactly one applicable category, but there are {yaml_basis.measurement.paths}")

        measurement_fields = yaml_basis.measurement.paths[0].fields
        metadata_fields = yaml_basis.metadata.fields

        self.all_fields: list[FieldDef] = measurement_fields + metadata_fields
        self.nodes = nodes
        self.fhir_dict: dict = {}

    #TODO implement retreiving different version from the database but this shouldnt happen here
    def build_fhir(self, lp_record: str) -> str:
        lp_dict = parse_line(lp_record)

        fields: dict[str, str | int | float] = lp_dict["fields"]
        tags: dict[str, str] = lp_dict["tags"]
        measurement: str = lp_dict["measurement"]
        time: int = lp_dict["time"]

        for field_name, field_value in fields.items():
            node = self.find_node_by_field_name(field_name)
            self.deduct_partial_fhir(node, field_value)


    def find_node_by_field_name(self, field_name: str) -> Node | None:

        for node in self.nodes:
            if node.name == field_name:
                return node

        return None

    def deduct_partial_fhir(self, node: Node, field_value: str | int | float):

        #start with the input node
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
                        raise TypeError(f"Root must be a dict to set field {field_name!r} in path {target_path!r}")
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

