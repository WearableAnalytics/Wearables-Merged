import json
from datetime import UTC, datetime
from uuid import uuid7

import pytest
from httpx import AsyncClient

from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.common import empty_async_iterator
from tests.helpers.common import extract_tag_param_values as _extract_tag_param_values

pytestmark = pytest.mark.anyio


def _uuid_str() -> str:
    return str(uuid7())


class TestTelemetryRawEndpoint:
    async def test_read_telemetry_raw_supports_bucket_without_measurement(
        self, client: AsyncClient, mock_influx_client
    ):
        captured_params: dict[str, object] = {}
        timestamp = datetime.now(UTC).replace(microsecond=0)

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": timestamp,
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 72,
                    "patient_id": "p1",
                }
            )

        async def query_stream(*args, **kwargs):
            params = kwargs.get("params", {})
            captured_params.update(params)
            start_param = params.get("start_param")
            stop_param = params.get("stop_param")
            if (
                isinstance(start_param, datetime)
                and isinstance(stop_param, datetime)
                and start_param <= timestamp < stop_param
            ):
                return gen()
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw",
            params={
                "bucket": "research_data",
                "patient_id": "p1",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["measurement"] == "sensor_readings"
        assert captured_params["bucket_param"] == "research_data"
        assert "measurement_param" not in captured_params

    async def test_read_telemetry_raw_empty(self, client: AsyncClient):
        response = await client.get("/telemetry/raw", params={"measurement": "sensor_readings"})
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["items"] == []
        assert data["has_more"] is False
        assert data["next_end"] is None

    async def test_read_telemetry_rejects_naive_start(self, client: AsyncClient):
        response = await client.get(
            "/telemetry/",
            params={"measurement": "sensor_readings", "start": "2026-01-01T00:00:00"},
        )
        payload = _assert_api_error(response, status_code=422)
        assert len(payload["detail"]) == 1
        error = payload["detail"][0]
        assert error["type"] == "timezone_aware"
        assert error["loc"] == ["query", "start"]
        assert error["input"] == "2026-01-01T00:00:00"
        assert "timezone" in error["msg"].lower()

    async def test_read_telemetry_raw_rejects_naive_start(self, client: AsyncClient):
        response = await client.get(
            "/telemetry/raw",
            params={"measurement": "sensor_readings", "start": "2026-01-01T00:00:00"},
        )
        payload = _assert_api_error(response, status_code=422)
        assert len(payload["detail"]) == 1
        error = payload["detail"][0]
        assert error["type"] == "timezone_aware"
        assert error["loc"] == ["query", "start"]
        assert error["input"] == "2026-01-01T00:00:00"
        assert "timezone" in error["msg"].lower()

    async def test_read_telemetry_raw_non_empty(self, client: AsyncClient, mock_influx_client):
        timestamp = datetime.now(UTC).replace(microsecond=0)

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": timestamp,
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 72,
                    "patient_id": "p1",
                }
            )

        async def query_stream(*args, **kwargs):
            params = kwargs.get("params", {})
            start_param = params.get("start_param")
            stop_param = params.get("stop_param")
            if (
                isinstance(start_param, datetime)
                and isinstance(stop_param, datetime)
                and start_param <= timestamp < stop_param
            ):
                return gen()
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw",
            params={"measurement": "sensor_readings", "patient_id": "p1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["field"] == "heart_rate"

    async def test_read_telemetry_raw_accepts_arbitrary_tag(self, client: AsyncClient, mock_influx_client):
        captured_params = {}

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 72,
                    "patient_id": "p1",
                    "sensor_type": "heart_rate",
                }
            )

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw",
            params={
                "measurement": "sensor_readings",
                "patient_id": "p1",
                "sensor_type": "heart_rate",
            },
        )
        assert response.status_code == 200
        assert any(value == "heart_rate" for key, value in captured_params.items() if key.startswith("tag_val_"))
        assert any(value == "p1" for key, value in captured_params.items() if key.startswith("tag_val_"))

    async def test_read_telemetry_raw_accepts_repeated_arbitrary_tag(self, client: AsyncClient, mock_influx_client):
        captured_params = {}

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw",
            params=[
                ("measurement", "sensor_readings"),
                ("sensor_type", "heart_rate"),
                ("sensor_type", "spo2"),
            ],
        )
        assert response.status_code == 200
        tag_values = _extract_tag_param_values(captured_params)
        assert {"heart_rate", "spo2"}.issubset(set(tag_values))

    async def test_read_telemetry_raw_accepts_unknown_get_query_params(self, client: AsyncClient, mock_influx_client):
        captured_params = {}

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw",
            params=[
                ("measurement", "sensor_readings"),
                ("sensor_type", "heart_rate"),
                ("sensor_type", "spo2"),
                ("site", "icu"),
            ],
        )
        assert response.status_code == 200
        tag_values = _extract_tag_param_values(captured_params)
        assert {"heart_rate", "spo2", "icu"}.issubset(set(tag_values))

    async def test_read_telemetry_raw_rejects_tag_query_param(self, client: AsyncClient):
        response = await client.get(
            "/telemetry/raw",
            params={"measurement": "sensor_readings", "tag": "sensor_type=heart_rate"},
        )
        _assert_api_error(
            response,
            status_code=422,
        )
        assert "Unsupported telemetry tag format" in response.json()["detail"]

    async def test_read_telemetry_raw_rejects_colon_tag_list_query_param(self, client: AsyncClient):
        response = await client.get(
            "/telemetry/raw",
            params={"measurement": "sensor_readings", "tag": "sensor_type:heart_rate"},
        )
        _assert_api_error(
            response,
            status_code=422,
        )
        assert "Unsupported telemetry tag format" in response.json()["detail"]

    async def test_read_telemetry_raw_accepts_all_core_fixed_tags(self, client: AsyncClient, mock_influx_client):
        captured_params = {}
        dot_dependency_file_id = _uuid_str()

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw",
            params={
                "measurement": "sensor_readings",
                "patient_id": "p1",
                "device_id": "d1",
                "wearable_id": "w1",
                "case_id": "c1",
                "context_id": "ctx1",
                "mapping_id": "m1",
                "dot_dependency_file_id": dot_dependency_file_id,
            },
        )
        assert response.status_code == 200
        tag_values = [value for key, value in captured_params.items() if key.startswith("tag_val_")]
        assert set(tag_values) >= {"p1", "d1", "w1", "c1", "ctx1", "m1", dot_dependency_file_id}

    async def test_read_telemetry_rejects_legacy_dot_dependency_file_id(self, client: AsyncClient):
        response = await client.get(
            "/telemetry/",
            params={"measurement": "sensor_readings", "dot_dependency_file_id": "heart_rate"},
        )
        payload = _assert_api_error(response, status_code=422)
        assert len(payload["detail"]) == 1
        error = payload["detail"][0]
        assert error["type"] == "uuid_parsing"
        assert error["loc"] == ["query", "dot_dependency_file_id"]
        assert error["input"] == "heart_rate"
        assert "valid UUID" in error["msg"]

    async def test_stream_telemetry_endpoint(self, client: AsyncClient, mock_influx_client):
        patient_id = str(uuid7())
        case_id = str(uuid7())
        device_id = str(uuid7())
        wearable_id = str(uuid7())
        mapping_id = str(uuid7())
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "patient_id": patient_id,
                    "case_id": case_id,
                    "device_id": device_id,
                    "wearable_id": wearable_id,
                    "mapping_id": mapping_id,
                    "dot_dependency_file_id": dot_dependency_file_id,
                    "heart_rate": 72,
                }
            )

        async def query_stream(*args, **kwargs):
            return gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/stream",
            params={"measurement": "sensor_readings", "patient_id": "p1", "limit": 10},
        )
        assert response.status_code == 200
        assert "application/x-ndjson" in response.headers["content-type"]
        lines = [line for line in response.text.splitlines() if line.strip()]
        assert len(lines) == 1
        body = json.loads(lines[0])
        assert body["measurement"] == "sensor_readings"
        assert body["tags"]["patient_id"] == patient_id

    async def test_stream_telemetry_raw_endpoint(self, client: AsyncClient, mock_influx_client):
        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 72,
                    "patient_id": "p1",
                }
            )

        async def query_stream(*args, **kwargs):
            return gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        response = await client.get(
            "/telemetry/raw/stream",
            params={"measurement": "sensor_readings", "patient_id": "p1", "limit": 10},
        )
        assert response.status_code == 200
        assert "application/x-ndjson" in response.headers["content-type"]
        lines = [line for line in response.text.splitlines() if line.strip()]
        assert len(lines) == 1
        body = json.loads(lines[0])
        assert body["measurement"] == "sensor_readings"
        assert body["field"] == "heart_rate"
