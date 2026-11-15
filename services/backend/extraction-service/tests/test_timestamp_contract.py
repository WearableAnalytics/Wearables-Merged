from pathlib import Path

import pytest
import yaml

from src.fhir_serde.fhir_builder import FhirParser
from src.fhir_serde.model import FhirYamlConfig


@pytest.mark.parametrize(
    "category,measurement",
    [
        ("instantaneous", "heart-rate"),
        ("cumulative", "steps"),
        ("duration", "sleep-deep"),
    ],
)
@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2026-11-03T10:00:00.123456+01:00", "2026-11-03T09:00:00.123456Z"),
        ("2026-07-03T10:00:00+02:00", "2026-07-03T08:00:00Z"),
        ("2026-10-25T02:30:00+02:00", "2026-10-25T00:30:00Z"),
        ("2026-10-25T02:30:00+01:00", "2026-10-25T01:30:00Z"),
        ("2026-03-29T01:59:59+01:00", "2026-03-29T00:59:59Z"),
        ("2026-03-29T03:00:00+02:00", "2026-03-29T01:00:00Z"),
        ("2026-11-03T09:00:00Z", "2026-11-03T09:00:00Z"),
        # Compatibility only: historical naive timestamps cannot recover their timezone.
        ("2026-11-03T09:00:00", "2026-11-03T09:00:00Z"),
    ],
)
def test_export_mapping_preserves_instant(category, measurement, timestamp, expected):
    mapping = Path(__file__).parents[1] / "src/app/default_fhir_mapping.yaml"
    config = FhirYamlConfig.model_validate(yaml.safe_load(mapping.read_text()))
    parser = FhirParser(config, f"measurements.{category}")
    observation = parser.build_fhir_from_telemetry(
        fields={"value": 61},
        tags={},
        measurement=measurement,
        timestamp=timestamp,
    )
    actual = (
        observation["effectiveDateTime"] if category == "instantaneous" else observation["effectivePeriod"]["start"]
    )
    assert actual == expected


@pytest.mark.parametrize("timestamp", ["2026-11-03T09:00:00Z", "2026-11-03T10:00:00+01:00"])
def test_database_supplied_legacy_mapping_does_not_append_second_offset(timestamp):
    mapping = Path(__file__).parents[1] / "src/app/default_fhir_mapping.yaml"
    config = FhirYamlConfig.model_validate(yaml.safe_load(mapping.read_text()))
    for field in config.measurement.paths[0].fields:
        for transform in field.transform or []:
            if transform.type == "normalizeTimestamp":
                transform.type = "append"
                transform.params = ["Z"]
    parser = FhirParser(config, "measurements.instantaneous")
    observation = parser.build_fhir_from_telemetry(
        fields={"value": 61},
        tags={},
        measurement="heart-rate",
        timestamp=timestamp,
    )
    assert observation["effectiveDateTime"] == "2026-11-03T09:00:00Z"
