import json
from pathlib import Path

import pytest
import yaml

from src.fhir_serde.fhir_builder import FhirParser, tokenize_path
from src.fhir_serde.dot_parser import parse_file
from src.fhir_serde.model import FhirYamlConfig


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
DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def fhir_yaml():
    yaml_path = DATA_DIR / "example.yaml"
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    return FhirYamlConfig.model_validate(raw)


@pytest.fixture
def dot_graphs():
    dot_path = DATA_DIR / "example_dot.txt"
    if not dot_path.exists():
        return None
    return dot_path.read_text()


def test_build_path_complex(fhir_yaml):
    b = FhirParser(fhir_yaml, CATEGORY_NAME)

    b.build_path("a.b[0].c", 123)

    assert b.fhir_dict == {"a": {"b": [{"c": 123}]}}

def test_build_path_full(fhir_yaml):
    b = FhirParser(fhir_yaml, CATEGORY_NAME)

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


def test_build_fhir_from_telemetry(fhir_yaml):
    """Test building a FHIR resource from a telemetry record."""
    parser = FhirParser(fhir_yaml, "measurements.instantaneous")

    result = parser.build_fhir_from_telemetry(
        fields={"value": 72.0, "status": "final"},
        tags={"device-id": "dev-123"},
        measurement="heart-rate",
        timestamp="2024-01-01T00:00:00",
    )

    assert result["resourceType"] == "Observation"
    assert result["status"] == "final"
    assert result["valueQuantity"]["value"] == 72.0
