from typing import Any

import pytest

from src.fhir_serde.fhir_builder import tokenize_path, build_path
from src.fhir_serde.env_client import Settings, get_category_name, EnvClient
from src.fhir_serde.dot_parser import parse_graph, Graph
from src.fhir_serde.version_category_manager import VersionManager
from src.fhir_serde.yaml_parser import FieldDef, MappingDef, parse_yaml


def test_tokenize_simple_fields():
    assert tokenize_path("a.b.c") == [
        ("field", "a"),
        ("field", "b"),
        ("field", "c"),
    ]

def test_tokenize_with_indexes():
    assert tokenize_path("a.b[0].c[2]") == [
        ("field", "a"),
        ("field", "b"),
        ("index", 0),
        ("field", "c"),
        ("index", 2),
    ]

YAML_PATH = "/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example.yaml"
GRAPHS_PATH = "/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example_dot.txt"

CATEGORY_NAME = "measurements.cumulative"
VERSION = "1.0.0"

class FakeClient:

    def read_yaml_for_version_and_category(self, _: str, category: str) -> tuple[dict[str, FieldDef], dict[str, MappingDef]]:

        with open(YAML_PATH, "r") as stream:
            yaml_string = stream.read()

        return  parse_yaml(yaml_string, category)

    def read_graph_for_version_and_category(self, _: str, category: str) -> Graph:

        with open(GRAPHS_PATH, "r") as stream:
            graphs_string = stream.read()

        graph_list = graphs_string.split("&")

        for g in graph_list:
            if len(g) == 0:
                continue
            name = get_category_name(g)

            if name == category:
                return parse_graph(g, category)

        raise RuntimeError(f"no category matching '{category}' was found")


@pytest.fixture
def builder():

    s = Settings(
        yaml_path="/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example.yaml",
        graphs_path="/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example_dot.txt"
    )

    client = FakeClient()
    env_client = EnvClient(s)

    vm = VersionManager(client, env_client)

    vm.initialize()

    return vm

def test_build_path_complex():
    fhir_dict: dict[str, Any] = {}

    build_path(fhir_dict, "a.b[0].c", 123)

    assert fhir_dict == {"a": {"b": [{"c": 123}]}}

def test_build_path_full():

    fhir_dict: dict[str, Any] = {}

    build_path(fhir_dict, "a.b[0].c", 123)
    build_path(fhir_dict, "a.b[0].d", "xgsd")
    build_path(fhir_dict, "a.b[0].e.f", True)
    build_path(fhir_dict, "a.b[0].e.g[0]", "gfasdg0")
    build_path(fhir_dict, "a.b[0].e.g[1]", "ggdsga1")
    build_path(fhir_dict, "a.b[1].c", 456)
    build_path(fhir_dict, "a.b[1].h", None)
    build_path(fhir_dict, "a.b[1].e.g[0]", "gdfga")

    assert fhir_dict == {
        "a": {
            "b": [
                {
                    "c": 123,
                    "d": "xgsd",
                    "e": {"f": True, "g": ["gfasdg0", "ggdsga1"]},
                },
                {
                    "c": 456,
                    "h": None,
                    "e": {"g": ["gdfga"]},
                },
            ]
        }
    }

def test_deduct_full_fhir(builder):

    with open("/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/lp.txt", "r") as stream:
        lp = stream.read()

    with open("output.txt", "a", encoding="utf-8") as f:
        for line in lp.splitlines():
            built_fhir = builder.transform_to_fhir(line)
            print("parsed")
            if built_fhir is not None:
                f.write(built_fhir + "\n")



