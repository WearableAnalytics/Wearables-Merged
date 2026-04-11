from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

from app.core.config import settings
from tests.helpers.common import empty_async_iterator

_INTEGRATION_INFLUX_ADMIN_TOKEN = "integration-admin-token"
_INFLUXDB_PORT = 8086


class _MockWriteApi:
    def __init__(self) -> None:
        self.write = AsyncMock(return_value=None)


class _MockQueryApi:
    async def query_stream(self, *args, **kwargs):
        return empty_async_iterator()


class MockInfluxClient:
    def __init__(self) -> None:
        self._write_api = _MockWriteApi()
        self._query_api = _MockQueryApi()
        self.write_api = Mock(return_value=self._write_api)
        self.query_api = Mock(return_value=self._query_api)


class InfluxDb2DockerContainer(DockerContainer):
    def __init__(self) -> None:
        super().__init__("influxdb:2.7")
        self.with_exposed_ports(_INFLUXDB_PORT)
        self.with_env("DOCKER_INFLUXDB_INIT_MODE", "setup")
        self.with_env("DOCKER_INFLUXDB_INIT_ADMIN_TOKEN", _INTEGRATION_INFLUX_ADMIN_TOKEN)
        self.with_env("DOCKER_INFLUXDB_INIT_USERNAME", "integration-admin")
        self.with_env("DOCKER_INFLUXDB_INIT_PASSWORD", "integration-password")
        self.with_env("DOCKER_INFLUXDB_INIT_ORG", settings.INFLUX_ORG)
        self.with_env("DOCKER_INFLUXDB_INIT_BUCKET", settings.INFLUX_BUCKET)
        self.waiting_for(HttpWaitStrategy(_INFLUXDB_PORT, "/health").for_status_code(200))

    def get_url(self) -> str:
        host = self.get_container_host_ip()
        port = self.get_exposed_port(_INFLUXDB_PORT)
        return f"http://{host}:{port}"


@pytest.fixture(scope="session")
def influxdb_container():
    """Start an InfluxDB container for integration tests."""
    with InfluxDb2DockerContainer() as influxdb:
        yield influxdb


@pytest.fixture
async def integration_influx_client(influxdb_container):
    """Create InfluxDB async client connected to real container."""
    from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync

    url = influxdb_container.get_url()
    token = _INTEGRATION_INFLUX_ADMIN_TOKEN
    org = settings.INFLUX_ORG
    bucket = settings.INFLUX_BUCKET

    client = InfluxDBClientAsync(url=url, token=token, org=org, timeout=30_000)
    if not await client.ping():
        await client.close()
        raise RuntimeError("Failed to ping integration InfluxDB container")

    start = datetime(1970, 1, 1, tzinfo=UTC)
    stop = datetime(2100, 1, 1, tzinfo=UTC)
    await client.delete_api().delete(start=start, stop=stop, predicate="", bucket=bucket, org=org)

    yield client

    await client.delete_api().delete(start=start, stop=stop, predicate="", bucket=bucket, org=org)
    await client.close()


@pytest.fixture
def integration_telemetry_repo(integration_influx_client):
    """Create TelemetryRepo with real InfluxDB client."""
    from app.db.influx.telemetry import TelemetryRepo

    return TelemetryRepo(integration_influx_client)


@pytest.fixture
def mock_influx_client() -> MockInfluxClient:
    """Create a minimal InfluxDB client stub for unit tests."""
    return MockInfluxClient()


@pytest.fixture
def mock_telemetry_repo(mock_influx_client):
    """Create a TelemetryRepo with mocked client."""
    from app.db.influx.telemetry import TelemetryRepo

    return TelemetryRepo(mock_influx_client)
