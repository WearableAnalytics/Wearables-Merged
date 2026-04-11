import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import pytest
from httpx import AsyncClient

from app.core.json_types import JsonObject
from tests.helpers.api import assert_graphql_ok as _assert_graphql_ok
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.common import eventually as _eventually

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def _new_telemetry_ids() -> dict[str, UUID]:
    return {
        "patient_id": uuid7(),
        "case_id": uuid7(),
        "device_id": uuid7(),
        "wearable_id": uuid7(),
        "mapping_id": uuid7(),
        "context_id": uuid7(),
        "dot_dependency_file_id": uuid7(),
    }


def _telemetry_payload(
    *,
    ids: dict[str, UUID],
    measurement: str,
    timestamp: datetime,
    field_value: int | float | None = None,
    fields: JsonObject | None = None,
    sensor_type: str = "ecg",
    site: str | None = None,
    device_id: UUID | None = None,
    include_context: bool = True,
) -> JsonObject:
    payload: JsonObject = {
        "patient_id": str(ids["patient_id"]),
        "case_id": str(ids["case_id"]),
        "device_id": str(device_id if device_id is not None else ids["device_id"]),
        "wearable_id": str(ids["wearable_id"]),
        "mapping_id": str(ids["mapping_id"]),
        "dot_dependency_file_id": str(ids["dot_dependency_file_id"]),
        "measurement": measurement,
        "timestamp": timestamp.isoformat(),
        "fields": fields if fields is not None else {"heart_rate": field_value},
        "other_tags": {"sensor_type": sensor_type},
    }
    if include_context:
        payload["context_id"] = str(ids["context_id"])
    if site is not None:
        payload["other_tags"]["site"] = site
    return payload


def _telemetry_query_params(
    *,
    ids: dict[str, UUID],
    measurement: str,
    limit: int,
    start: datetime | None = None,
    end: datetime | str | None = None,
    extra: dict[str, str | int] | None = None,
) -> dict[str, str | int]:
    params: dict[str, str | int] = {
        "measurement": measurement,
        "patient_id": str(ids["patient_id"]),
        "limit": limit,
    }
    if start is not None:
        params["start"] = start.isoformat()
    if end is not None:
        params["end"] = end.isoformat() if isinstance(end, datetime) else end
    if extra is not None:
        params.update(extra)
    return params


async def _post_telemetry_points(
    client: AsyncClient,
    *,
    ids: dict[str, UUID],
    measurement: str,
    points: list[tuple[datetime, int]],
    site: str | None = None,
    rotate_device: bool = False,
) -> None:
    for timestamp, value in points:
        payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=timestamp,
            field_value=value,
            site=site,
            device_id=uuid7() if rotate_device else None,
        )
        _assert_json_response(await client.post("/telemetry/", json=payload), status_code=201)


async def _post_telemetry_payloads(client: AsyncClient, payloads: list[JsonObject]) -> None:
    for payload in payloads:
        _assert_json_response(await client.post("/telemetry/", json=payload), status_code=201)


async def _walk_window_items(
    client: AsyncClient,
    url: str,
    *,
    params: dict[str, str | int],
) -> list[dict[str, Any]]:
    current_params = dict(params)
    items: list[dict[str, Any]] = []

    while True:
        body = _assert_json_response(await client.get(url, params=current_params), status_code=200)
        items.extend(body["items"])
        if not body["has_more"]:
            return items
        next_end = body["next_end"]
        assert next_end is not None
        current_params["end"] = next_end


