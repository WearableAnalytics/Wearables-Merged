import copy
import json

from .api_client import ApiClient
from .dot_parser import Graph
from .transformations import to_lower_case, substring, append, prepend, replace
from datetime import datetime, timezone
from typing import Any

import line_protocol_parser

from src.fhir_serde.dot_parser import Node
from src.fhir_serde.yaml_parser import FieldDef, MappingDef

import logging

logger = logging.getLogger(__name__)


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
            i += 1
            if i >= n:
                raise ValueError(f"Unclosed '[' in path: {path!r}")


            start = i
            while i < n and path[i].isdigit():
                i += 1

            if start == i:
                raise ValueError(f"Empty or non-numeric index in brackets in path: {path!r}")

            if i >= n or path[i] != "]":
                raise ValueError(f"Unclosed or malformed index in path: {path!r}")

            idx_str = path[start:i]
            tokens.append(("index", int(idx_str)))
            i += 1
            continue

        if c == "]":

            raise ValueError(f"Stray ']' in path: {path!r}")

        buf.append(c)
        i += 1

    flush_field()
    return tokens


def build_path(fhir_dict: dict[str, Any], path: str, field_value: str | int | float):
    tokens = tokenize_path(path)
    if not tokens:
        raise ValueError(f"No tokens were generated for path {path!r}")

    current: Any = fhir_dict
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


class FhirParser:
    def __init__(self, client: ApiClient, version: str, category_name: str):

        self.client = client

        self.category: str = category_name
        self.version: str = version

        self.all_fields: dict[str, FieldDef] = {}
        self.all_maps: dict[str, MappingDef] = {}
        self.nodes: dict[str, Node] = {}

        self.ready = False

    def prepare_yaml_and_graph(self):

        parsed_yaml = self.client.read_yaml_for_version_and_category(self.version, self.category)
        parsed_graph = self.client.read_graph_for_version_and_category(self.version, self.category)

        self.prepare_config(parsed_yaml, parsed_graph)

        self.ready = True

    def prepare_config(self, relevant_yaml: tuple[dict[str, FieldDef], dict[str, MappingDef]], graph: Graph):

        self.all_fields = relevant_yaml[0]
        self.all_maps = relevant_yaml[1]

        self.nodes = graph.nodes

    def build_fhir(self, lp_record: str) -> str:
        if not self.ready:
            raise RuntimeError("setup for FhirParser was not completed")

        #Uses an external lib
        lp_dict = line_protocol_parser.parse_line(lp_record)

        fields: dict[str, str | int | float] = lp_dict["fields"]
        tags: dict[str, str] = lp_dict["tags"]
        measurement: str = lp_dict["measurement"]
        time: int = lp_dict["time"]

        fhir_dict: dict[str, Any] = {}

        self.deduct_field_type(fields, fhir_dict)
        self.deduct_field_type(tags, fhir_dict)

        for field_name, field in self.all_fields.items():
            if field.lineProtocol.type == "timestamp":
                node = self.nodes[field_name]
                if node is None:
                    raise RuntimeError(f"no node found for timestamp field name {field_name}")

                dt = datetime.fromtimestamp(time / 1_000_000_000, tz=timezone.utc)
                transformed_value = dt.isoformat(timespec="microseconds").replace("+00:00", "Z")

                self.deduct_partial_fhir(fhir_dict, node, transformed_value)

            if field.lineProtocol.type == "measurement":
                node = self.nodes.get(field_name)
                if node is None:
                    raise RuntimeError(f"no node found for measurement field name {field_name}")
                self.deduct_partial_fhir(fhir_dict, node, measurement)

        return json.dumps(fhir_dict)

    def deduct_field_type(self, entries: dict[str, str | int | float], fhir_dict: dict[str, Any]):
        for name, value in entries.items():
            found = False
            for f_name, field in self.all_fields.items():
                if field.lineProtocol.name == name:
                    found = True
                    node = self.nodes.get(f_name)
                    if node is None:
                        raise RuntimeError(f"no node found for field/tag name {f_name}")
                    self.deduct_partial_fhir(fhir_dict, node, value)

            if not found:
                raise RuntimeError(f"no field with matching line protocol name found for tag name {name}")

    def deduct_partial_fhir(self, fhir_dict: dict[str, Any], node: Node, field_value: str | int | float):

        # start with the input node
        field = self.all_fields.get(node.name)
        if field is None:
            raise RuntimeError(f"no field found for name {node.name}")
        if field.target is None:
            raise RuntimeError(f"no target set for field {field.name}")

        build_path(fhir_dict, field.target, field_value)

        for succ in node.successor:
            self.recursively_deduct_fhir(fhir_dict, node, field_value)

    def recursively_deduct_fhir(self, fhir_dict: dict[str, Any], node: Node, field_value: str | int | float):

        for succ in node.successor:
            s_field = self.all_fields.get(succ.name)
            if s_field.transform is not None:
                transformed_value = self.apply_transformations(s_field, field_value)
            else:
                transformed_value = field_value
            build_path(fhir_dict, s_field.target, transformed_value)
            self.recursively_deduct_fhir(fhir_dict, succ, transformed_value)

    def apply_transformations(self, field: FieldDef, initial_value: str | int | float) -> str | float | int:

        value = initial_value

        for t in field.transform:
            match t.type:
                case "toLowerCase":
                    value = to_lower_case(value)
                case "replace":
                    value = replace(value, t.params)
                case "append":
                    value = append(value, t.params)
                case "prepend":
                    value = prepend(value, t.params)
                case "map":
                    req_map = self.all_maps.get(field.name)
                    if req_map is None:
                        raise RuntimeError(f"no map found for field {field.name} even map transformation was set")
                    found = False
                    for m in req_map.map:
                        if m.key == value:
                            found = True
                            value = m.value
                    if not found:
                        raise RuntimeError(f"no matching key found for field {field.name} in map for current value {value}")

                case "substring":
                    value = substring(value, t.params)
                case _:
                    raise RuntimeError(f"transformation {t} is not implemented")

        return value
