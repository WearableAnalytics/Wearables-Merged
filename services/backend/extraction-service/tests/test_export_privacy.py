import csv
import io
import json

import pytest
import test_export_api as export_tests
from test_export_api import OTHER, PATIENT, point

from src.app.privacy import ExportPrivacy

# Reuse the existing in-memory backend fixtures.
client = export_tests.client
db_lord = export_tests.db_lord


@pytest.mark.parametrize("format", ["csv", "fhir"])
def test_export_pseudonyms_are_scoped_and_metadata_is_removed(client, db_lord, format):
    contaminated = point(40, value=11)
    contaminated.fields["notes"] = {"name": "PRIVATE-NAME", "id": PATIENT}
    contaminated.tags["device-serial"] = "PRIVATE-SERIAL"
    contaminated.tags["mapping_id"] = "PRIVATE-MAPPING"
    db_lord.points.append(contaminated)
    original = contaminated.model_dump()
    url = f"/v1/measurements/export.{format}"
    response = client.get(url, params={"pseudonymize": "true"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "pseudonymized" in response.headers["content-disposition"]
    for secret in [PATIENT, OTHER, "PRIVATE-NAME", "PRIVATE-SERIAL", "PRIVATE-MAPPING", "telegraf-"]:
        assert secret not in response.text

    def extract(body):
        if format == "csv":
            rows = list(csv.DictReader(io.StringIO(body)))
            assert all(row["fields"] == "" for row in rows)
            return [(row["patient_id"], float(row["value"])) for row in rows]
        bundle = json.loads(body)
        observations = [entry["resource"] for entry in bundle["entry"]]
        assert len({entry["fullUrl"] for entry in bundle["entry"]}) == len(observations)
        assert all("device" not in observation for observation in observations)
        return [(o["subject"]["reference"], o["valueQuantity"]["value"]) for o in observations]

    readings = extract(response.text)
    assert sorted(value for _, value in readings) == [3, 5, 7, 9, 11, 72, 100]
    assert len({identity for identity, value in readings if value != 100}) == 1
    assert len({identity for identity, _ in readings}) == 2
    second = extract(client.get(url, params={"pseudonymize": "true"}).text)
    assert {identity for identity, _ in readings}.isdisjoint(identity for identity, _ in second)
    assert contaminated.model_dump() == original


@pytest.mark.parametrize("format", ["csv", "fhir"])
def test_pseudonymized_export_omits_free_text_and_unknown_measurements(client, db_lord, format):
    db_lord.points = [point(0, value="PRIVATE-NAME"), point(1, measurement="PRIVATE-NAME")]
    response = client.get(f"/v1/measurements/export.{format}", params={"pseudonymize": "true"})
    assert response.status_code == 200
    assert "PRIVATE-NAME" not in response.text
    if format == "csv":
        assert list(csv.DictReader(io.StringIO(response.text))) == []
    else:
        assert response.json()["entry"] == []


def test_missing_patient_is_not_assigned_a_shared_identity():
    source = point(0, device_id=None, reference=False)
    projected = ExportPrivacy().project(source)
    assert projected is not None
    assert projected.patient_id is None


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), {"name": "PRIVATE"}])
def test_non_numeric_or_non_finite_values_are_excluded(value):
    assert ExportPrivacy().project(point(0, value=value)) is None


@pytest.mark.parametrize("measurement", ["bpm", "ms", "8867-4", "55425-3"])
def test_mapping_units_and_codes_are_not_measurement_names(measurement):
    assert ExportPrivacy().project(point(0, measurement=measurement)) is None


@pytest.mark.parametrize("format", ["csv", "fhir"])
def test_filter_uses_original_identity_and_opt_out_is_unchanged(client, format):
    url = f"/v1/measurements/export.{format}"
    params = {"patient_id": PATIENT}
    ordinary = client.get(url, params=params)
    disabled = client.get(url, params={**params, "pseudonymize": "false"})
    assert ordinary.text == disabled.text
    assert PATIENT in ordinary.text
    private = client.get(url, params={**params, "pseudonymize": "true"})
    assert private.status_code == 200
    assert PATIENT not in private.text
    if format == "csv":
        assert len(list(csv.DictReader(io.StringIO(private.text)))) == 5
    else:
        assert len(private.json()["entry"]) == 5


@pytest.mark.parametrize("format", ["csv", "fhir"])
def test_omission_counts_match_download_and_do_not_count_duplicates(client, db_lord, format):
    db_lord.points.extend(
        [
            point(41, measurement="unknown", value="also invalid"),
            point(42, value="text"),
            point(43, value=float("inf")),
        ]
    )
    response = client.get(f"/v1/measurements/export.{format}?pseudonymize=true")
    assert response.status_code == 200
    assert response.headers["x-export-considered"] == "9"
    assert response.headers["x-export-exported"] == "6"
    assert response.headers["x-export-omitted"] == "3"
    assert response.headers["x-export-omitted-unsupported"] == "1"
    assert response.headers["x-export-omitted-invalid-value"] == "2"
    assert "-3-omitted." in response.headers["content-disposition"]
    assert int(response.headers["content-length"]) == len(response.content)
    count = len(list(csv.DictReader(io.StringIO(response.text)))) if format == "csv" else len(response.json()["entry"])
    assert count == 6


@pytest.mark.parametrize("format", ["csv", "fhir"])
@pytest.mark.parametrize("points", [[], [point(0, measurement="unknown")]])
def test_empty_and_completely_omitted_exports_report_zero(client, db_lord, format, points):
    db_lord.points = points
    response = client.get(f"/v1/measurements/export.{format}?pseudonymize=true")
    assert response.status_code == 200
    assert response.headers["x-export-exported"] == "0"
    assert int(response.headers["x-export-considered"]) == len(points)
    assert int(response.headers["x-export-omitted"]) == len(points)
    if format == "csv":
        assert list(csv.DictReader(io.StringIO(response.text))) == []
    else:
        assert response.json()["entry"] == []


@pytest.mark.parametrize("format", ["csv", "fhir"])
def test_complete_export_reports_no_omissions(client, format):
    response = client.get(f"/v1/measurements/export.{format}?pseudonymize=true")
    assert response.headers["x-export-omitted"] == "0"
    assert response.headers["x-export-exported"] == response.headers["x-export-considered"] == "6"
    assert "-omitted" not in response.headers["content-disposition"]