async def _read_ndjson_items(
    client: AsyncClient,
    url: str,
    *,
    params: dict[str, str | int],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async with client.stream("GET", url, params=params) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if not line:
                continue
            items.append(json.loads(line))
    return items


class TestTelemetryWorkflowIntegration:
    async def test_rest_telemetry_follow_up_window_excludes_boundary_duplicates(self, integration_client: AsyncClient):
        measurement = f"it_window_boundary_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        timestamp = datetime.now(UTC).replace(microsecond=0)
        baseline_points = [
            (timestamp, 101),
            (timestamp - timedelta(seconds=1), 102),
            (timestamp - timedelta(seconds=2), 103),
        ]
        baseline_rates = [value for _, value in baseline_points]

        await _post_telemetry_points(
            integration_client,
            ids=ids,
            measurement=measurement,
            points=baseline_points,
            rotate_device=True,
        )

        async def fetch_baseline():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(ids=ids, measurement=measurement, limit=10),
            )
            payload = _assert_json_response(response, status_code=200)
            rates = {item["fields"].get("heart_rate") for item in payload["items"]}
            return payload if set(baseline_rates).issubset(rates) else None

        baseline_page = await _eventually(fetch_baseline)
        assert baseline_page is not None

        first_page = _assert_json_response(
            await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=2,
                    end=timestamp + timedelta(minutes=1),
                ),
            ),
            status_code=200,
        )
        assert len(first_page["items"]) == 2
        assert first_page["has_more"] is True
        assert first_page["next_end"] is not None

        new_rate = 999
        await _post_telemetry_points(
            integration_client,
            ids=ids,
            measurement=measurement,
            points=[(timestamp + timedelta(minutes=5), new_rate)],
            rotate_device=True,
        )

        second_page = _assert_json_response(
            await integration_client.get(
                "/telemetry/",
                params={
                    "measurement": measurement,
                    "patient_id": str(ids["patient_id"]),
                    "limit": 2,
                    "end": first_page["next_end"],
                },
            ),
            status_code=200,
        )

        combined_rates = [item["fields"]["heart_rate"] for item in [*first_page["items"], *second_page["items"]]]
        assert len(combined_rates) == 3
        assert set(combined_rates) == set(baseline_rates)
        assert new_rate not in combined_rates

        async def fetch_latest():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=10,
                    end=timestamp + timedelta(minutes=10),
                ),
            )
            payload = _assert_json_response(response, status_code=200)
            rates = {item["fields"].get("heart_rate") for item in payload["items"]}
            return payload if new_rate in rates else None

        latest_page = await _eventually(fetch_latest)
        assert latest_page is not None

    async def test_rest_telemetry_roundtrip_with_time_windows(self, integration_client: AsyncClient):
        measurement = f"it_sensor_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()

        now_utc = datetime.now(UTC).replace(microsecond=0)
        older = now_utc - timedelta(minutes=1)

        await _post_telemetry_points(
            integration_client,
            ids=ids,
            measurement=measurement,
            points=[(older, 71), (now_utc, 72)],
        )

        async def fetch_first_page():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=1,
                    end=now_utc + timedelta(minutes=1),
                ),
            )
            body = _assert_json_response(response, status_code=200)
            return body if body["items"] else None

        first_page = await _eventually(
            fetch_first_page,
            message="Telemetry first page did not return the newest written ECG point",
        )
        assert first_page is not None, "Telemetry points were not visible in Influx query results"
        assert len(first_page["items"]) == 1
        assert first_page["has_more"] is True
        assert first_page["next_end"] is not None
        assert first_page["items"][0]["fields"]["heart_rate"] == 72

        second_page = _assert_json_response(
            await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(ids=ids, measurement=measurement, limit=1, end=first_page["next_end"]),
            ),
            status_code=200,
        )
        assert len(second_page["items"]) == 1
        assert second_page["items"][0]["fields"]["heart_rate"] == 71
        assert second_page["has_more"] is False

        search_body = _assert_json_response(
            await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=10,
                    extra={"sensor_type": "ecg"},
                ),
            ),
            status_code=200,
        )
        assert len(search_body["items"]) == 2
        assert {item["fields"]["heart_rate"] for item in search_body["items"]} == {71, 72}
        assert all(item["measurement"] == measurement for item in search_body["items"])
        assert all(item["tags"]["patient_id"] == str(ids["patient_id"]) for item in search_body["items"])
        assert all(
            item["tags"]["dot_dependency_file_id"] == str(ids["dot_dependency_file_id"])
            for item in search_body["items"]
        )
        assert all(item["tags"].get("sensor_type") == "ecg" for item in search_body["items"])

    async def test_rest_telemetry_treats_entity_ids_as_influx_tags(self, integration_client: AsyncClient):
        measurement = f"it_tag_contract_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        timestamp = datetime.now(UTC).replace(microsecond=0)

        payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=timestamp,
            fields={"heart_rate": 66},
            site="remote",
        )
        _assert_json_response(await integration_client.post("/telemetry/", json=payload), status_code=201)

        async def fetch_page():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=10,
                    end=timestamp + timedelta(minutes=1),
                ),
            )
            body = _assert_json_response(response, status_code=200)
            return body if body["items"] else None

        page = await _eventually(
            fetch_page,
            message="Telemetry tag contract read did not return the point written with opaque UUID tags",
        )
        assert len(page["items"]) == 1

        item = page["items"][0]
        assert item["measurement"] == measurement
        assert item["fields"] == {"heart_rate": 66}
        assert item["tags"]["patient_id"] == str(ids["patient_id"])
        assert item["tags"]["case_id"] == str(ids["case_id"])
        assert item["tags"]["device_id"] == str(ids["device_id"])
        assert item["tags"]["wearable_id"] == str(ids["wearable_id"])
        assert item["tags"]["mapping_id"] == str(ids["mapping_id"])
        assert item["tags"]["context_id"] == str(ids["context_id"])
        assert item["tags"]["dot_dependency_file_id"] == str(ids["dot_dependency_file_id"])
        assert item["tags"]["site"] == "remote"


