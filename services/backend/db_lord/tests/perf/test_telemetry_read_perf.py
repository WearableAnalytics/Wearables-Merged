import json
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID, uuid7

import pytest
from httpx import AsyncClient

from app.db.influx.telemetry import TelemetryRepo
from app.schemas.telemetry import TelemetryCreate

pytestmark = [pytest.mark.perf, pytest.mark.integration, pytest.mark.anyio]

_PAGE_SIZE = 50
_FULL_SCAN_LIMIT = 10_000
_TARGET_FIELD_ROWS = 1_000_000
_POINT_BATCH_SIZE = 5_000
_POINT_COUNT = 800_000


def _perf_ids() -> dict[str, UUID]:
    return {
        "patient_id": uuid7(),
        "case_id": uuid7(),
        "device_id": uuid7(),
        "wearable_id": uuid7(),
        "mapping_id": uuid7(),
        "context_id": uuid7(),
        "dot_dependency_file_id": uuid7(),
    }


async def _seed_perf_measurement(repo: TelemetryRepo, measurement: str) -> tuple[dict[str, UUID], datetime]:
    ids = _perf_ids()
    base_timestamp = datetime(2026, 2, 25, 15, 0, tzinfo=UTC)
    pending: list[TelemetryCreate] = []

    for index in range(_POINT_COUNT):
        fields: dict[str, int | float] = {"heart_rate": 60 + (index % 25)}
        if index % 4 == 0:
            fields["spo2"] = 94 + (index % 5)
        context_id = None if index % 5 == 0 else ids["context_id"]
        pending.append(
            TelemetryCreate(
                patient_id=ids["patient_id"],
                case_id=ids["case_id"],
                device_id=ids["device_id"],
                wearable_id=ids["wearable_id"],
                mapping_id=ids["mapping_id"],
                context_id=context_id,
                dot_dependency_file_id=ids["dot_dependency_file_id"],
                measurement=measurement,
                timestamp=base_timestamp + timedelta(seconds=index),
                other_tags={
                    "sensor_type": "ecg" if index % 3 else "pulse_ox",
                    "site": "icu" if index % 2 else "ward",
                    "source": "perf_pytest",
                },
                fields=fields,
            )
        )
        if len(pending) >= _POINT_BATCH_SIZE:
            await repo.write_batch(pending)
            pending.clear()

    if pending:
        await repo.write_batch(pending)

    return ids, base_timestamp


