from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

from app.core.config import settings

client = InfluxDBClientAsync(url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG)
