import asyncio
from datetime import UTC, datetime
from uuid import uuid7

import pytest

from app.core.config import settings
from app.db.influx.telemetry import TelemetryRepo
from app.db.influx.telemetry.queries import build_field_filter_clause
from app.db.influx.telemetry.schema import TelemetrySchemaStore
from app.schemas.telemetry import TelemetryCreate
from app.telemetry.types import MeasurementSchema
from tests.helpers.common import empty_async_iterator

pytestmark = pytest.mark.anyio


def _uuid_str() -> str:
    return str(uuid7())


def _telemetry_create(**overrides) -> TelemetryCreate:
    payload = {
        "patient_id": uuid7(),
        "case_id": uuid7(),
        "device_id": uuid7(),
        "wearable_id": uuid7(),
        "mapping_id": uuid7(),
        "dot_dependency_file_id": uuid7(),
        "measurement": "sensor_readings",
        "timestamp": datetime.now(UTC),
        "other_tags": {},
        "fields": {"heart_rate": 70},
    }
    payload.update(overrides)
    return TelemetryCreate(**payload)


class TestTelemetryRepoBatchWrite:
    async def test_write_batch_single_client_call(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        points = [_telemetry_create() for _ in range(5)]

        await repo.write_batch(points)

        write_api = mock_influx_client.write_api.return_value
        assert write_api.write.await_count == 1

        _, kwargs = write_api.write.await_args
        assert kwargs["bucket"] == "medical_data"
        assert len(kwargs["record"]) == 5

    async def test_write_point_uses_normalized_dict_payload(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        point = _telemetry_create(
            other_tags={"sensor_type": "ecg"},
            fields={"heart_rate": 70, "ignored": None},
        )

        await repo.write_point(point)

        _, kwargs = mock_influx_client.write_api.return_value.write.await_args
        record = kwargs["record"]
        line_protocol = record.to_line_protocol()
        assert "sensor_readings" in line_protocol
        assert "patient_id=" in line_protocol
        assert "sensor_type=ecg" in line_protocol
        assert "heart_rate=70i" in line_protocol
        assert "ignored" not in line_protocol

    async def test_write_point_rejects_empty_effective_fields(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)

        with pytest.raises(ValueError, match="Point must contain at least one non-None field"):
            await repo.write_point(_telemetry_create(fields={"heart_rate": None}))


class TestTelemetryRepoRead:
    async def test_get_points_allows_tag_only_query_without_measurement(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)

        class Record:
            def __init__(self, values):
                self.values = values

        captured: dict[str, object] = {}

        async def point_gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 3, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                }
            )

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux or "schema.measurementFieldKeys" in flux:
                pytest.fail("Schema queries are not expected when measurement is omitted.")
            captured["flux"] = flux
            captured["params"] = kwargs.get("params", {})
            return point_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(
            measurement=None,
            tags={"patient_id": ["p1"]},
            bucket="research_data",
            limit=10,
        )
        assert len(window.items) == 1
        assert window.items[0]["measurement"] == "sensor_readings"
        assert window.items[0]["tags"]["patient_id"] == "p1"
        assert window.items[0]["fields"] == {"heart_rate": 70}

        params = captured["params"]
        assert isinstance(params, dict)
        assert params["bucket_param"] == "research_data"
        assert "measurement_param" not in params
        assert isinstance(captured["flux"], str)
        assert 'r["_measurement"] == measurement_param' not in captured["flux"]

    async def test_get_points_uses_limit_plus_one_for_window_continuation(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def point_gen():
            for ts, _key in (
                (datetime(2026, 1, 3, tzinfo=UTC), "k3"),
                (datetime(2026, 1, 2, tzinfo=UTC), "k2"),
                (datetime(2026, 1, 1, tzinfo=UTC), "k1"),
            ):
                yield Record(
                    {
                        "_time": ts,
                        "_measurement": "sensor_readings",
                        "_field": "heart_rate",
                        "_value": 70,
                        "patient_id": "p1",
                        "device_id": "d1",
                        "wearable_id": "w1",
                        "case_id": "c1",
                        "mapping_id": "m1",
                        "dot_dependency_file_id": dot_dependency_file_id,
                    }
                )

        async def tag_key_gen():
            for key in ("patient_id", "device_id", "wearable_id", "case_id", "mapping_id", "dot_dependency_file_id"):
                yield Record({"_value": key})

        async def field_key_gen():
            yield Record({"_value": "heart_rate"})

        captured_main_flux = ""

        async def query_stream(*args, **kwargs):
            nonlocal captured_main_flux
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            captured_main_flux = flux
            return point_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(measurement="sensor_readings", limit=2)
        assert len(window.items) == 2
        assert window.has_more is True
        assert window.next_end == datetime(2026, 1, 2, tzinfo=UTC)

        assert '|> sort(columns: ["_time"], desc: true)' in captured_main_flux
        assert "|> limit(" not in captured_main_flux
        assert "_cursor_key" not in captured_main_flux

    async def test_get_points_keeps_sparse_tag_columns_without_flux_pivot(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)

        class Record:
            def __init__(self, values):
                self.values = values

        captured_main_flux = ""

        async def point_gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 3, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                }
            )

        async def query_stream(*args, **kwargs):
            nonlocal captured_main_flux
            flux = args[0] if args else ""
            captured_main_flux = flux
            return point_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(measurement="sensor_readings", limit=10)

        assert len(window.items) == 1
        assert window.items[0]["tags"]["patient_id"] == "p1"
        assert "context_id" not in window.items[0]["tags"]
        assert "|> keep(columns:" not in captured_main_flux
        assert "|> pivot(" not in captured_main_flux
        assert "|> group(columns: [])" not in captured_main_flux

    async def test_stream_points_returns_grouped_items_without_flux_row_limits(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        produced: list[int] = []
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        timestamps = (
            datetime(2026, 1, 3, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )

        async def point_gen(limit: int | None = None):
            for index, ts in enumerate(timestamps):
                if limit is not None and index >= limit:
                    break
                produced.append(index)
                yield Record(
                    {
                        "_time": ts,
                        "_measurement": "sensor_readings",
                        "_field": "heart_rate",
                        "_value": 70 + index,
                        "patient_id": "p1",
                        "device_id": "d1",
                        "wearable_id": "w1",
                        "case_id": "c1",
                        "mapping_id": "m1",
                        "dot_dependency_file_id": dot_dependency_file_id,
                    }
                )

        async def tag_key_gen():
            for key in ("patient_id", "device_id", "wearable_id", "case_id", "mapping_id", "dot_dependency_file_id"):
                yield Record({"_value": key})

        async def field_key_gen():
            yield Record({"_value": "heart_rate"})

        query_calls = 0

        async def empty_gen():
            if False:
                yield None

        async def query_stream(*args, **kwargs):
            nonlocal query_calls
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            if "|> limit(" in flux:
                pytest.fail("Structured stream query should not rely on Flux row limits.")
            query_calls += 1
            if query_calls == 1:
                return point_gen(limit=2)
            return empty_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        point_stream = repo.stream_structured(measurement="sensor_readings", limit=2)
        first = await anext(point_stream)
        assert produced == [0, 1]
        assert first["fields"]["heart_rate"] == 70

        second = await anext(point_stream)
        assert produced == [0, 1]
        assert second["fields"]["heart_rate"] == 71

        with pytest.raises(StopAsyncIteration):
            await anext(point_stream)

    async def test_get_points_separates_unfiltered_custom_tags_from_fields(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def point_gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 3, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                    "sensor_type": "ecg",
                    "site": "icu",
                }
            )

        async def tag_key_gen():
            for key in (
                "patient_id",
                "device_id",
                "wearable_id",
                "case_id",
                "mapping_id",
                "dot_dependency_file_id",
                "sensor_type",
                "site",
            ):
                yield Record({"_value": key})

        async def field_key_gen():
            yield Record({"_value": "heart_rate"})

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            return point_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(measurement="sensor_readings", limit=10)
        assert len(window.items) == 1
        item = window.items[0]
        assert item["tags"]["sensor_type"] == "ecg"
        assert item["tags"]["site"] == "icu"
        assert item["fields"] == {"heart_rate": 70}

    async def test_get_points_keeps_explicit_string_fields_under_fields(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def point_gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 3, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "status",
                    "_value": "stable",
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                    "sensor_type": "ecg",
                }
            )

        async def tag_key_gen():
            for key in (
                "patient_id",
                "device_id",
                "wearable_id",
                "case_id",
                "mapping_id",
                "dot_dependency_file_id",
                "sensor_type",
            ):
                yield Record({"_value": key})

        async def field_key_gen():
            yield Record({"_value": "status"})

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            return point_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(measurement="sensor_readings", fields=["status"], limit=10)
        assert len(window.items) == 1
        item = window.items[0]
        assert item["fields"] == {"status": "stable"}
        assert item["tags"]["sensor_type"] == "ecg"

    async def test_get_points_raw_preserves_native_value_type(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        timestamp = datetime.now(UTC).replace(microsecond=0)

        class Record:
            def __init__(self, values):
                self.values = values

        async def point_gen():
            yield Record(
                {
                    "_time": timestamp,
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 72,
                    "patient_id": "p1",
                }
            )

        async def tag_key_gen():
            yield Record({"_value": "patient_id"})

        async def field_key_gen():
            yield Record({"_value": "heart_rate"})

        captured_main_flux = ""

        async def query_stream(*args, **kwargs):
            nonlocal captured_main_flux
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            captured_main_flux = flux
            params = kwargs.get("params", {})
            start_param = params.get("start_param")
            stop_param = params.get("stop_param")
            if (
                isinstance(start_param, datetime)
                and isinstance(stop_param, datetime)
                and start_param <= timestamp < stop_param
            ):
                return point_gen()
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_raw_window(measurement="sensor_readings", limit=10)
        assert len(window.items) == 1
        assert window.items[0]["value"] == 72
        assert isinstance(window.items[0]["value"], int)
        assert "toString()" not in captured_main_flux
        assert "_cursor_key" not in captured_main_flux
        assert "|> group(columns: [])" not in captured_main_flux

    async def test_get_points_groups_multiple_field_rows_into_one_item(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        timestamp = datetime(2026, 1, 3, tzinfo=UTC)

        async def point_gen():
            yield Record(
                {
                    "_time": timestamp,
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                    "sensor_type": "ecg",
                }
            )
            yield Record(
                {
                    "_time": timestamp,
                    "_measurement": "sensor_readings",
                    "_field": "spo2",
                    "_value": 98,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                    "sensor_type": "ecg",
                }
            )

        async def tag_key_gen():
            for key in (
                "patient_id",
                "device_id",
                "wearable_id",
                "case_id",
                "mapping_id",
                "dot_dependency_file_id",
                "sensor_type",
            ):
                yield Record({"_value": key})

        async def field_key_gen():
            for key in ("heart_rate", "spo2"):
                yield Record({"_value": key})

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            return point_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(measurement="sensor_readings", limit=10)
        assert len(window.items) == 1
        assert window.items[0]["fields"] == {"heart_rate": 70, "spo2": 98}
        assert window.items[0]["tags"]["sensor_type"] == "ecg"

    async def test_get_points_raw_skips_schema_lookup_for_measurement_queries(self, mock_influx_client):
        repo = TelemetryRepo(mock_influx_client)
        timestamp = datetime.now(UTC).replace(microsecond=0)

        class Record:
            def __init__(self, values):
                self.values = values

        async def point_gen():
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
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux or "schema.measurementFieldKeys" in flux:
                pytest.fail("Raw measurement queries should not perform schema discovery.")
            params = kwargs.get("params", {})
            start_param = params.get("start_param")
            stop_param = params.get("stop_param")
            if (
                isinstance(start_param, datetime)
                and isinstance(stop_param, datetime)
                and start_param <= timestamp < stop_param
            ):
                return point_gen()
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_raw_window(measurement="sensor_readings", limit=10)
        assert len(window.items) == 1
        assert window.items[0]["value"] == 72

    def test_field_filter_uses_equality_for_single_field(self):
        params: dict[str, object] = {}

        clause = build_field_filter_clause(fields=["heart_rate"], params=params)

        assert clause is not None
        assert params == {"field_val_0": "heart_rate"}
        assert "field_val_0" in clause
        assert "heart_rate" not in clause

    def test_field_filter_uses_or_chain_for_small_field_lists(self):
        params: dict[str, object] = {}

        clause = build_field_filter_clause(fields=["heart_rate", "spo2"], params=params)

        assert clause is not None
        assert params == {"field_val_0": "heart_rate", "field_val_1": "spo2"}
        assert "field_val_0" in clause
        assert "field_val_1" in clause
        assert "contains(" not in clause
        assert "heart_rate" not in clause
        assert "spo2" not in clause

    def test_field_filter_uses_contains_for_large_field_lists(self):
        params: dict[str, object] = {}
        fields = [f"field_{index}" for index in range(9)]

        clause = build_field_filter_clause(fields=fields, params=params)

        assert clause is not None
        assert params == {"field_set_param": fields}
        assert "contains(" in clause
        assert "field_set_param" in clause

    async def test_get_points_expands_structured_windows_when_first_slice_is_too_small(
        self,
        mock_influx_client,
        monkeypatch,
    ):
        repo = TelemetryRepo(mock_influx_client)
        dot_dependency_file_id = _uuid_str()
        original_initial = settings.INFLUX_STRUCTURED_READ_INITIAL_WINDOW_SECONDS
        original_max = settings.INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS
        original_growth = settings.INFLUX_STRUCTURED_READ_WINDOW_GROWTH_FACTOR
        monkeypatch.setattr(settings, "INFLUX_STRUCTURED_READ_INITIAL_WINDOW_SECONDS", 60)
        monkeypatch.setattr(settings, "INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS", 300)
        monkeypatch.setattr(settings, "INFLUX_STRUCTURED_READ_WINDOW_GROWTH_FACTOR", 2.0)

        class Record:
            def __init__(self, values):
                self.values = values

        base_end = datetime(2026, 1, 3, 0, 3, tzinfo=UTC)
        queried_windows: list[tuple[datetime, datetime]] = []
        data_by_window = {
            (
                datetime(2026, 1, 3, 0, 2, tzinfo=UTC),
                datetime(2026, 1, 3, 0, 3, tzinfo=UTC),
            ): [
                {
                    "_time": datetime(2026, 1, 3, 0, 2, 30, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 72,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                }
            ],
            (
                datetime(2026, 1, 3, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 3, 0, 2, tzinfo=UTC),
            ): [
                {
                    "_time": datetime(2026, 1, 3, 0, 1, 30, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 71,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                },
                {
                    "_time": datetime(2026, 1, 3, 0, 0, 30, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                },
            ],
        }

        async def tag_key_gen():
            for key in ("patient_id", "device_id", "wearable_id", "case_id", "mapping_id", "dot_dependency_file_id"):
                yield Record({"_value": key})

        async def field_key_gen():
            yield Record({"_value": "heart_rate"})

        async def row_gen(rows):
            for row in rows:
                yield Record(row)

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            params = kwargs.get("params", {})
            if "schema.measurementTagKeys" in flux:
                return tag_key_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_key_gen()
            if "|> limit(" in flux:
                pytest.fail("Structured window reads should not use Flux row limits.")
            window = (params["start_param"], params["stop_param"])
            queried_windows.append(window)
            return row_gen(data_by_window.get(window, []))

        mock_influx_client.query_api.return_value.query_stream = query_stream

        window = await repo.read_window(
            measurement="sensor_readings",
            start=datetime(2026, 1, 3, 0, 0, tzinfo=UTC),
            end=base_end,
            limit=2,
        )

        assert [item["fields"]["heart_rate"] for item in window.items] == [72, 71]
        assert window.has_more is True
        assert queried_windows == [
            (
                datetime(2026, 1, 3, 0, 2, tzinfo=UTC),
                datetime(2026, 1, 3, 0, 3, tzinfo=UTC),
            ),
            (
                datetime(2026, 1, 3, 0, 0, tzinfo=UTC),
                datetime(2026, 1, 3, 0, 2, tzinfo=UTC),
            ),
        ]

        monkeypatch.setattr(settings, "INFLUX_STRUCTURED_READ_INITIAL_WINDOW_SECONDS", original_initial)
        monkeypatch.setattr(settings, "INFLUX_STRUCTURED_READ_MAX_WINDOW_SECONDS", original_max)
        monkeypatch.setattr(settings, "INFLUX_STRUCTURED_READ_WINDOW_GROWTH_FACTOR", original_growth)


class TestTelemetrySchemaStore:
    async def test_measurement_schema_cache_reuses_cached_result(self, mock_influx_client):
        store = TelemetrySchemaStore(mock_influx_client.query_api.return_value)
        calls = 0

        class Record:
            def __init__(self, values):
                self.values = values

        async def row_gen(values: list[str]):
            for value in values:
                yield Record({"_value": value})

        async def query_stream(*args, **kwargs):
            nonlocal calls
            calls += 1
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return row_gen(["patient_id"])
            if "schema.measurementFieldKeys" in flux:
                return row_gen(["heart_rate"])
            pytest.fail("Unexpected schema query")

        mock_influx_client.query_api.return_value.query_stream = query_stream

        first = await store.get_measurement_schema("sensor_readings", bucket="medical_data")
        second = await store.get_measurement_schema("sensor_readings", bucket="medical_data")

        assert first == MeasurementSchema(tag_keys=("patient_id",), field_keys=frozenset({"heart_rate"}))
        assert second == first
        assert calls == 2

    async def test_measurement_schema_loads_tag_and_field_keys_concurrently(self, mock_influx_client):
        store = TelemetrySchemaStore(mock_influx_client.query_api.return_value)
        both_started = asyncio.Event()
        entered = 0

        class Record:
            def __init__(self, values):
                self.values = values

        async def row_gen(values: list[str]):
            for value in values:
                yield Record({"_value": value})

        async def query_stream(*args, **kwargs):
            nonlocal entered
            entered += 1
            if entered == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.1)

            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return row_gen(["patient_id"])
            if "schema.measurementFieldKeys" in flux:
                return row_gen(["heart_rate"])
            pytest.fail("Unexpected schema query")

        mock_influx_client.query_api.return_value.query_stream = query_stream

        schema = await store.get_measurement_schema("sensor_readings", bucket="medical_data")

        assert schema == MeasurementSchema(tag_keys=("patient_id",), field_keys=frozenset({"heart_rate"}))
