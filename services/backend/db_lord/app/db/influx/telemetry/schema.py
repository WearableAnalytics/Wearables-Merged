"""
Schema discovery and caching for Graphql
"""

import asyncio
from datetime import UTC, datetime

from cachetools import TTLCache
from influxdb_client.client.query_api_async import QueryApiAsync

from app.core.config import settings
from app.telemetry.types import MeasurementSchema

type FluxParams = dict[str, object]


class TelemetrySchemaStore:
    def __init__(self, query_api: QueryApiAsync):
        self._query_api = query_api
        self._schema_lookback = settings.INFLUX_SCHEMA_LOOKBACK
        self._schema_cache: TTLCache[tuple[str, str], MeasurementSchema] = TTLCache(
            maxsize=max(1, settings.INFLUX_SCHEMA_CACHE_MAX_MEASUREMENTS),
            ttl=max(1, settings.INFLUX_SCHEMA_CACHE_TTL_SECONDS),
        )
        self._schema_cache_lock = asyncio.Lock()

    async def list_measurements(self, bucket: str) -> list[str]:
        start_expr, start_params = self._schema_start_expr_and_params()
        flux = f"""
        import "influxdata/influxdb/schema"
        schema.measurements(
        bucket: bucket_param,
        start: {start_expr},
        )"""
        params = {"bucket_param": bucket, **start_params}
        return sorted(await self._collect_string_values(flux, params))

    async def get_measurement_schema(self, measurement: str, *, bucket: str) -> MeasurementSchema:
        cache_key = (bucket, measurement)
        cached = self._schema_cache.get(cache_key)
        if cached is not None:
            return cached

        async with self._schema_cache_lock:
            cached = self._schema_cache.get(cache_key)
            if cached is not None:
                return cached

            tag_keys, field_keys = await asyncio.gather(
                self._get_measurement_schema_keys(measurement, "measurementTagKeys", bucket),
                self._get_measurement_schema_keys(measurement, "measurementFieldKeys", bucket),
            )

            schema = MeasurementSchema(
                tuple(sorted(tag_keys)),
                frozenset(field_keys),
            )
            self._schema_cache[cache_key] = schema
            return schema

    async def get_measurement_tag_values(
        self,
        measurement: str,
        tag_key: str,
        bucket: str,
        limit: int | None = 500,
    ) -> list[str]:
        normalized_tag_key = tag_key.strip()
        if not normalized_tag_key:
            raise ValueError("tag_key must be a non-empty string")
        if limit is not None and limit < 1:
            raise ValueError("limit must be >= 1 when provided")

        start_expr, start_params = self._schema_start_expr_and_params()
        flux = f"""
        import "influxdata/influxdb/schema"
        schema.measurementTagValues(
        bucket: bucket_param,
        measurement: measurement_param,
        tag: tag_param,
        start: {start_expr},
        )"""

        params: FluxParams = {
            "bucket_param": bucket,
            "measurement_param": measurement,
            "tag_param": normalized_tag_key,
            **start_params,
        }

        if limit is not None:
            flux = f"{flux}\n|> limit(n: limit_param)"
            params["limit_param"] = limit

        return sorted(await self._collect_string_values(flux, params))

    async def _collect_string_values(
        self,
        flux: str,
        params: FluxParams,
        exclude_private: bool = False,
    ) -> set[str]:
        stream = await self._query_api.query_stream(flux, params=params)
        values: set[str] = set()
        async for record in stream:
            value = record.values.get("_value")
            if not isinstance(value, str) or not value:
                continue
            if exclude_private and value.startswith("_"):
                continue
            values.add(value)
        return values

    async def _get_measurement_schema_keys(
        self,
        measurement: str,
        schema_fn: str,
        bucket: str,
    ) -> set[str]:
        start_expr, start_params = self._schema_start_expr_and_params()
        flux = f"""
        import "influxdata/influxdb/schema"
        schema.{schema_fn}(
        bucket: bucket_param,
        measurement: measurement_param,
        start: {start_expr},
        )"""
        params: FluxParams = {
            "bucket_param": bucket,
            "measurement_param": measurement,
            **start_params,
        }
        return await self._collect_string_values(flux, params, True)

    def _schema_start_expr_and_params(self) -> tuple[str, dict[str, object]]:
        if self._schema_lookback <= 0:
            return "schema_start_param", {"schema_start_param": datetime.fromtimestamp(0, UTC)}
        return f"-{self._schema_lookback}s", {}
