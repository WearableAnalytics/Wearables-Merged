import json
from typing import Any

import pytest

from src.app.db_lord_api import DbLordApi
from src.fhir_serde.fhir_builder import FhirParser, tokenize_path, build_path
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

class FakeDBApi:
    def read_yaml_for_version(self, version: str) -> str:



    return

CATEGORY_NAME = "measurements.cumulative"
VERSION = "1.0.0"

@pytest.fixture
def builder():

    s  = Settings(
        yaml_path="/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example.yaml",
        graphs_path="/Users/linusgustafsson/Uni/DSP/current/Wearables-Merged/services/backend/extraction-service/tests/data/example_dot.txt"
    )

    client = DbLordApi()

    b = FhirParser(fhir_yaml, CATEGORY_NAME, VERSION, nodes)

    return b

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
        graphs_string = stream.read()

    for line in graphs_string.splitlines():
        builder.build_fhir(line)