from typing import Protocol

from src.fhir_serde.dot_parser import Graph
from src.fhir_serde.yaml_parser import FieldDef, MappingDef


class ApiClient(Protocol):
    def read_yaml_for_version_and_category(self, version: str, category: str) -> tuple[dict[str, FieldDef], dict[str, MappingDef]]:
        ...

    def read_graph_for_version_and_category(self, version: str, category: str) -> Graph:
        ...