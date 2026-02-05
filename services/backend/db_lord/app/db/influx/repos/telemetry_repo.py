from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write.point import Point

from app.core.config import settings


# TODO: fix unsafe flux string interpolation
@dataclass(frozen=True)
class TelemetryPage:
    items: list[dict[str, Any]]
    next_cursor: str | None


class TelemetryRepo:
    """Repository for writing telemetry points.

    This repo now requires callers to provide point data as dicts. Each dict
    must include at minimum `measurement` and `timestamp` keys and may include
    `tags` and `fields` dictionaries.
    """

    # idk how many we should allow here??
    MAX_PAGE_SIZE = 50_000

    def __init__(self, client: InfluxDBClientAsync):
        self._client = client

    @property
    def _write_api(self):
        return self._client.write_api()

    @property
    def _query_api(self):
        return self._client.query_api()

    async def write_point(self, point: dict[str, Any]) -> None:
        """Write a single point represented as a dict.

        Dict format:
        {
            "measurement": "mname",
            "timestamp": datetime(...),
            "tags": {"tag1": "v1", ...},
            "fields": {"field1": 1.23, ...}
        }

        `measurement` and `timestamp` are required.
        """
        pt = self._build_point(point)
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=pt)

    async def write_batch(self, points: Iterable[dict[str, Any]]) -> None:
        """Write multiple points; each item must be a dict in the same format
        as `write_point`.
        """
        prepared_points = [self._build_point(p) for p in points]
        if not prepared_points:
            return
        await self._write_api.write(bucket=settings.INFLUX_BUCKET, record=prepared_points)

    async def get_points(
        self,
        measurement: str,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: dict[str, str] | None = None,
        page_size: int = 100,
        cursor: str | None = None,
    ) -> TelemetryPage:
        if not isinstance(measurement, str) or not measurement:
            raise ValueError("measurement must be a non-empty string")

        if page_size < 1:
            raise ValueError("page_size must be at least 1")
        if page_size > self.MAX_PAGE_SIZE:
            raise ValueError(f"page_size cannot exceed {self.MAX_PAGE_SIZE}. Use cursor pagination.")

        if start is None:
            start = datetime.now(UTC) - timedelta(hours=24)

        start_utc = self._to_utc(start)
        stop_utc = self._to_utc(end) if end else datetime.now(UTC)

        if start_utc > stop_utc:
            raise ValueError("start must be <= end")
        # Unsafe
        bucket_lit = self._flux_str_literal(settings.INFLUX_BUCKET)
        meas_lit = self._flux_str_literal(measurement)

        flux = f"""from(bucket: {bucket_lit})
        |> range(start: time(v: "{start_utc.isoformat()}"), stop: time(v: "{stop_utc.isoformat()}"))
        |> filter(fn: (r) => r["_measurement"] == {meas_lit})
        """

        # Dynamic Tag Filtering
        if tags:
            for k, v in tags.items():
                k_lit = self._flux_str_literal(k)
                v_lit = self._flux_str_literal(str(v))
                flux += f"|> filter(fn: (r) => r[{k_lit}] == {v_lit})\n"

        # Cursor Pagination
        if cursor:
            # Unsafe
            flux += f'|> filter(fn: (r) => r["_time"] < time(v: "{cursor}"))\n'

        # Pivot + Group + Sort + Limit
        flux += f"""|> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> group(columns: [])
        |> sort(columns: ["_time"], desc: true)
        |> limit(n: {page_size})
        """

        stream = await self._query_api.query_stream(flux)

        items: list[dict[str, Any]] = []
        async for record in stream:
            vals = record.values
            ts = vals.get("_time")

            clean_props = {
                k: v
                for k, v in vals.items()
                if k not in ("result", "table", "_start", "_stop", "_time", "_measurement") and v is not None
            }

            items.append({"timestamp": ts, "measurement": vals.get("_measurement"), **clean_props})

        next_cursor = None
        if len(items) == page_size:
            last_ts = items[-1].get("timestamp")
            if isinstance(last_ts, datetime):
                next_cursor = last_ts.isoformat()

        return TelemetryPage(items=items, next_cursor=next_cursor)

    def _build_point(self, data: dict[str, Any]) -> Point:
        if not isinstance(data, dict):
            raise TypeError("point must be a dict")

        measurement = data.get("measurement")
        if not isinstance(measurement, str) or not measurement:
            raise ValueError("point must include non-empty 'measurement' (str)")

        ts = data.get("timestamp")
        if not isinstance(ts, datetime):
            raise ValueError("point must include 'timestamp' (datetime)")
        ts = self._to_utc(ts)

        fields = data.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ValueError("point must include non-empty 'fields' (dict)")

        tags = data.get("tags") or {}
        if not isinstance(tags, dict):
            raise ValueError("'tags' must be a dict if provided")

        pt = Point(measurement).time(ts)

        for k, v in tags.items():
            pt.tag(str(k), str(v))

        field_count = 0
        for k, v in fields.items():
            if v is None:
                continue
            pt.field(str(k), v)
            field_count += 1

        if field_count == 0:
            raise ValueError("Point must contain at least one non-None field")

        return pt

    @staticmethod
    def _to_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.astimezone(UTC)
        return dt.astimezone(UTC)

    @staticmethod
    def _flux_str_literal(s: str) -> str:
        """Escape a string for use as a Flux string literal."""
        s = s.replace("\\", "\\\\")
        s = s.replace('"', '\\"')
        s = s.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
        s = s.replace("${", "\\${")
        return f'"{s}"'
