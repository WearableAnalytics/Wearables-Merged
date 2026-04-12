from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from app.core.config import settings


def create_influx_client() -> InfluxDBClientAsync:
    """Create a new InfluxDB async client.

    Used by lifespan in main.py. Do **NOT** call directly in request handlers. Use DI via CurrentInfluxClient.
    """
    optional_kwargs = {
        key: value
        for key, value in (
            ("timeout", settings.INFLUX_TIMEOUT_MS),
            ("connection_pool_maxsize", settings.INFLUX_CONNECTION_POOL_MAXSIZE),
        )
        if value is not None
    }
    return InfluxDBClientAsync(
        url=settings.INFLUX_URL,
        token=settings.INFLUX_TOKEN,
        org=settings.INFLUX_ORG,
        enable_gzip=settings.INFLUX_ENABLE_GZIP,
        **optional_kwargs,
    )
