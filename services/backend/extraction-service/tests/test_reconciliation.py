from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.app.main import app, get_db_lord_api
from src.app.schemas import TelemetryPoint

START = datetime(2026, 11, 12, 9, tzinfo=UTC)
END = START + timedelta(hours=1)
WATCH = "a" * 64
PHONE = "b" * 64


def reading(source=WATCH, *, value=100, record_id="record-1", begin=START, finish=END, patient="p1", **extra):
    return TelemetryPoint(
        measurement="steps",
        timestamp=begin,
        tags={"device-id": patient, "source-key": source, "version": "2.0.0", "valueUnit": "1"},
        fields={
            "value": value,
            "source_record_id": record_id,
            "source_id": "writer",
            "source_platform": "apple-health",
            "period_start": begin.isoformat(),
            "period_end": finish.isoformat(),
            **extra,
        },
    )


class FakeApi:
    def __init__(self, points):
        self.points = points

    async def stream_telemetry(self, *, measurement, start, end, tags=None):
        for point in sorted(self.points, key=lambda p: p.timestamp, reverse=True):
            if (point.measurement == measurement and start <= point.timestamp < end
                    and all(point.tags.get(key) == value for key, value in (tags or {}).items())):
                yield point


@pytest.fixture
def client():
    api = FakeApi([reading(), reading(PHONE, value=90)])
    app.dependency_overrides[get_db_lord_api] = lambda: api
    with TestClient(app) as client:
        yield client, api
    app.dependency_overrides.clear()


def query(client, **params):
    return client.get(
        "/v1/measurements/reconciled",
        params={
            "patient_id": "p1",
            "measurement": "steps",
            "start": START.isoformat(),
            "end": END.isoformat(),
            **params,
        },
    )


def test_default_keeps_sources_separate_and_selection_is_explicit(client):
    client, _ = client
    response = query(client)
    assert response.status_code == 200
    assert response.json()["selection"] is None
    assert [source["value"] for source in response.json()["sources"]] == [100, 90]
    selected = query(client, mode="select", source_key=WATCH).json()
    assert selected["selection"]["value"] == 100
    assert selected["excluded_sources"] == [PHONE]


def test_priority_selects_one_whole_source_and_reports_coverage(client):
    client, api = client
    api.points[0] = reading(finish=START + timedelta(minutes=30))
    result = query(client, mode="priority", source_priority=[WATCH, PHONE]).json()
    assert result["selected_source"] == WATCH
    assert result["selection"]["reported_interval_seconds"] == 1800
    assert result["selection"]["value"] == 100


@pytest.mark.parametrize(
    "change,status",
    [
        ({"record_id": "record-2"}, "overlapping-records"),
        ({"record_id": "record-1", "value": 200}, "conflicting-source-record"),
    ],
)
def test_conflicting_or_overlapping_records_do_not_produce_a_total(client, change, status):
    client, api = client
    api.points.append(reading(**change))
    source = query(client, mode="select", source_key=WATCH).json()["selection"]
    assert source["value"] is None
    assert source["status"] == status


def test_same_native_record_from_another_collector_is_deduplicated(client):
    client, api = client
    api.points.append(reading(collector_id="replacement-phone"))
    source = query(client, mode="select", source_key=WATCH).json()["selection"]
    assert source["record_count"] == 1
    assert source["value"] == 100


def test_legacy_source_is_explicit_and_different_sources_survive_export(client):
    client, api = client
    api.points.append(reading("legacy", record_id=""))
    sources = query(client).json()["sources"]
    assert next(source for source in sources if source["source_key"] == "legacy")["status"] == "source-unknown"
    page = client.get("/v1/measurements", params={"patient_id": "p1", "measurement": "steps"}).json()
    assert len(page["items"]) == 3
    selected = client.get(
        "/v1/measurements",
        params={
            "patient_id": "p1",
            "measurement": "steps",
            "source_key": WATCH,
        },
    ).json()
    assert len(selected["items"]) == 1


