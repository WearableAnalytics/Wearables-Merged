import json

import pytest

from src.fhir_serde.fhir_builder import FhirParser, tokenize_path
from src.environment.settings import get_env_values, Settings
from src.fhir_serde.dot_parser import parse_file



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

CATEGORY_NAME = "measurements.cumulative"
@pytest.fixture
def builder():

    s  = Settings(
        yaml_path="/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example.yaml",
        graphs_path="/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example_dot.txt"
    )
    envs = get_env_values(s)

    return envs

def test_build_path_complex(builder):
    fhir_yaml, dot_graphs = builder
    graph_dict = parse_file(dot_graphs)

    nodes = graph_dict[CATEGORY_NAME].nodes

    b = FhirParser(fhir_yaml, CATEGORY_NAME, nodes)

    b.build_path("a.b[0].c", 123)

    assert b.fhir_dict == {"a": {"b": [{"c": 123}]}}

def test_build_path_full(builder):
    fhir_yaml, dot_graphs = builder
    graph_dict = parse_file(dot_graphs)

    nodes = graph_dict[CATEGORY_NAME].nodes

    b = FhirParser(fhir_yaml, CATEGORY_NAME, nodes)

    b.build_path("a.b[0].c", 123)
    b.build_path("a.b[0].d", "xgsd")
    b.build_path("a.b[0].e.f", True)
    b.build_path("a.b[0].e.g[0]", "gfasdg0")
    b.build_path("a.b[0].e.g[1]", "ggdsga1")
    b.build_path("a.b[1].c", 456)
    b.build_path("a.b[1].h", None)
    b.build_path("a.b[1].e.g[0]", "gdfga")

    assert b.fhir_dict == {
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