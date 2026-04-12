import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid7

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.dependencies import get_graphql_context
from app.api.routers.graphql import WearablesGraphQLRouter
from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import Loaders
from app.graphql.schema import schema
from app.telemetry.types import MeasurementSchema, StructuredTelemetryItem, TelemetryTags, TelemetryWindowResult


class _SessionScopeStub:
    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, _exc_type, _exc, _tb) -> bool:
        return False


class _SessionFactoryStub:
    def __call__(self) -> _SessionScopeStub:
        return _SessionScopeStub()


class _TelemetryServiceStub:
    def resolve_bucket(self, bucket: str | None) -> str:
        return "medical_data" if bucket is None else bucket

    async def list_measurements(self, *, bucket: str | None = None) -> list[str]:
        return ["sensor_readings"]

    async def describe_measurement(self, measurement: str, *, bucket: str | None = None) -> MeasurementSchema:
        return MeasurementSchema(tag_keys=("patient_id",), field_keys=frozenset({"heart_rate"}))

    async def get_measurement_tag_values(
        self,
        measurement: str,
        tag_key: str,
        *,
        limit: int | None = 500,
        bucket: str | None = None,
    ) -> list[str]:
        return ["patient-1"] if tag_key == "patient_id" else []

    async def read_window(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int | None = 100,
        bucket: str | None = None,
    ) -> TelemetryWindowResult[StructuredTelemetryItem]:
        return TelemetryWindowResult[StructuredTelemetryItem](items=[], has_more=False, next_end=None)

    async def stream_structured(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        bucket: str | None = None,
    ):
        assert measurement == "sensor_readings"
        assert limit == 2
        assert tags == {"patient_id": ["patient-1"]}

        now_utc = datetime.now(UTC).replace(microsecond=0)
        dot_dependency_file_id = str(uuid7())
        for offset, value in ((0, 71), (1, 72)):
            yield {
                "timestamp": now_utc + timedelta(seconds=offset),
                "measurement": "sensor_readings",
                "tags": {
                    "patient_id": "patient-1",
                    "device_id": "device-1",
                    "wearable_id": "wearable-1",
                    "case_id": "case-1",
                    "mapping_id": "mapping-1",
                    "context_id": "context-1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                },
                "fields": {"heart_rate": value},
            }

    async def stream_raw(
        self,
        measurement: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        tags: TelemetryTags | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        bucket: str | None = None,
    ):
        assert measurement == "sensor_readings"
        assert limit == 2
        assert tags == {"patient_id": ["patient-1"]}

        now_utc = datetime.now(UTC).replace(microsecond=0)
        dot_dependency_file_id = str(uuid7())
        for offset, value in ((0, 71), (1, 72)):
            yield {
                "timestamp": now_utc + timedelta(seconds=offset),
                "measurement": "sensor_readings",
                "field": "heart_rate",
                "value": value,
                "tags": {
                    "patient_id": "patient-1",
                    "device_id": "device-1",
                    "wearable_id": "wearable-1",
                    "case_id": "case-1",
                    "mapping_id": "mapping-1",
                    "context_id": "context-1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                },
            }


async def _graphql_context_override() -> GraphQLContext:
    db_semaphore = asyncio.Semaphore(2)
    session_factory = cast(Any, _SessionFactoryStub())
    return GraphQLContext(
        session_factory=session_factory,
        db_semaphore=db_semaphore,
        loaders=Loaders(session_factory, db_semaphore),
        telemetry_service=cast(Any, _TelemetryServiceStub()),
    )


def _build_graphql_test_app(
    *,
    allow_queries_via_get: bool = True,
    subscription_protocols: tuple[str, ...] = ("graphql-transport-ws",),
    keep_alive: bool = True,
    keep_alive_interval: float = 15.0,
) -> FastAPI:
    app = FastAPI()
    app.include_router(
        WearablesGraphQLRouter(
            schema,
            context_getter=get_graphql_context,
            allow_queries_via_get=allow_queries_via_get,
            subscription_protocols=subscription_protocols,
            keep_alive=keep_alive,
            keep_alive_interval=keep_alive_interval,
        ),
        prefix="/graphql",
    )
    app.dependency_overrides[get_graphql_context] = _graphql_context_override
    return app


def test_graphql_http_transport_post_success() -> None:
    app = _build_graphql_test_app()

    with TestClient(app) as client:
        response = client.post("/graphql", json={"query": "query { __typename }"})

    assert response.status_code == 200
    assert response.json() == {"data": {"__typename": "Query"}}


def test_graphql_http_transport_post_graphql_error_payload() -> None:
    app = _build_graphql_test_app()

    with TestClient(app) as client:
        response = client.post("/graphql", json={"query": "query { unknownField }"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] is None
    assert payload["errors"]


def test_graphql_subscription_transport_over_websocket() -> None:
    app = _build_graphql_test_app()

    subscription = """
        subscription StreamTelemetry($measurement: String!) {
                telemetryStream(
                    query: {
                        measurement: $measurement
                        tags: [{ key: "patient_id", match: { value: "patient-1" } }]
                        limit: 2
                    }
                ) {
                measurement
                tags
                fields
            }
        }
    """

    with (
        TestClient(app) as client,
        client.websocket_connect("/graphql", subprotocols=["graphql-transport-ws"]) as websocket,
    ):
        websocket.send_json({"type": "connection_init"})
        ack = websocket.receive_json()
        assert ack["type"] == "connection_ack"

        websocket.send_json(
            {
                "id": "telemetry-sub",
                "type": "subscribe",
                "payload": {
                    "query": subscription,
                    "variables": {"measurement": "sensor_readings"},
                },
            }
        )

        payloads: list[dict[str, Any]] = []
        while True:
            message = websocket.receive_json()
            if message["type"] == "next":
                payloads.append(message["payload"]["data"]["telemetryStream"])
                continue

            assert message["type"] == "complete"
            assert message["id"] == "telemetry-sub"
            break

    assert len(payloads) == 2
    assert payloads[0]["measurement"] == "sensor_readings"
    assert payloads[1]["measurement"] == "sensor_readings"
    assert payloads[0]["tags"]["patient_id"] == "patient-1"
    assert payloads[1]["tags"]["patient_id"] == "patient-1"
    assert payloads[0]["tags"]["dot_dependency_file_id"]
    assert payloads[1]["tags"]["dot_dependency_file_id"]
    assert payloads[0]["fields"]["heart_rate"] == 71
    assert payloads[1]["fields"]["heart_rate"] == 72


def test_graphql_raw_subscription_transport_over_websocket() -> None:
    app = _build_graphql_test_app()

    subscription = """
        subscription StreamRawTelemetry($measurement: String!) {
            telemetryRawStream(
                query: {
                    measurement: $measurement
                    tags: [{ key: "patient_id", match: { value: "patient-1" } }]
                    limit: 2
                }
            ) {
                measurement
                field
                value
                tags
            }
        }
    """

    with (
        TestClient(app) as client,
        client.websocket_connect("/graphql", subprotocols=["graphql-transport-ws"]) as websocket,
    ):
        websocket.send_json({"type": "connection_init"})
        ack = websocket.receive_json()
        assert ack["type"] == "connection_ack"

        websocket.send_json(
            {
                "id": "telemetry-raw-sub",
                "type": "subscribe",
                "payload": {
                    "query": subscription,
                    "variables": {"measurement": "sensor_readings"},
                },
            }
        )

        payloads: list[dict[str, Any]] = []
        while True:
            message = websocket.receive_json()
            if message["type"] == "next":
                payloads.append(message["payload"]["data"]["telemetryRawStream"])
                continue

            assert message["type"] == "complete"
            assert message["id"] == "telemetry-raw-sub"
            break

    assert len(payloads) == 2
    assert payloads[0]["measurement"] == "sensor_readings"
    assert payloads[1]["measurement"] == "sensor_readings"
    assert payloads[0]["field"] == "heart_rate"
    assert payloads[1]["field"] == "heart_rate"
    assert payloads[0]["value"] == 71
    assert payloads[1]["value"] == 72
    assert payloads[0]["tags"]["patient_id"] == "patient-1"
    assert payloads[1]["tags"]["patient_id"] == "patient-1"
    assert payloads[0]["tags"]["dot_dependency_file_id"]
    assert payloads[1]["tags"]["dot_dependency_file_id"]


def test_graphql_subscription_transport_rejects_legacy_protocol() -> None:
    app = _build_graphql_test_app(subscription_protocols=("graphql-transport-ws",))

    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/graphql", subprotocols=["graphql-ws"]) as websocket,
    ):
        websocket.send_json({"type": "connection_init"})
        websocket.receive_json()


def test_graphql_http_get_query_disabled() -> None:
    app = _build_graphql_test_app(allow_queries_via_get=False)

    with TestClient(app) as client:
        response = client.get("/graphql", params={"query": "query { __typename }"})

    assert response.status_code >= 400
    assert response.status_code != 200
