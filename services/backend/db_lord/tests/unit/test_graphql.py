"""
GraphQL API tests.
- Basic queries with pagination
- Nested relationship resolution via DataLoaders
- Filter application with boolean logic
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid7

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry.relay.utils import to_base64

from app.db.influx.telemetry import TelemetryRepo
from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import Loaders
from app.graphql.schema import schema
from app.services.telemetry_service import TelemetryService
from tests.helpers.common import empty_async_iterator
from tests.helpers.common import extract_tag_param_values as _extract_tag_param_values
from tests.helpers.common import relay_global_id as _relay_global_id
from tests.helpers.common import relay_node_id as _relay_node_id

pytestmark = pytest.mark.anyio


def _uuid_str() -> str:
    return str(uuid7())


@pytest.fixture
def graphql_context_factory(db_session: AsyncSession, mock_influx_client) -> Callable[[], GraphQLContext]:
    bind = db_session.bind
    if bind is None:
        raise RuntimeError("Test db_session is not bound to an engine.")

    session_factory = async_sessionmaker(
        bind,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    db_semaphore = asyncio.Semaphore(1)

    def _build_context() -> GraphQLContext:
        return GraphQLContext(
            session_factory=session_factory,
            db_semaphore=db_semaphore,
            loaders=Loaders(session_factory, db_semaphore),
            telemetry_service=TelemetryService(TelemetryRepo(mock_influx_client)),
        )

    return _build_context


@pytest.fixture
def graphql_execute(
    graphql_context_factory: Callable[[], GraphQLContext],
) -> Callable[[str], Awaitable[dict[str, Any]]]:
    async def _execute(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await schema.execute(query, variable_values=variables, context_value=graphql_context_factory())
        assert result.errors is None, result.errors
        assert result.data is not None
        return result.data

    return _execute


@pytest.fixture
def graphql_execute_raw(
    graphql_context_factory: Callable[[], GraphQLContext],
) -> Callable[[str, dict[str, Any] | None], Awaitable[Any]]:
    async def _execute(query: str, variables: dict[str, Any] | None = None):
        return await schema.execute(query, variable_values=variables, context_value=graphql_context_factory())

    return _execute


class TestGraphQLPatientQueries:
    """Test Patient queries and pagination."""

    async def test_patients_query_returns_connection(self, graphql_execute, patient_factory):
        """Test basic patients query returns Relay-style connection."""
        # Create test patients
        await patient_factory(name="Alice Smith")
        await patient_factory(name="Bob Jones")

        query = """
            query {
                patients(first: 10) {
                    edges {
                        cursor
                        node {
                            id
                            name
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        """

        data = await graphql_execute(query)
        patients = data["patients"]
        assert len(patients["edges"]) == 2
        assert patients["pageInfo"]["hasNextPage"] is False

        # Verify node structure
        names = {edge["node"]["name"] for edge in patients["edges"]}
        assert "Alice Smith" in names
        assert "Bob Jones" in names

    async def test_patients_pagination_cursor(self, graphql_execute, patient_factory):
        """Test cursor-based pagination works correctly."""
        # Create 3 patients
        await patient_factory(name="Patient 1")
        await patient_factory(name="Patient 2")
        await patient_factory(name="Patient 3")

        # First page - get only 2
        query = """
            query {
                patients(first: 2) {
                    edges {
                        cursor
                        node { name }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        """

        data = await graphql_execute(query)
        first_page = data["patients"]
        assert len(first_page["edges"]) == 2
        assert first_page["pageInfo"]["hasNextPage"] is True
        end_cursor = first_page["pageInfo"]["endCursor"]

        # Second page using cursor
        query = f"""
            query {{
                patients(first: 2, after: "{end_cursor}") {{
                    edges {{
                        node {{ name }}
                    }}
                    pageInfo {{
                        hasNextPage
                    }}
                }}
            }}
        """

        data = await graphql_execute(query)
        second_page = data["patients"]
        assert len(second_page["edges"]) == 1  # Only 1 remaining
        assert second_page["pageInfo"]["hasNextPage"] is False


class TestGraphQLCursorValidation:
    async def test_cursor_rejects_malformed_base64(self, graphql_execute_raw, patient_factory):
        await patient_factory(name="Cursor malformed base64")
        query = """
            query($after: String!) {
                patients(first: 1, after: $after) {
                    edges { node { id } }
                }
            }
        """
        result = await graphql_execute_raw(query, {"after": "not-a-valid-cursor"})
        assert result.errors is not None
        assert "Argument 'after'" in result.errors[0].message
        assert "non-existing value" in result.errors[0].message

    async def test_cursor_rejects_wrong_prefix(self, graphql_execute_raw, patient_factory):
        await patient_factory(name="Cursor wrong prefix")
        wrong_prefix_cursor = to_base64("wrong-prefix", str(uuid7()))
        query = """
            query($after: String!) {
                patients(first: 1, after: $after) {
                    edges { node { id } }
                }
            }
        """
        result = await graphql_execute_raw(query, {"after": wrong_prefix_cursor})
        assert result.errors is not None
        assert "Argument 'after'" in result.errors[0].message
        assert "non-existing value" in result.errors[0].message

    async def test_cursor_rejects_invalid_uuid_payload(self, graphql_execute_raw, patient_factory):
        await patient_factory(name="Cursor invalid uuid payload")
        invalid_uuid_cursor = to_base64("keyset", "not-a-uuid")
        query = """
            query($after: String!) {
                patients(first: 1, after: $after) {
                    edges { node { id } }
                }
            }
        """
        result = await graphql_execute_raw(query, {"after": invalid_uuid_cursor})
        assert result.errors is not None
        assert "Argument 'after'" in result.errors[0].message
        assert "non-existing value" in result.errors[0].message

    async def test_connection_rejects_first_and_last_together(self, graphql_execute_raw, patient_factory):
        await patient_factory(name="Cursor first+last invalid")
        query = """
            query {
                patients(first: 1, last: 1) {
                    edges { node { id } }
                }
            }
        """
        result = await graphql_execute_raw(query)
        assert result.errors is not None
        assert "Arguments 'first' and 'last'" in result.errors[0].message
        assert "cannot both be provided" in result.errors[0].message

    @pytest.mark.parametrize(
        ("arg_name", "arg_value"),
        [
            ("first", -1),
            ("last", -1),
        ],
    )
    async def test_connection_rejects_negative_window_sizes(
        self, graphql_execute_raw, patient_factory, arg_name: str, arg_value: int
    ):
        await patient_factory(name=f"Cursor negative {arg_name}")
        query = f"""
            query($value: Int!) {{
                patients({arg_name}: $value) {{
                    edges {{ node {{ id }} }}
                }}
            }}
        """
        result = await graphql_execute_raw(query, {"value": arg_value})
        assert result.errors is not None
        assert f"Argument '{arg_name}'" in result.errors[0].message
        assert "non-negative integer" in result.errors[0].message

    async def test_connection_first_zero_returns_empty_edges_with_has_next_page(self, graphql_execute, patient_factory):
        await patient_factory(name="Cursor first zero 1")
        await patient_factory(name="Cursor first zero 2")

        query = """
            query {
                patients(first: 0) {
                    edges { node { id } }
                    pageInfo { hasNextPage hasPreviousPage }
                }
            }
        """
        data = await graphql_execute(query)
        payload = data["patients"]
        assert payload["edges"] == []
        assert payload["pageInfo"]["hasNextPage"] is True
        assert payload["pageInfo"]["hasPreviousPage"] is False

    async def test_connection_last_zero_returns_empty_edges_with_has_previous_page(
        self, graphql_execute, patient_factory
    ):
        await patient_factory(name="Cursor last zero 1")
        await patient_factory(name="Cursor last zero 2")

        query = """
            query {
                patients(last: 0) {
                    edges { node { id } }
                    pageInfo { hasNextPage hasPreviousPage }
                }
            }
        """
        data = await graphql_execute(query)
        payload = data["patients"]
        assert payload["edges"] == []
        assert payload["pageInfo"]["hasNextPage"] is False
        assert payload["pageInfo"]["hasPreviousPage"] is True

    async def test_nested_cursor_rejects_parent_mismatch(
        self, graphql_execute, graphql_execute_raw, patient_factory, case_factory
    ):
        first_patient = await patient_factory(name="Cursor Parent One")
        second_patient = await patient_factory(name="Cursor Parent Two")
        await case_factory(patient_id=first_patient["id"], status="ONGOING")
        await case_factory(patient_id=second_patient["id"], status="ONGOING")

        first_patient_node_id = _relay_global_id("Patient", str(first_patient["id"]))
        second_patient_node_id = _relay_global_id("Patient", str(second_patient["id"]))

        first_query = """
            query($id: ID!) {
                node(id: $id) {
                    ... on Patient {
                        cases(first: 1) {
                            edges { cursor }
                        }
                    }
                }
            }
        """
        first_data = await graphql_execute(first_query, {"id": first_patient_node_id})
        cursor = first_data["node"]["cases"]["edges"][0]["cursor"]

        second_query = """
            query($id: ID!, $after: String!) {
                node(id: $id) {
                    ... on Patient {
                        cases(first: 1, after: $after) {
                            edges { node { id } }
                        }
                    }
                }
            }
        """
        result = await graphql_execute_raw(second_query, {"id": second_patient_node_id, "after": cursor})
        assert result.errors is not None
        assert "Argument 'after'" in result.errors[0].message
        assert "non-existing value" in result.errors[0].message


class TestGraphQLNestedRelationships:
    """Test nested relationship resolution via DataLoaders."""

    async def test_patient_with_cases(self, graphql_execute, patient_factory, case_factory):
        """Test querying patient with nested cases relationship."""
        patient = await patient_factory(name="John Doe")
        await case_factory(patient_id=patient["id"], status="PLANNED")
        await case_factory(patient_id=patient["id"], status="ONGOING")
        patient_node_id = _relay_global_id("Patient", str(patient["id"]))

        query = f"""
            query {{
                node(id: "{patient_node_id}") {{
                    ... on Patient {{
                        name
                        cases(first: 10) {{
                            edges {{
                                node {{
                                    status
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        """

        data = await graphql_execute(query)
        patient_data = data["node"]
        assert patient_data["name"] == "John Doe"
        edges = patient_data["cases"]["edges"]
        assert len(edges) == 2

        statuses = {edge["node"]["status"] for edge in edges}
        assert "PLANNED" in statuses
        assert "ONGOING" in statuses

    async def test_case_with_patient_backref(self, graphql_execute, patient_factory, case_factory):
        """Test querying case with back-reference to patient."""
        patient = await patient_factory(name="Jane Doe")
        case = await case_factory(patient_id=patient["id"], status="COMPLETED")
        case_node_id = _relay_global_id("Case", str(case["id"]))

        query = f"""
            query {{
                node(id: "{case_node_id}") {{
                    ... on Case {{
                        status
                        patient {{
                            name
                        }}
                    }}
                }}
            }}
        """

        data = await graphql_execute(query)
        case_data = data["node"]
        assert case_data["status"] == "COMPLETED"
        assert case_data["patient"]["name"] == "Jane Doe"


class TestGraphQLFilters:
    """Test filter application with boolean logic."""

    async def test_filter_by_status(self, graphql_execute, patient_factory, case_factory):
        """Test filtering cases by status using EQ operator."""
        patient = await patient_factory(name="Filter Test Patient")
        await case_factory(patient_id=patient["id"], status="PLANNED")
        await case_factory(patient_id=patient["id"], status="ONGOING")
        await case_factory(patient_id=patient["id"], status="COMPLETED")

        query = """
            query {
                cases(
                    first: 10
                    filter: {
                        condition: {
                            field: "status"
                            op: EQ
                            value: { string: "ONGOING" }
                        }
                    }
                ) {
                    edges {
                        node {
                            status
                        }
                    }
                }
            }
        """

        data = await graphql_execute(query)
        cases = data["cases"]["edges"]
        assert len(cases) == 1
        assert cases[0]["node"]["status"] == "ONGOING"

    async def test_filter_with_ilike(self, graphql_execute, patient_factory):
        """Test filtering patients by name using ILIKE (case-insensitive)."""
        await patient_factory(name="John Smith")
        await patient_factory(name="Jane Smith")
        await patient_factory(name="Bob Johnson")

        query = """
            query {
                patients(
                    first: 10
                    filter: {
                        condition: {
                            field: "name"
                            op: ILIKE
                            value: { string: "%smith%" }
                        }
                    }
                ) {
                    edges {
                        node {
                            name
                        }
                    }
                }
            }
        """

        data = await graphql_execute(query)
        patients = data["patients"]["edges"]
        assert len(patients) == 2

        names = {p["node"]["name"] for p in patients}
        assert "John Smith" in names
        assert "Jane Smith" in names
        assert "Bob Johnson" not in names

    async def test_filter_rejects_ilike_on_non_string_field(self, graphql_execute_raw, case_factory, patient_factory):
        patient = await patient_factory(name="Enum Filter Patient")
        await case_factory(patient_id=patient["id"], status="ONGOING")

        query = """
            query {
                cases(
                    first: 10
                    filter: {
                        condition: {
                            field: "status"
                            op: ILIKE
                            value: { string: "%ONGOING%" }
                        }
                    }
                ) {
                    edges { node { id } }
                }
            }
        """

        result = await graphql_execute_raw(query)
        assert result.errors is not None
        assert "Filter operator ILIKE" in result.errors[0].message
        assert "only supported for string fields" in result.errors[0].message
        assert "Case" in result.errors[0].message

    async def test_filter_rejects_contains_without_value(self, graphql_execute_raw, patient_factory):
        await patient_factory(name="Missing Contains Value")

        query = """
            query {
                patients(
                    first: 10
                    filter: {
                        condition: {
                            field: "name"
                            op: CONTAINS
                        }
                    }
                ) {
                    edges { node { id } }
                }
            }
        """

        result = await graphql_execute_raw(query)
        assert result.errors is not None
        assert "Filter operator CONTAINS" in result.errors[0].message
        assert "non-empty string value" in result.errors[0].message

    async def test_filter_rejects_empty_in_list(self, graphql_execute_raw, patient_factory):
        await patient_factory(name="Empty In List")

        query = """
            query {
                patients(
                    first: 10
                    filter: {
                        condition: {
                            field: "name"
                            op: IN
                            value: { stringList: [] }
                        }
                    }
                ) {
                    edges { node { id } }
                }
            }
        """

        result = await graphql_execute_raw(query)
        assert result.errors is not None
        assert "Filter operator IN" in result.errors[0].message
        assert "non-empty list-like value" in result.errors[0].message


class TestGraphQLTelemetry:
    """Test telemetry GraphQL direct Influx query path."""

    async def test_telemetry_rejects_naive_datetime(self, graphql_execute_raw):
        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    start: "2026-01-01T00:00:00"
                    limit: 50
                }) {
                    items { measurement }
                    hasMore
                }
            }
        """
        result = await graphql_execute_raw(query)
        assert result.errors is not None
        assert "AwareDateTime" in result.errors[0].message
        assert "Datetime must include timezone information." in result.errors[0].message

    async def test_telemetry_direct_query(self, graphql_execute, mock_influx_client):
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                }
            )

        async def schema_tag_gen():
            for key in ("patient_id", "device_id", "wearable_id", "case_id", "mapping_id", "dot_dependency_file_id"):
                yield Record({"_value": key})

        async def schema_field_gen():
            yield Record({"_value": "heart_rate"})

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux:
                return schema_tag_gen()
            if "schema.measurementFieldKeys" in flux:
                return schema_field_gen()
            return gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    tags: [{ key: "patient_id", match: { value: "p1" } }]
                    limit: 50
                }) {
                    items {
                        measurement
                        tags
                        fields
                    }
                    hasMore
                }
            }
        """

        data = await graphql_execute(query)
        payload = data["telemetry"]
        assert payload["hasMore"] is False
        assert len(payload["items"]) == 1
        assert payload["items"][0]["measurement"] == "sensor_readings"
        assert payload["items"][0]["tags"]["patient_id"] == "p1"
        assert payload["items"][0]["tags"]["dot_dependency_file_id"] == dot_dependency_file_id

    async def test_telemetry_raw_direct_query(self, graphql_execute, mock_influx_client):
        dot_dependency_file_id = _uuid_str()
        query_calls = 0

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                }
            )

        async def empty_gen():
            if False:
                yield None

        async def query_stream(*args, **kwargs):
            nonlocal query_calls
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux or "schema.measurementFieldKeys" in flux:
                pytest.fail("Raw GraphQL telemetry query should not issue schema queries.")
            query_calls += 1
            if query_calls == 1:
                return gen()
            return empty_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetryRaw(query: {
                    measurement: "sensor_readings"
                    tags: [{ key: "patient_id", match: { value: "p1" } }]
                    limit: 50
                }) {
                    items {
                        timestamp
                        measurement
                        field
                        value
                        tags
                    }
                    hasMore
                }
            }
        """

        data = await graphql_execute(query)
        payload = data["telemetryRaw"]
        assert payload["hasMore"] is False
        assert len(payload["items"]) == 1
        assert payload["items"][0]["measurement"] == "sensor_readings"
        assert payload["items"][0]["field"] == "heart_rate"
        assert payload["items"][0]["value"] == 70
        assert payload["items"][0]["tags"]["patient_id"] == "p1"
        assert payload["items"][0]["tags"]["dot_dependency_file_id"] == dot_dependency_file_id

    async def test_telemetry_direct_query_supports_bucket_and_optional_measurement(
        self, graphql_execute, mock_influx_client
    ):
        captured_params: dict[str, object] = {}
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                }
            )

        async def query_stream(*args, **kwargs):
            flux = args[0] if args else ""
            if "schema.measurementTagKeys" in flux or "schema.measurementFieldKeys" in flux:
                pytest.fail("Schema queries should not be required when measurement is omitted.")
            captured_params.update(kwargs.get("params", {}))
            return gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    bucket: "research_data"
                    tags: [{ key: "patient_id", match: { value: "p1" } }]
                    limit: 50
                }) {
                    items {
                        measurement
                        tags
                    }
                }
            }
        """

        data = await graphql_execute(query)
        payload = data["telemetry"]
        assert len(payload["items"]) == 1
        assert payload["items"][0]["measurement"] == "sensor_readings"
        assert payload["items"][0]["tags"]["patient_id"] == "p1"
        assert payload["items"][0]["tags"]["dot_dependency_file_id"] == dot_dependency_file_id

        assert captured_params["bucket_param"] == "research_data"
        assert "measurement_param" not in captured_params

    async def test_telemetry_direct_query_supports_in_for_arbitrary_tags(self, graphql_execute, mock_influx_client):
        captured_params = {}
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def gen():
            yield Record(
                {
                    "_time": datetime(2026, 1, 1, tzinfo=UTC),
                    "_measurement": "sensor_readings",
                    "_field": "heart_rate",
                    "_value": 70,
                    "patient_id": "p1",
                    "device_id": "d1",
                    "wearable_id": "w1",
                    "case_id": "c1",
                    "mapping_id": "m1",
                    "dot_dependency_file_id": dot_dependency_file_id,
                    "sensor_type": "ecg",
                }
            )

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    tags: [
                        { key: "patient_id", match: { value: "p1" } }
                        { key: "sensor_type", match: { values: ["ecg", "ppg"] } }
                    ]
                    limit: 50
                }) {
                    items {
                        measurement
                        tags
                    }
                    hasMore
                }
            }
        """

        data = await graphql_execute(query)
        payload = data["telemetry"]
        assert len(payload["items"]) == 1

        tag_values = _extract_tag_param_values(captured_params)
        assert "p1" in tag_values
        assert {"ecg", "ppg"}.issubset(set(tag_values))

    async def test_telemetry_rejects_legacy_dot_dependency_file_ids(self, graphql_execute_raw):
        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    dotDependencyFileIds: ["heart_rate"]
                    limit: 50
                }) {
                    items { measurement }
                }
            }
        """

        result = await graphql_execute_raw(query)
        assert result.errors is not None
        assert "UUID" in result.errors[0].message

    async def test_telemetry_patient_filter_injects_patient_ids(
        self,
        graphql_execute,
        patient_factory,
        mock_influx_client,
    ):
        older_patient = await patient_factory(name="Older Patient", dob=date(1960, 1, 1))
        await patient_factory(name="Younger Patient", dob=date(2010, 1, 1))

        captured_params = {}

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    patientFilter: {
                        condition: {
                            field: "dob"
                            op: LTE
                            value: { date: "1976-01-01" }
                        }
                    }
                    limit: 50
                }) {
                    items { measurement }
                    hasMore
                }
            }
        """

        await graphql_execute(query)

        tag_values = _extract_tag_param_values(captured_params)
        assert str(older_patient["id"]) in tag_values

    async def test_telemetry_device_filter_injects_device_ids(
        self,
        graphql_execute,
        device_factory,
        mock_influx_client,
    ):
        matching_device = await device_factory(serial_nr="TARGET-DEVICE", model="Model A")
        await device_factory(serial_nr="OTHER-DEVICE", model="Model B")

        captured_params = {}

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    deviceFilter: {
                        condition: {
                            field: "serial_nr"
                            op: ILIKE
                            value: { string: "%TARGET%" }
                        }
                    }
                    limit: 50
                }) {
                    items { measurement }
                    hasMore
                }
            }
        """

        await graphql_execute(query)

        tag_values = _extract_tag_param_values(captured_params)
        assert str(matching_device["id"]) in tag_values

    async def test_telemetry_include_resolved_metadata_returns_entities(
        self,
        graphql_execute,
        patient_factory,
        mock_influx_client,
    ):
        target_patient = await patient_factory(name="Metadata Target", dob=date(1960, 1, 1))
        await patient_factory(name="Metadata Other", dob=date(2010, 1, 1))

        captured_params = {}

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    patientFilter: {
                        condition: {
                            field: "dob"
                            op: LTE
                            value: { date: "1976-01-01" }
                        }
                    }
                    includeResolvedMetadata: true
                    limit: 50
                }) {
                    items { measurement }
                    hasMore
                    resolved {
                        patients {
                            id
                            name
                        }
                    }
                }
            }
        """

        data = await graphql_execute(query)
        telemetry = data["telemetry"]
        assert telemetry["resolved"] is not None
        assert len(telemetry["resolved"]["patients"]) == 1
        assert _relay_node_id(telemetry["resolved"]["patients"][0]["id"]) == str(target_patient["id"])
        assert telemetry["resolved"]["patients"][0]["name"] == "Metadata Target"

        tag_values = _extract_tag_param_values(captured_params)
        assert str(target_patient["id"]) in tag_values

    async def test_telemetry_include_resolved_metadata_exposes_mapping_json(
        self,
        graphql_execute,
        db_session,
        mock_influx_client,
    ):
        from app.db.postgres.orm import FHIRMapping

        mapping_id = uuid7()
        mapping_payload = {
            "resourceType": "Observation",
            "map": {"heart_rate": "valueQuantity.value"},
        }
        db_session.add(
            FHIRMapping(
                id=mapping_id,
                version="v-json-test",
                full_mapping=mapping_payload,
            )
        )
        await db_session.commit()

        captured_params = {}

        async def query_stream(*args, **kwargs):
            captured_params.update(kwargs.get("params", {}))
            return empty_async_iterator()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    mappingFilter: {
                        condition: {
                            field: "version"
                            op: EQ
                            value: { string: "v-json-test" }
                        }
                    }
                    includeResolvedMetadata: true
                    limit: 50
                }) {
                    items { measurement }
                    resolved {
                        mappings {
                            id
                            version
                            fullMapping
                        }
                    }
                }
            }
        """

        data = await graphql_execute(query)
        telemetry = data["telemetry"]
        assert telemetry["resolved"] is not None
        assert len(telemetry["resolved"]["mappings"]) == 1
        assert _relay_node_id(telemetry["resolved"]["mappings"][0]["id"]) == str(mapping_id)
        assert telemetry["resolved"]["mappings"][0]["version"] == "v-json-test"
        assert telemetry["resolved"]["mappings"][0]["fullMapping"] == mapping_payload

        tag_values = _extract_tag_param_values(captured_params)
        assert str(mapping_id) in tag_values


class TestGraphQLTelemetryStreaming:
    async def test_telemetry_subscription_streams_incrementally(self, graphql_context_factory, mock_influx_client):
        produced: list[int] = []
        dot_dependency_file_id = _uuid_str()

        class Record:
            def __init__(self, values):
                self.values = values

        async def tag_keys_gen():
            for key in ("patient_id", "device_id", "wearable_id", "case_id", "mapping_id", "dot_dependency_file_id"):
                yield Record({"_value": key})

        async def field_keys_gen():
            yield Record({"_value": "heart_rate"})

        async def gen():
            for index, ts in enumerate(
                (
                    datetime(2026, 1, 3, tzinfo=UTC),
                    datetime(2026, 1, 2, tzinfo=UTC),
                )
            ):
                produced.append(index)
                yield Record(
                    {
                        "_time": ts,
                        "_measurement": "sensor_readings",
                        "_field": "heart_rate",
                        "_value": 70 + index,
                        "patient_id": "p1",
                        "device_id": "d1",
                        "wearable_id": "w1",
                        "case_id": "c1",
                        "mapping_id": "m1",
                        "dot_dependency_file_id": dot_dependency_file_id,
                    }
                )

        query_calls = 0

        async def empty_gen():
            if False:
                yield None

        async def query_stream(*args, **kwargs):
            nonlocal query_calls
            flux = args[0] if args else kwargs.get("query", "")
            if "schema.measurementTagKeys" in flux:
                return tag_keys_gen()
            if "schema.measurementFieldKeys" in flux:
                return field_keys_gen()
            if "|> limit(" in flux:
                pytest.fail("Structured GraphQL telemetry stream should not rely on Flux row limits.")
            query_calls += 1
            if query_calls == 1:
                return gen()
            return empty_gen()

        mock_influx_client.query_api.return_value.query_stream = query_stream

        subscription = """
            subscription StreamTelemetry($measurement: String!) {
                telemetryStream(
                    query: {
                        measurement: $measurement
                        tags: [{ key: "patient_id", match: { value: "p1" } }]
                        limit: 2
                    }
                ) {
                    measurement
                    tags
                    fields
                }
            }
        """

        result = await schema.subscribe(
            subscription,
            variable_values={"measurement": "sensor_readings"},
            context_value=graphql_context_factory(),
        )

        assert hasattr(result, "__aiter__"), "Expected subscription to return an async result stream"

        first_event = await anext(result)
        assert first_event.errors is None
        assert first_event.data is not None
        assert produced == [0, 1]
        assert first_event.data["telemetryStream"]["measurement"] == "sensor_readings"
        assert first_event.data["telemetryStream"]["tags"]["patient_id"] == "p1"
        assert first_event.data["telemetryStream"]["fields"]["heart_rate"] == 70

        second_event = await anext(result)
        assert second_event.errors is None
        assert second_event.data is not None
        assert produced == [0, 1]
        assert second_event.data["telemetryStream"]["fields"]["heart_rate"] == 71

        with pytest.raises(StopAsyncIteration):
            await anext(result)

        await result.aclose()


class TestGraphQLPerformance:
    async def test_nested_connections_are_batched_not_n_plus_one(
        self, graphql_context_factory, db_session: AsyncSession, patient_factory, case_factory
    ):
        for index in range(6):
            patient = await patient_factory(name=f"Batch Parent {index}")
            await case_factory(patient_id=patient["id"], status="ONGOING")

        query = """
            query {
                patients(first: 10) {
                    edges {
                        node {
                            id
                            cases(first: 1) {
                                edges {
                                    node { id }
                                }
                            }
                        }
                    }
                }
            }
        """

        bind = db_session.bind
        if bind is None:
            raise RuntimeError("Test db_session is not bound to an engine.")
        sync_engine = bind.sync_engine
        statement_count = 0

        def _before_cursor_execute(
            _conn,
            _cursor,
            statement: str,
            _parameters,
            _context,
            _executemany,
        ):
            nonlocal statement_count
            if statement.lstrip().upper().startswith(("SELECT", "WITH")):
                statement_count += 1

        event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
        try:
            result = await schema.execute(query, context_value=graphql_context_factory())
        finally:
            event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)

        assert result.errors is None, result.errors
        assert result.data is not None
        assert len(result.data["patients"]["edges"]) == 6
        for edge in result.data["patients"]["edges"]:
            assert len(edge["node"]["cases"]["edges"]) == 1

        # Guards against per-parent query growth in nested connection resolution.
        assert statement_count <= 3
