"""Reading telemetry for the export endpoints: patient filtering, merging and de-duplication."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from datetime import UTC, datetime

import httpx

from .db_lord_api import DbLordApi
from .schemas import INGESTION_FIELDS, PATIENT_REFERENCE_PREFIX, MeasurementPage, MeasurementPoint, TelemetryPoint
from .settings import settings


def patient_tag_filters(patient_id: str) -> list[dict[str, str]]:
    """Tag filters that together find all points of one patient.

    Points carry `device-id`, `device-id-reference`, or both, so both are queried and merged.
    """
    return [{"device-id": patient_id}, {"device-id-reference": f"{PATIENT_REFERENCE_PREFIX}{patient_id}"}]


def reading_key(point: TelemetryPoint) -> tuple:
    """Identity of a reading, ignoring how it was ingested.

    The same reading re-sent by the app is stored once per Telegraf pod that ingested it
    (different `host` tag and `t_ingested`), so those are left out of the key.
    """
    fields = {k: v for k, v in point.fields.items() if k not in INGESTION_FIELDS}
    return (point.measurement, point.patient_id, json.dumps(fields, sort_keys=True, default=str))


async def dedupe(points: AsyncIterator[TelemetryPoint]) -> AsyncIterator[TelemetryPoint]:
    """Drop repeated readings. Expects input sorted by timestamp, so copies are adjacent."""
    current_ts: datetime | None = None
    seen: set[tuple] = set()
    async for point in points:
        if point.timestamp != current_ts:
            current_ts = point.timestamp
            seen = set()
        key = reading_key(point)
        if key in seen:
            continue
        seen.add(key)
        yield point


async def _patient_window(
    api: DbLordApi, *, measurement: str | None, start: datetime, end: datetime, patient_id: str
) -> list[TelemetryPoint]:
    """All points of one patient in [start, end), newest first."""
    points: list[TelemetryPoint] = []
    for tags in patient_tag_filters(patient_id):
        points.extend(await _read_all(api, measurement=measurement, start=start, end=end, tags=tags))
    return sorted(points, key=lambda p: p.timestamp, reverse=True)


async def _read_all(api: DbLordApi, *, attempts: int = 3, **query) -> list[TelemetryPoint]:
    """Read one bounded query completely. Retried, since a long export makes many requests
    and a pooled keep-alive connection can be closed by db_lord just as it is reused."""
    for attempt in range(attempts):
        try:
            async with aclosing(api.stream_telemetry(**query)) as stream:
                return [p async for p in stream]
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            if attempt == attempts - 1:
                raise
    raise AssertionError("unreachable")


async def _patient_points(
    api: DbLordApi, *, measurement: str | None, start: datetime, end: datetime | None, patient_id: str
) -> AsyncIterator[TelemetryPoint]:
    """Walks back from `end` in windows and queries both patient tags per window.

    The two tag queries are run one after the other per window rather than as two
    concurrent streams, so only one window of one patient is held in memory.
    """
    window_end = end or datetime.now(UTC)
    while window_end > start:
        window_start = max(start, window_end - settings.patient_window)
        for point in await _patient_window(
            api, measurement=measurement, start=window_start, end=window_end, patient_id=patient_id
        ):
            yield point
        window_end = window_start


async def iter_readings(
    api: DbLordApi,
    *,
    measurement: str | None,
    start: datetime,
    end: datetime | None,
    patient_id: str | None,
) -> AsyncIterator[TelemetryPoint]:
    """All matching readings, newest first, without duplicates."""
    if patient_id:
        points = _patient_points(api, measurement=measurement, start=start, end=end, patient_id=patient_id)
    else:
        points = api.stream_telemetry(measurement=measurement, start=start, end=end)

    async with aclosing(points), aclosing(dedupe(points)) as readings:
        async for point in readings:
            yield point


async def read_page(readings: AsyncIterator[TelemetryPoint], limit: int) -> MeasurementPage:
    """Take at least `limit` readings, completing the last timestamp so `next_end` can be exclusive."""
    items: list[MeasurementPoint] = []
    has_more = False
    async for point in readings:
        if len(items) >= limit and point.timestamp != items[-1].timestamp:
            has_more = True
            break
        items.append(MeasurementPoint.from_telemetry(point))
    return MeasurementPage(
        items=items,
        has_more=has_more,
        next_end=items[-1].timestamp if has_more else None,
    )
