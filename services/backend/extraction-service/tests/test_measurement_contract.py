from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from src.app.fhir import ObservationBuilder, builtin_mapping
from src.app.schemas import TelemetryPoint


def point(**kwargs):
    return TelemetryPoint(
        measurement="sleep-light",
        timestamp=datetime(2026, 11, 12, 9, tzinfo=UTC),
        tags={"device-id": "p1", "version": "2.0.0", "category": "measurements.duration", **kwargs.pop("tags", {})},
        fields={
            "value": 1.5041666666666667,
            "period_start": "2026-11-12T09:00:00Z",
            "period_end": "2026-11-12T09:01:30.250000Z",
            **kwargs.pop("fields", {}),
        },
        **kwargs,
    )


class MissingMapping:
    async def get_fhir_mapping(self, mapping_id):
        raise ConnectionError("mapping service unavailable")


@pytest.mark.asyncio
async def test_roundtrip_preserves_period_precision_and_light_sleep():
    observation = await ObservationBuilder(MissingMapping()).build(point())
    assert observation["valueQuantity"]["value"] == pytest.approx(90.25 / 60)
    assert observation["code"]["coding"][0]["code"] == "93830-8"
    assert observation["effectivePeriod"]["end"] == "2026-11-12T09:01:30.250000Z"
    assert "effectiveDateTime" not in observation


@pytest.mark.asyncio
async def test_stored_code_and_unit_override_newer_mapping():
    observation = await ObservationBuilder(MissingMapping()).build(
        point(
            tags={
                "valueUnit": "s",
                "valueCode": "s",
                "valueSystem": "http://unitsofmeasure.org",
                "codeCodingCodeZero": "stored-code",
                "codeCodingSystemZero": "urn:test:codes",
            }
        )
    )
    assert observation["valueQuantity"]["code"] == "s"
    assert observation["code"]["coding"][0]["code"] == "stored-code"


@pytest.mark.asyncio
async def test_mapping_outage_cannot_reinterpret_versioned_record():
    with pytest.raises(ConnectionError):
        await ObservationBuilder(MissingMapping()).build(point(tags={"mapping_id": "saved-mapping"}))


def test_legacy_points_keep_legacy_mapping():
    old = point(tags={"version": "1.0.0"})
    assert builtin_mapping(old).version == "1.0.0"
    assert builtin_mapping(point()).version.startswith("2.")


def test_all_mapping_copies_match():
    root = Path(__file__).resolve().parents[4]
    canonical = yaml.safe_load(
        (root / "services/backend/fhir-mapper-validator/config/mapping-2026-01-28.yaml").read_text()
    )
    for path in [
        "services/backend/fhir-mapper-validator/src/main/resources/mapping-2026-01-28.yaml",
        "services/backend/extraction-service/src/app/default_fhir_mapping.yaml",
    ]:
        assert yaml.safe_load((root / path).read_text()) == canonical
    helm = (root / "gitops/apps/services/mapper-validator/templates/mappings-config-map.yaml").read_text()
    assert (
        yaml.safe_load("\n".join(line[4:] for line in helm.split("  mapping.yaml: |\n", 1)[1].splitlines()))
        == canonical
    )
