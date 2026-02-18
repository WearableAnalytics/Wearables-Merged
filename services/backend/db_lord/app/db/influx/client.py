from typing import NotRequired, TypedDict

from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from app.core.config import settings


class _InfluxClientKwargs(TypedDict):
    url: str
    token: str
    org: str
    enable_gzip: bool
    timeout: NotRequired[int]
    connection_pool_maxsize: NotRequired[int]


def create_influx_client() -> InfluxDBClientAsync:
    """Create a new InfluxDB async client.

    Used by lifespan in main.py. Do **NOT** call directly in request handlers. Use DI via CurrentInfluxClient.
    """
    client_kwargs: _InfluxClientKwargs = {
        "url": settings.INFLUX_URL,
        "token": settings.INFLUX_TOKEN,
        "org": settings.INFLUX_ORG,
        "enable_gzip": settings.INFLUX_ENABLE_GZIP,
    }
    if settings.INFLUX_TIMEOUT_MS is not None:
        client_kwargs["timeout"] = settings.INFLUX_TIMEOUT_MS
    if settings.INFLUX_CONNECTION_POOL_MAXSIZE is not None:
        client_kwargs["connection_pool_maxsize"] = settings.INFLUX_CONNECTION_POOL_MAXSIZE
    return InfluxDBClientAsync(**client_kwargs)