async def _time_http_json(
    client: AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> dict[str, object]:
    started = perf_counter()
    response = await client.request(method, url, **kwargs)
    elapsed = perf_counter() - started
    response.raise_for_status()
    body = response.json()
    return {"elapsed_s": round(elapsed, 2), "status": response.status_code, "body": body}


async def _time_ndjson_stream(client: AsyncClient, url: str, *, params: dict[str, str | int]) -> dict[str, object]:
    started = perf_counter()
    lines: list[dict[str, object]] = []
    async with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line:
                continue
            lines.append(json.loads(line))
            if len(lines) >= _PAGE_SIZE:
                break
    elapsed = perf_counter() - started
    return {"elapsed_s": round(elapsed, 2), "status": 200, "item_count": len(lines)}


async def _time_full_stream(
    client: AsyncClient,
    url: str,
    *,
    params: dict[str, str],
) -> dict[str, object]:
    started = perf_counter()
    item_count = 0
    async with client.stream("GET", url, params=params) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line:
                continue
            item_count += 1
    elapsed = perf_counter() - started
    return {"elapsed_s": round(elapsed, 2), "item_count": item_count}


async def _time_full_window_scan(
    client: AsyncClient,
    url: str,
    *,
    params: dict[str, str],
) -> dict[str, object]:
    current_end = params["end"]
    total_items = 0
    requests = 0
    started = perf_counter()

    while True:
        response = await client.get(
            url,
            params={**params, "limit": _FULL_SCAN_LIMIT, "end": current_end},
        )
        response.raise_for_status()
        body = response.json()
        requests += 1
        total_items += len(body["items"])
        if not body["has_more"]:
            break
        current_end = body["next_end"]
        if current_end is None:
            raise RuntimeError(f"{url} reported has_more=True without next_end")

    elapsed = perf_counter() - started
    return {"elapsed_s": round(elapsed, 2), "requests": requests, "item_count": total_items}


def _print_report_summary(report: dict[str, object]) -> None:
    print("\nTelemetry benchmark summary")
    print(f"target_field_rows={report['target_field_rows']}")

    ordered_metrics = (
        ("current_structured", "REST structured page"),
        ("current_graphql_structured", "GraphQL structured page"),
        ("current_raw", "REST raw page"),
        ("current_raw_heart_rate", "REST raw page heart_rate filter"),
        ("current_raw_stream", "REST raw stream page"),
        ("current_structured_full_scan", "REST structured full scan"),
        ("current_raw_full_scan", "REST raw full scan"),
        ("current_structured_full_stream", "REST structured full stream"),
        ("current_raw_full_stream", "REST raw full stream"),
    )

    for key, label in ordered_metrics:
        metric = report[key]
        if not isinstance(metric, dict):
            continue

        line = f"- {label}: {metric['elapsed_s']}s"
        item_count = metric.get("item_count")
        if item_count is not None:
            line += f", items={item_count}"
        requests = metric.get("requests")
        if requests is not None:
            line += f", requests={requests}"
        has_more = metric.get("has_more")
        if has_more is not None:
            line += f", has_more={has_more}"
        complete = metric.get("complete")
        if complete is not None:
            line += f", complete={complete}"
        print(line)


class TestTelemetryReadPerf:
    async def test_endpoint_read_paths(
        self,
        integration_client: AsyncClient,
        integration_telemetry_repo: TelemetryRepo,
    ) -> None:
        measurement = f"perf_sensor_{uuid7().hex[:10]}"
        _ids, start = await _seed_perf_measurement(integration_telemetry_repo, measurement)
        end = start + timedelta(seconds=_POINT_COUNT + 10)

        graphql_query = """
            query TelemetryWindow($measurement: String!, $start: AwareDateTime!, $end: AwareDateTime!, $limit: Int!) {
                telemetry(query: {
                    measurement: $measurement
                    start: $start
                    end: $end
                    limit: $limit
                    includeResolvedMetadata: false
                }) {
                    hasMore
                    items { timestamp }
                }
            }
        """

        current_structured = await _time_http_json(
            integration_client,
            "GET",
            "/telemetry/",
            params={
                "measurement": measurement,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": _PAGE_SIZE,
            },
        )
        current_graphql = await _time_http_json(
            integration_client,
            "POST",
            "/graphql",
            json={
                "query": graphql_query,
                "variables": {
                    "measurement": measurement,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": _PAGE_SIZE,
                },
            },
        )
        current_raw = await _time_http_json(
            integration_client,
            "GET",
            "/telemetry/raw",
            params={
                "measurement": measurement,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": _PAGE_SIZE,
            },
        )
        current_raw_heart_rate = await _time_http_json(
            integration_client,
            "GET",
            "/telemetry/raw",
            params={
                "measurement": measurement,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": _PAGE_SIZE,
                "fields": "heart_rate",
            },
        )
        raw_stream = await _time_ndjson_stream(
            integration_client,
            "/telemetry/raw/stream",
            params={
                "measurement": measurement,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "limit": _PAGE_SIZE,
            },
        )
        base_params = {
            "measurement": measurement,
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        structured_full_scan = await _time_full_window_scan(
            integration_client,
            "/telemetry/",
            params=base_params,
        )
        raw_full_scan = await _time_full_window_scan(
            integration_client,
            "/telemetry/raw",
            params=base_params,
        )
        structured_full_stream = await _time_full_stream(
            integration_client,
            "/telemetry/stream",
            params=base_params,
        )
        raw_full_stream = await _time_full_stream(
            integration_client,
            "/telemetry/raw/stream",
            params=base_params,
        )

        report = {
            "target_field_rows": _TARGET_FIELD_ROWS,
            "current_structured": {
                "elapsed_s": current_structured["elapsed_s"],
                "item_count": len(current_structured["body"]["items"]),
                "has_more": current_structured["body"]["has_more"],
            },
            "current_graphql_structured": {
                "elapsed_s": current_graphql["elapsed_s"],
                "item_count": len(current_graphql["body"]["data"]["telemetry"]["items"]),
                "has_more": current_graphql["body"]["data"]["telemetry"]["hasMore"],
            },
            "current_raw": {
                "elapsed_s": current_raw["elapsed_s"],
                "item_count": len(current_raw["body"]["items"]),
                "has_more": current_raw["body"]["has_more"],
            },
            "current_raw_heart_rate": {
                "elapsed_s": current_raw_heart_rate["elapsed_s"],
                "item_count": len(current_raw_heart_rate["body"]["items"]),
                "has_more": current_raw_heart_rate["body"]["has_more"],
            },
            "current_raw_stream": raw_stream,
            "current_structured_full_scan": structured_full_scan,
            "current_raw_full_scan": {
                **raw_full_scan,
                "complete": raw_full_scan["item_count"] == _TARGET_FIELD_ROWS,
            },
            "current_structured_full_stream": {
                **structured_full_stream,
                "complete": structured_full_stream["item_count"] == _POINT_COUNT,
            },
            "current_raw_full_stream": {
                **raw_full_stream,
                "complete": raw_full_stream["item_count"] == _TARGET_FIELD_ROWS,
            },
        }
        _print_report_summary(report)

        assert len(current_structured["body"]["items"]) == _PAGE_SIZE
        assert len(current_graphql["body"]["data"]["telemetry"]["items"]) == _PAGE_SIZE
        assert len(current_raw["body"]["items"]) == _PAGE_SIZE
        assert len(current_raw_heart_rate["body"]["items"]) == _PAGE_SIZE
        assert raw_stream["item_count"] == _PAGE_SIZE
        assert structured_full_scan["item_count"] == _POINT_COUNT
        assert raw_full_scan["item_count"] == _TARGET_FIELD_ROWS
        assert structured_full_stream["item_count"] == _POINT_COUNT
        assert raw_full_stream["item_count"] == _TARGET_FIELD_ROWS
