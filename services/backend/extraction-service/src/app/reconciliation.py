"""Read-only source policies. Raw observations remain available through exports."""

from collections.abc import AsyncIterator
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Literal

from fastapi import HTTPException

from .db_lord_api import DbLordApi
from .fhir import default_mapping
from .points import patient_tag_filters, reading_key
from .schemas import TelemetryPoint

POLICY_VERSION = "source-selection/1"
MAX_RECORDS = 10_000
MAX_WINDOW = timedelta(days=31)
Mode = Literal["separate", "select", "priority"]


def metric_policy(measurement: str) -> str:
    for path in default_mapping().measurement.paths:
        for mapping in path.mappings or []:
            if mapping.fieldName == "codeCodingCodeZero" and any(x.key == measurement for x in mapping.map):
                return "samples" if path.path.endswith("instantaneous") else "sum-nonoverlapping-intervals"
    return "samples"


async def bounded_readings(
    api: DbLordApi,
    *,
    patient_id: str,
    measurement: str,
    start: datetime,
    end: datetime,
) -> list[TelemetryPoint]:
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Source policy times require explicit timezone offsets")
    if start >= end or end - start > MAX_WINDOW:
        raise HTTPException(422, "Use a nonempty source policy window of at most 31 days")
    records = {}
    scanned = 0
    for tags in patient_tag_filters(patient_id):
        stream: AsyncIterator[TelemetryPoint] = api.stream_telemetry(
            measurement=measurement,
            start=start,
            end=end,
            tags=tags,
        )
        async with aclosing(stream):
            async for point in stream:
                scanned += 1
                if point.patient_id != patient_id:
                    continue
                records.setdefault((point.timestamp, reading_key(point)), point)
                if len(records) > MAX_RECORDS or scanned > MAX_RECORDS * len(patient_tag_filters(patient_id)):
                    raise HTTPException(413, "Too many readings. Use a smaller time range")
    return sorted(records.values(), key=lambda point: point.timestamp)


def _summary(source: str, points: list[TelemetryPoint], policy: str, start: datetime, end: datetime) -> dict:
    first = points[0]
    summary = {
        "source_key": source,
        "platform": first.fields.get("source_platform"),
        "writer_id": first.fields.get("source_id"),
        "name": first.fields.get("source_name"),
        "measuring_device_id": first.fields.get("source_device_id"),
        "record_count": len(points),
        "status": "samples",
        "value": None,
        "unit": None,
        "reported_interval_seconds": 0.0,
    }
    if policy == "samples":
        return summary
    if source == "legacy":
        return {**summary, "status": "source-unknown"}
    intervals = []
    units = set()
    source_records = set()
    for point in points:
        record_id = point.fields.get("source_record_id")
        if record_id and record_id in source_records:
            return {**summary, "status": "conflicting-source-record"}
        if record_id:
            source_records.add(record_id)
        try:
            if isinstance(point.fields["value"], bool):
                return {**summary, "status": "invalid-record"}
            begin = datetime.fromisoformat(point.fields["period_start"].replace("Z", "+00:00"))
            finish = datetime.fromisoformat(point.fields["period_end"].replace("Z", "+00:00"))
            value = float(point.fields["value"])
            unit = point.tags["valueUnit"]
        except (KeyError, TypeError, ValueError):
            return {**summary, "status": "incomplete-interval-or-unit"}
        if begin.tzinfo is None or finish.tzinfo is None or not isfinite(value) or value < 0 or finish < begin:
            return {**summary, "status": "invalid-record"}
        if begin < start or finish > end:
            return {**summary, "status": "interval-crosses-window"}
        intervals.append((begin.astimezone(UTC), finish.astimezone(UTC), value))
        units.add(unit)
    if len(units) != 1:
        return {**summary, "status": "mixed-units"}
    last_end = None
    total = 0.0
    covered_seconds = 0.0
    for begin, finish, value in sorted(intervals):
        if last_end is not None and begin < last_end:
            return {**summary, "status": "overlapping-records"}
        last_end = finish
        total += value
        covered_seconds += (finish - begin).total_seconds()
    return {
        **summary,
        "status": "nonoverlapping-records",
        "value": total,
        "unit": next(iter(units)),
        "reported_interval_seconds": covered_seconds,
    }


def reconcile(
    points: list[TelemetryPoint],
    *,
    measurement: str,
    start: datetime,
    end: datetime,
    mode: Mode = "separate",
    source_key: str | None = None,
    priorities: list[str] | None = None,
) -> dict:
    if mode == "select" and not source_key:
        raise HTTPException(422, "select mode requires source_key")
    if mode == "priority" and not priorities:
        raise HTTPException(422, "priority mode requires an ordered source_priority list")
    if mode != "select" and source_key is not None:
        raise HTTPException(422, "source_key is only valid with select mode")
    if mode != "priority" and priorities:
        raise HTTPException(422, "source_priority is only valid with priority mode")
    grouped: dict[str, list[TelemetryPoint]] = {}
    for point in points:
        grouped.setdefault(point.tags.get("source-key", "legacy"), []).append(point)
    policy = metric_policy(measurement)
    summaries = [_summary(source, readings, policy, start, end) for source, readings in sorted(grouped.items())]
    selected = source_key if mode == "select" else None
    if mode == "priority":
        selected = next((key for key in priorities if key in grouped), None)
    if selected is not None and selected not in grouped:
        raise HTTPException(404, "The selected source has no readings in this window")
    chosen = next((summary for summary in summaries if summary["source_key"] == selected), None)
    return {
        "policy_version": POLICY_VERSION,
        "measurement": measurement,
        "mode": mode,
        "metric_policy": policy,
        "start": start,
        "end": end,
        "selected_source": selected,
        "sources": summaries,
        "selection": chosen,
        "excluded_sources": [key for key in sorted(grouped) if selected is not None and key != selected],
        "scope": "returned records in the requested window; source gaps are not filled from another source",
    }