def test_distinct_sources_with_equal_values_have_distinct_fhir_ids(client):
    client, api = client
    api.points = [reading(), reading(PHONE)]
    response = client.get("/v1/measurements/export.fhir", params={"patient_id": "p1", "measurement": "steps"})
    entries = response.json()["entry"]
    assert len(entries) == 2
    assert len({entry["fullUrl"] for entry in entries}) == 2
    assert entries[0]["resource"]["identifier"] != entries[1]["resource"]["identifier"]


@pytest.mark.parametrize(
    "params",
    [
        {"mode": "select"},
        {"mode": "priority"},
        {"source_key": WATCH},
        {"source_priority": [WATCH]},
        {"start": "2026-11-12T09:00:00"},
        {"end": (END + timedelta(days=32)).isoformat()},
    ],
)
def test_invalid_policy_requests_are_rejected(client, params):
    client, _ = client
    assert query(client, **params).status_code == 422


def test_unknown_source_and_incomplete_boundary_return_explicit_outcomes(client):
    client, api = client
    assert query(client, mode="select", source_key="c" * 64).status_code == 404
    api.points[0] = reading(finish=END + timedelta(minutes=1))
    result = query(client, mode="select", source_key=WATCH).json()["selection"]
    assert result["status"] == "interval-crosses-window"
    assert result["value"] is None


def test_source_policy_is_bounded_and_patient_ids_are_authoritative(client, monkeypatch):
    client, api = client
    import src.app.reconciliation as policy
    monkeypatch.setattr(policy, "MAX_RECORDS", 1)
    assert query(client).status_code == 413
    api.points = [reading()]
    api.points[0].tags["patient-id"] = "different-patient"
    assert query(client).json()["sources"] == []


def test_instantaneous_measurements_remain_samples(client):
    client, api = client
    api.points[0].measurement = "heart-rate"
    result = query(client, measurement="heart-rate", mode="select", source_key=WATCH).json()
    assert result["metric_policy"] == "samples"
    assert result["selection"]["value"] is None


def test_scanned_limit_also_applies_to_mismatched_patient_results(client, monkeypatch):
    client, api = client
    import src.app.reconciliation as policy
    monkeypatch.setattr(policy, "MAX_RECORDS", 1)
    api.points = [reading(record_id=str(index)) for index in range(5)]
    for point in api.points:
        point.tags["patient-id"] = "different-patient"
    assert query(client).status_code == 413


def test_invalid_legacy_interval_type_has_an_explicit_outcome(client):
    client, api = client
    api.points = [reading(period_start=123)]
    result = query(client, mode="select", source_key=WATCH).json()["selection"]
    assert result["status"] == "incomplete-interval-or-unit"
    assert result["value"] is None


def test_finite_inputs_cannot_overflow_a_reconciled_total(client):
    client, api = client
    middle = START + timedelta(minutes=30)
    api.points = [reading(value=1e308, finish=middle),
                  reading(value=1e308, record_id="record-2", begin=middle)]
    result = query(client, mode="select", source_key=WATCH).json()["selection"]
    assert result["status"] == "non-finite-total"
    assert result["value"] is None


def test_conflicting_instantaneous_ids_are_reported(client):
    client, api = client
    api.points = [reading(value=70), reading(value=75)]
    for point in api.points:
        point.measurement = "heart-rate"
    result = query(client, measurement="heart-rate", mode="select", source_key=WATCH).json()["selection"]
    assert result["status"] == "conflicting-source-record"
    assert result["value"] is None


def test_dashboards_keep_sources_in_distinct_series():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    for name in ["standard", "6mgt"]:
        dashboard = json.loads((root / f"observability/dashboards/{name}-dash-2026-04-11.json").read_text())
        assert any(variable["name"] == "sourceKey" for variable in dashboard["templating"]["list"])
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                query = target.get("query", "")
                if '"device-id"' in query:
                    assert '"source-key" =~ /^$sourceKey$/' in query
                    assert 'GROUP BY "source-key"' in query