class TestExtendedTelemetryAndGraphQLIntegration:
    async def test_telemetry_batch_rest_and_graphql_window_roundtrip(self, integration_client: AsyncClient):
        measurement = f"it_full_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()

        newest = datetime.now(UTC).replace(microsecond=0)
        middle = newest - timedelta(minutes=1)
        oldest = middle - timedelta(minutes=1)

        batch_payload = [
            _telemetry_payload(ids=ids, measurement=measurement, timestamp=ts, field_value=value, site="icu")
            for ts, value in ((oldest, 65), (middle, 67), (newest, 69))
        ]
        _assert_json_response(await integration_client.post("/telemetry/batch", json=batch_payload), status_code=201)

        async def fetch_rest_page():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=2,
                    end=newest + timedelta(minutes=1),
                ),
            )
            body = _assert_json_response(response, status_code=200)
            return body if body["items"] else None

        first_rest_page = await _eventually(fetch_rest_page)
        assert first_rest_page is not None, "REST telemetry query did not return newly written points"
        assert len(first_rest_page["items"]) == 2
        assert first_rest_page["has_more"] is True
        assert first_rest_page["next_end"] is not None

        second_rest_page = _assert_json_response(
            await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=2,
                    end=first_rest_page["next_end"],
                ),
            ),
            status_code=200,
        )
        assert len(second_rest_page["items"]) == 1
        assert second_rest_page["has_more"] is False

        search_payload = _assert_json_response(
            await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=10,
                    extra={"sensor_type": "ecg", "site": "icu"},
                ),
            ),
            status_code=200,
        )
        assert len(search_payload["items"]) == 3
        assert all(
            item["tags"]["dot_dependency_file_id"] == str(ids["dot_dependency_file_id"])
            for item in search_payload["items"]
        )
        assert all(item["tags"].get("sensor_type") == "ecg" for item in search_payload["items"])

        graphql_query = """
            query TelemetryWindow(
                $measurement: String!,
                $patientId: String!,
                $dotDependencyFileId: UUID!,
                $end: AwareDateTime
            ) {
                telemetry(
                    query: {
                        measurement: $measurement
                        tags: [
                            { key: "patient_id", match: { value: $patientId } }
                            { key: "sensor_type", match: { value: "ecg" } }
                        ]
                        dotDependencyFileIds: [$dotDependencyFileId]
                        limit: 2
                        end: $end
                    }
                ) {
                    items {
                        measurement
                        tags
                        fields
                    }
                    hasMore
                    nextEnd
                }
            }
        """

        async def fetch_graphql_first_page() -> dict[str, Any] | None:
            response = await integration_client.post(
                "/graphql",
                json={
                    "query": graphql_query,
                    "variables": {
                        "measurement": measurement,
                        "patientId": str(ids["patient_id"]),
                        "dotDependencyFileId": str(ids["dot_dependency_file_id"]),
                        "end": (newest + timedelta(minutes=1)).isoformat(),
                    },
                },
            )
            body = _assert_graphql_ok(response)
            payload = body["data"]["telemetry"]
            return payload if payload["items"] else None

        first_graphql_page = await _eventually(fetch_graphql_first_page)
        assert first_graphql_page is not None, "GraphQL telemetry query did not return newly written points"
        assert len(first_graphql_page["items"]) == 2
        assert first_graphql_page["hasMore"] is True
        assert first_graphql_page["nextEnd"] is not None

        second_graphql_body = _assert_graphql_ok(
            await integration_client.post(
                "/graphql",
                json={
                    "query": graphql_query,
                    "variables": {
                        "measurement": measurement,
                        "patientId": str(ids["patient_id"]),
                        "dotDependencyFileId": str(ids["dot_dependency_file_id"]),
                        "end": first_graphql_page["nextEnd"],
                    },
                },
            )
        )

        second_graphql_page = second_graphql_body["data"]["telemetry"]
        assert len(second_graphql_page["items"]) == 1
        assert second_graphql_page["hasMore"] is False

    async def test_structured_telemetry_groups_multiple_fields_per_timestamp(self, integration_client: AsyncClient):
        measurement = f"it_struct_group_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        timestamp = datetime.now(UTC).replace(microsecond=0)

        payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=timestamp,
            fields={"heart_rate": 68, "spo2": 97},
            site="icu",
        )
        _assert_json_response(await integration_client.post("/telemetry/", json=payload), status_code=201)

        async def fetch_page():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=10,
                    end=timestamp + timedelta(minutes=1),
                ),
            )
            body = _assert_json_response(response, status_code=200)
            return body if body["items"] else None

        page = await _eventually(fetch_page)
        assert page is not None
        assert len(page["items"]) == 1
        assert page["items"][0]["fields"] == {"heart_rate": 68, "spo2": 97}
        assert page["items"][0]["tags"]["sensor_type"] == "ecg"

    async def test_structured_telemetry_handles_missing_optional_context(self, integration_client: AsyncClient):
        measurement = f"it_struct_sparse_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        timestamp = datetime.now(UTC).replace(microsecond=0)

        payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=timestamp,
            field_value=70,
            include_context=False,
            site="ward",
        )
        _assert_json_response(await integration_client.post("/telemetry/", json=payload), status_code=201)

        async def fetch_page():
            response = await integration_client.get(
                "/telemetry/",
                params=_telemetry_query_params(ids=ids, measurement=measurement, limit=10),
            )
            body = _assert_json_response(response, status_code=200)
            return body if body["items"] else None

        page = await _eventually(fetch_page)
        assert page is not None
        assert len(page["items"]) == 1
        assert "context_id" not in page["items"][0]["tags"]
        assert page["items"][0]["fields"]["heart_rate"] == 70

    async def test_raw_and_structured_reads_agree_on_same_time_slice(self, integration_client: AsyncClient):
        measurement = f"it_struct_agree_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        timestamp = datetime.now(UTC).replace(microsecond=0)

        payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=timestamp,
            fields={"heart_rate": 71, "spo2": 98},
            site="icu",
        )
        _assert_json_response(await integration_client.post("/telemetry/", json=payload), status_code=201)

        async def fetch_bodies():
            structured = _assert_json_response(
                await integration_client.get(
                    "/telemetry/",
                    params=_telemetry_query_params(
                        ids=ids,
                        measurement=measurement,
                        limit=10,
                        end=timestamp + timedelta(minutes=1),
                    ),
                ),
                status_code=200,
            )
            raw = _assert_json_response(
                await integration_client.get(
                    "/telemetry/raw",
                    params=_telemetry_query_params(
                        ids=ids,
                        measurement=measurement,
                        limit=10,
                        end=timestamp + timedelta(minutes=1),
                    ),
                ),
                status_code=200,
            )
            return structured if structured["items"] and raw["items"] else None

        result = await _eventually(fetch_bodies)
        assert result is not None
        structured = result
        raw = _assert_json_response(
            await integration_client.get(
                "/telemetry/raw",
                params=_telemetry_query_params(
                    ids=ids,
                    measurement=measurement,
                    limit=10,
                    end=timestamp + timedelta(minutes=1),
                ),
            ),
            status_code=200,
        )
        assert len(structured["items"]) == 1
        assert {item["field"]: item["value"] for item in raw["items"]} == {"heart_rate": 71, "spo2": 98}
        assert structured["items"][0]["fields"] == {"heart_rate": 71, "spo2": 98}

    async def test_raw_window_walk_returns_all_rows_exactly_once(self, integration_client: AsyncClient):
        measurement = f"it_raw_window_full_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        newest = datetime.now(UTC).replace(microsecond=0)
        older = newest - timedelta(seconds=1)
        second_device_id = uuid7()

        first_payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=newest,
            fields={"heart_rate": 71, "spo2": 98},
            site="icu",
        )
        second_payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=newest,
            fields={"resp_rate": 16},
            device_id=second_device_id,
            site="ward",
        )
        third_payload = _telemetry_payload(
            ids=ids,
            measurement=measurement,
            timestamp=older,
            fields={"temperature": 36.8},
            site="icu",
        )

        await _post_telemetry_payloads(integration_client, [first_payload, second_payload, third_payload])

        params = _telemetry_query_params(ids=ids, measurement=measurement, limit=1, end=newest + timedelta(minutes=1))

        async def fetch_all_rows():
            items = await _walk_window_items(integration_client, "/telemetry/raw", params=params)
            return items if len(items) == 4 else None

        items = await _eventually(fetch_all_rows)
        assert items is not None
        assert len(items) == 4
        assert (
            len(
                {
                    (
                        item["timestamp"],
                        item["tags"]["device_id"],
                        item["field"],
                        str(item["value"]),
                    )
                    for item in items
                }
            )
            == 4
        )

        first_page = _assert_json_response(
            await integration_client.get("/telemetry/raw", params=params),
            status_code=200,
        )
        assert len(first_page["items"]) == 3
        assert {item["field"] for item in first_page["items"]} == {"heart_rate", "spo2", "resp_rate"}

    async def test_raw_stream_returns_full_dataset_without_limit(self, integration_client: AsyncClient):
        measurement = f"it_raw_stream_full_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        newest = datetime.now(UTC).replace(microsecond=0)
        older = newest - timedelta(seconds=1)
        second_device_id = uuid7()

        payloads = (
            _telemetry_payload(
                ids=ids,
                measurement=measurement,
                timestamp=newest,
                fields={"heart_rate": 72, "spo2": 97},
                site="icu",
            ),
            _telemetry_payload(
                ids=ids,
                measurement=measurement,
                timestamp=newest,
                fields={"resp_rate": 15},
                device_id=second_device_id,
                site="ward",
            ),
            _telemetry_payload(
                ids=ids,
                measurement=measurement,
                timestamp=older,
                fields={"temperature": 36.6},
                site="icu",
            ),
        )
        await _post_telemetry_payloads(integration_client, list(payloads))

        params = _telemetry_query_params(
            ids=ids,
            measurement=measurement,
            limit=10,
            start=older - timedelta(minutes=1),
            end=newest + timedelta(minutes=1),
        )

        async def fetch_stream():
            items = await _read_ndjson_items(integration_client, "/telemetry/raw/stream", params=params)
            return items if len(items) == 4 else None

        items = await _eventually(fetch_stream)
        assert items is not None
        assert len(items) == 4
        assert (
            len({(item["timestamp"], item["tags"]["device_id"], item["field"], str(item["value"])) for item in items})
            == 4
        )

    async def test_structured_stream_returns_full_grouped_dataset_without_limit(self, integration_client: AsyncClient):
        measurement = f"it_struct_stream_full_{uuid7().hex[:10]}"
        ids = _new_telemetry_ids()
        newest = datetime.now(UTC).replace(microsecond=0)
        older = newest - timedelta(seconds=1)
        second_device_id = uuid7()

        payloads = (
            _telemetry_payload(
                ids=ids,
                measurement=measurement,
                timestamp=newest,
                fields={"heart_rate": 73, "spo2": 99},
                site="icu",
            ),
            _telemetry_payload(
                ids=ids,
                measurement=measurement,
                timestamp=newest,
                fields={"resp_rate": 14},
                device_id=second_device_id,
                site="ward",
            ),
            _telemetry_payload(
                ids=ids,
                measurement=measurement,
                timestamp=older,
                fields={"temperature": 36.5},
                site="icu",
            ),
        )
        for payload in payloads:
            _assert_json_response(await integration_client.post("/telemetry/", json=payload), status_code=201)

        params = {
            "measurement": measurement,
            "patient_id": str(ids["patient_id"]),
            "start": (older - timedelta(minutes=1)).isoformat(),
            "end": (newest + timedelta(minutes=1)).isoformat(),
        }

        async def fetch_stream():
            items = await _read_ndjson_items(integration_client, "/telemetry/stream", params=params)
            return items if len(items) == 3 else None

        items = await _eventually(fetch_stream)
        assert items is not None
        assert len(items) == 3
        assert (
            len(
                {
                    (
                        item["timestamp"],
                        item["tags"]["device_id"],
                        tuple(sorted(item["fields"].items())),
                    )
                    for item in items
                }
            )
            == 3
        )
