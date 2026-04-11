from typing import Any
from unittest.mock import AsyncMock

import pytest
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from sqlalchemy.exc import SQLAlchemyError
from starlette.testclient import TestClient

import app.main as main_module

pytestmark = pytest.mark.smoke


class _EmptyAsyncIterator:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _QueryApiStub:
    async def query_stream(self, *args, **kwargs):
        return _EmptyAsyncIterator()


class _WriteApiStub:
    async def write(self, *args, **kwargs):
        return None


class _InfluxClientStub(InfluxDBClientAsync):
    def __init__(self) -> None:
        self._ping_mock = AsyncMock(return_value=True)
        self._close_mock = AsyncMock()
        self._write_api = _WriteApiStub()
        self._query_api = _QueryApiStub()

    async def ping(self) -> bool:
        return bool(await self._ping_mock())

    async def close(self):
        return await self._close_mock()

    def write_api(self, point_settings: Any = None) -> Any:
        return self._write_api

    def query_api(self, query_options: Any = None) -> Any:
        return self._query_api


class _PgConnectionStub:
    async def exec_driver_sql(self, statement: str) -> None:
        assert statement == "SELECT 1"


class _PgBeginScopeStub:
    def __init__(self, connection: _PgConnectionStub) -> None:
        self._connection = connection

    async def __aenter__(self) -> _PgConnectionStub:
        return self._connection

    async def __aexit__(self, _exc_type, _exc, _tb) -> bool:
        return False


class _PgConnectScopeStub:
    def __init__(
        self,
        connection: _PgConnectionStub,
        *,
        should_fail: bool = False,
        failure: Exception | None = None,
    ) -> None:
        self._connection = connection
        self._should_fail = should_fail
        self._failure = failure

    async def __aenter__(self) -> _PgConnectionStub:
        if self._should_fail:
            raise self._failure or SQLAlchemyError("postgres unavailable")
        return self._connection

    async def __aexit__(self, _exc_type, _exc, _tb) -> bool:
        return False


class _PgEngineStub:
    def __init__(self, *, fail_connect: bool = False, connect_failure: Exception | None = None) -> None:
        self.connection = _PgConnectionStub()
        self.dispose = AsyncMock()
        self._fail_connect = fail_connect
        self._connect_failure = connect_failure

    def begin(self) -> _PgBeginScopeStub:
        return _PgBeginScopeStub(self.connection)

    def connect(self) -> _PgConnectScopeStub:
        return _PgConnectScopeStub(
            self.connection,
            should_fail=self._fail_connect,
            failure=self._connect_failure,
        )


def test_lifespan_startup_shutdown_and_probes_without_dependency_overrides(monkeypatch) -> None:
    main_app = main_module.create_app()
    assert main_app.dependency_overrides == {}

    pg_engine_stub = _PgEngineStub()
    influx_client_stub = _InfluxClientStub()
    influx_probe = AsyncMock(return_value=True)

    monkeypatch.setattr(main_module, "pg_engine", pg_engine_stub)
    monkeypatch.setattr(main_module, "create_influx_client", lambda: influx_client_stub)
    monkeypatch.setattr(main_module, "_probe_influx_http", influx_probe)

    with TestClient(main_app) as test_client:
        assert main_app.dependency_overrides == {}

        live_response = test_client.get("/livez")
        assert live_response.status_code == 200, live_response.text
        assert live_response.json() == {"status": "healthy"}

        ready_response = test_client.get("/readyz")
        assert ready_response.status_code == 200, ready_response.text
        assert ready_response.json() == {
            "status": "healthy",
            "postgres": True,
            "influx": True,
        }

    pg_engine_stub.dispose.assert_awaited_once()
    influx_client_stub._close_mock.assert_awaited_once()

    assert main_app.dependency_overrides == {}


def test_readyz_returns_503_when_postgres_is_unavailable(monkeypatch) -> None:
    main_app = main_module.create_app()
    pg_engine_stub = _PgEngineStub(fail_connect=True)
    influx_client_stub = _InfluxClientStub()
    influx_probe = AsyncMock(return_value=True)

    monkeypatch.setattr(main_module, "pg_engine", pg_engine_stub)
    monkeypatch.setattr(main_module, "create_influx_client", lambda: influx_client_stub)
    monkeypatch.setattr(main_module, "_probe_influx_http", influx_probe)

    with TestClient(main_app) as test_client:
        response = test_client.get("/readyz")
        assert response.status_code == 503, response.text
        assert response.json() == {
            "status": "unhealthy",
            "postgres": False,
            "influx": True,
        }


def test_readyz_returns_503_when_postgres_connect_raises_oserror(monkeypatch) -> None:
    main_app = main_module.create_app()
    pg_engine_stub = _PgEngineStub(fail_connect=True, connect_failure=OSError("connection refused"))
    influx_client_stub = _InfluxClientStub()
    influx_probe = AsyncMock(return_value=True)

    monkeypatch.setattr(main_module, "pg_engine", pg_engine_stub)
    monkeypatch.setattr(main_module, "create_influx_client", lambda: influx_client_stub)
    monkeypatch.setattr(main_module, "_probe_influx_http", influx_probe)

    with TestClient(main_app) as test_client:
        response = test_client.get("/readyz")
        assert response.status_code == 503, response.text
        assert response.json() == {
            "status": "unhealthy",
            "postgres": False,
            "influx": True,
        }


def test_readyz_returns_503_when_influx_probe_fails(monkeypatch) -> None:
    main_app = main_module.create_app()
    pg_engine_stub = _PgEngineStub()
    influx_client_stub = _InfluxClientStub()
    influx_probe = AsyncMock(side_effect=[True, False])

    monkeypatch.setattr(main_module, "pg_engine", pg_engine_stub)
    monkeypatch.setattr(main_module, "create_influx_client", lambda: influx_client_stub)
    monkeypatch.setattr(main_module, "_probe_influx_http", influx_probe)

    with TestClient(main_app) as test_client:
        response = test_client.get("/readyz")
        assert response.status_code == 503, response.text
        assert response.json() == {
            "status": "unhealthy",
            "postgres": True,
            "influx": False,
        }


def test_readyz_returns_503_when_both_backends_are_unavailable(monkeypatch) -> None:
    main_app = main_module.create_app()
    pg_engine_stub = _PgEngineStub(fail_connect=True, connect_failure=OSError("connection refused"))
    influx_client_stub = _InfluxClientStub()
    influx_probe = AsyncMock(side_effect=[True, False])

    monkeypatch.setattr(main_module, "pg_engine", pg_engine_stub)
    monkeypatch.setattr(main_module, "create_influx_client", lambda: influx_client_stub)
    monkeypatch.setattr(main_module, "_probe_influx_http", influx_probe)

    with TestClient(main_app) as test_client:
        response = test_client.get("/readyz")
        assert response.status_code == 503, response.text
        assert response.json() == {
            "status": "unhealthy",
            "postgres": False,
            "influx": False,
        }
