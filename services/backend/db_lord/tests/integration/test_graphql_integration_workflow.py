import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry.relay.utils import to_base64

from app.core.config import settings
from app.schemas.context import ContextResponse
from app.schemas.device import DeviceResponse
from app.schemas.wearable import WearableResponse
from tests.helpers.api import assert_graphql_error as _assert_graphql_error
from tests.helpers.api import assert_graphql_ok as _assert_graphql_ok
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.api import create_case as _create_case_helper
from tests.helpers.api import create_context as _create_context_helper
from tests.helpers.api import create_device as _create_device_helper
from tests.helpers.api import create_patient as _create_patient_helper
from tests.helpers.api import create_wearable as _create_wearable_helper
from tests.helpers.api import record_telemetry as _record_telemetry_helper
from tests.helpers.common import eventually as _eventually
from tests.helpers.common import relay_global_id as _relay_global_id
from tests.helpers.common import relay_node_id as _relay_node_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

REALISTIC_DOT_DIGRAPH = """strict digraph G {
  value;
  start;
  type;
  codeCodingCodeZero;
  codeCodingDisplayZero;
  codeCodingSystemZero;
  valueUnit;
  valueCode;
  valueSystem;
  codeCodingCodeOne;
  codeCodingDisplayOne;
  codeCodingSystemOne;
  end;
  device;
  type -> codeCodingCodeZero;
  codeCodingCodeZero -> codeCodingDisplayZero;
  codeCodingCodeZero -> codeCodingSystemZero;
  codeCodingCodeZero -> valueUnit;
  valueUnit -> valueCode;
  valueUnit -> valueSystem;
  codeCodingCodeZero -> codeCodingCodeOne;
  codeCodingCodeOne -> codeCodingDisplayOne;
  codeCodingCodeOne -> codeCodingSystemOne;
}"""


async def _create_device(client: AsyncClient, serial_nr: str) -> DeviceResponse:
    return await _create_device_helper(client, serial_nr=serial_nr, model="GraphQL Device")


async def _create_wearable(client: AsyncClient, serial_nr: str) -> WearableResponse:
    return await _create_wearable_helper(client, serial_nr=serial_nr, model="GraphQL Wearable")


async def _create_context(client: AsyncClient, group_name: str) -> ContextResponse:
    return await _create_context_helper(client, group_name=group_name, coordinator="GraphQL Coordinator")


class TestGraphQLPostgresIntegration:
    async def test_nested_relationships_with_filters_and_dataloaders(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="GraphQL Nested Patient")
        other_patient = await _create_patient_helper(integration_client, name="GraphQL Other Patient")

        ongoing_case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        planned_case = await _create_case_helper(integration_client, patient_id=patient.id, status="PLANNED")
        await _create_case_helper(integration_client, patient_id=other_patient.id, status="COMPLETED")

        device = await _create_device(integration_client, serial_nr=f"GQL-DEV-{uuid7().hex[:8]}")
        wearable = await _create_wearable(integration_client, serial_nr=f"GQL-WEAR-{uuid7().hex[:8]}")
        context = await _create_context(integration_client, group_name="GQL-Ward")

        assign_device_response = await integration_client.post(f"/cases/{ongoing_case.id}/devices/{device.id}")
        _assert_json_response(assign_device_response, status_code=201)
        assign_wearable_response = await integration_client.post(
            f"/cases/{ongoing_case.id}/wearables/{wearable.id}"
        )
        _assert_json_response(assign_wearable_response, status_code=201)
        link_context_response = await integration_client.post(f"/cases/{ongoing_case.id}/contexts/{context.id}")
        _assert_json_response(link_context_response, status_code=201)

        query = """
            query($pattern: String!) {
                patients(
                    first: 10
                    filter: {
                        condition: {
                            field: "name"
                            op: ILIKE
                            value: { string: $pattern }
                        }
                    }
                ) {
                    edges {
                        node {
                            id
                            name
                            cases(first: 10) {
                                edges {
                                    node {
                                        id
                                        status
                                        patient { id name }
                                        devices(first: 10) { edges { node { id serialNr status } } }
                                        wearables(first: 10) { edges { node { id serialNr status } } }
                                        contexts(first: 10) { edges { node { id groupName } } }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """

        response = await integration_client.post(
            "/graphql",
            json={"query": query, "variables": {"pattern": "%GraphQL Nested%"}},
        )
        payload = _assert_graphql_ok(response)

        edges = payload["data"]["patients"]["edges"]
        assert len(edges) == 1
        patient_node = edges[0]["node"]
        assert _relay_node_id(patient_node["id"]) == str(patient.id)
        assert patient_node["name"] == "GraphQL Nested Patient"

        case_edges = patient_node["cases"]["edges"]
        cases_by_id = {_relay_node_id(edge["node"]["id"]): edge["node"] for edge in case_edges}
        assert set(cases_by_id) == {str(ongoing_case.id), str(planned_case.id)}

        ongoing_node = cases_by_id[str(ongoing_case.id)]
        assert _relay_node_id(ongoing_node["patient"]["id"]) == str(patient.id)
        assert {_relay_node_id(edge["node"]["id"]) for edge in ongoing_node["devices"]["edges"]} == {str(device.id)}
        assert {_relay_node_id(edge["node"]["id"]) for edge in ongoing_node["wearables"]["edges"]} == {str(wearable.id)}
        assert {_relay_node_id(edge["node"]["id"]) for edge in ongoing_node["contexts"]["edges"]} == {str(context.id)}

        planned_node = cases_by_id[str(planned_case.id)]
        assert planned_node["devices"]["edges"] == []
        assert planned_node["wearables"]["edges"] == []
        assert planned_node["contexts"]["edges"] == []

    async def test_case_devices_and_wearables_include_active_assignments_with_future_end(
        self, integration_client: AsyncClient
    ):
        patient = await _create_patient_helper(integration_client, name="GraphQL Timed Assignment Patient")
        ongoing_case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        device = await _create_device(integration_client, serial_nr=f"GQL-TIME-DEV-{uuid7().hex[:8]}")
        wearable = await _create_wearable(integration_client, serial_nr=f"GQL-TIME-WEAR-{uuid7().hex[:8]}")

        end_time = (datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)).isoformat()
        assign_device_response = await integration_client.post(
            f"/cases/{ongoing_case.id}/devices/{device.id}",
            params={"end_time": end_time},
        )
        _assert_json_response(assign_device_response, status_code=201)

        assign_wearable_response = await integration_client.post(
            f"/cases/{ongoing_case.id}/wearables/{wearable.id}",
            params={"end_time": end_time},
        )
        _assert_json_response(assign_wearable_response, status_code=201)
        case_node_id = _relay_global_id("Case", str(ongoing_case.id))

        query = """
            query($caseNodeId: ID!) {
                node(id: $caseNodeId) {
                    ... on Case {
                        id
                        devices(first: 10) { edges { node { id } } }
                        wearables(first: 10) { edges { node { id } } }
                    }
                }
            }
        """
        response = await integration_client.post(
            "/graphql",
            json={"query": query, "variables": {"caseNodeId": case_node_id}},
        )
        payload = _assert_graphql_ok(response)

        case_node = payload["data"]["node"]
        assert case_node is not None
        assert {_relay_node_id(edge["node"]["id"]) for edge in case_node["devices"]["edges"]} == {str(device.id)}
        assert {_relay_node_id(edge["node"]["id"]) for edge in case_node["wearables"]["edges"]} == {str(wearable.id)}

    async def test_assignment_loader_paths_case_and_device_wearable_sides(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="GraphQL Assignment Loader Patient")
        ongoing_case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        device = await _create_device(integration_client, serial_nr=f"GQL-ASSIGN-DEV-{uuid7().hex[:8]}")
        wearable = await _create_wearable(integration_client, serial_nr=f"GQL-ASSIGN-WEAR-{uuid7().hex[:8]}")

        assign_device_response = await integration_client.post(f"/cases/{ongoing_case.id}/devices/{device.id}")
        _assert_json_response(assign_device_response, status_code=201)
        assign_wearable_response = await integration_client.post(
            f"/cases/{ongoing_case.id}/wearables/{wearable.id}"
        )
        _assert_json_response(assign_wearable_response, status_code=201)

        query = """
            query AssignmentLoaderPaths($caseId: ID!, $deviceId: ID!, $wearableId: ID!) {
                caseNode: node(id: $caseId) {
                    ... on Case {
                        id
                        deviceAssignments(first: 10) {
                            edges {
                                node {
                                    caseId
                                    deviceId
                                    assignedFrom
                                    assignedTo
                                    device { id }
                                }
                            }
                        }
                        wearableAssignments(first: 10) {
                            edges {
                                node {
                                    caseId
                                    wearableId
                                    assignedFrom
                                    assignedTo
                                    wearable { id }
                                }
                            }
                        }
                    }
                }
                deviceNode: node(id: $deviceId) {
                    ... on Device {
                        id
                        caseAssignments(first: 10) {
                            edges {
                                node {
                                    caseId
                                    deviceId
                                    assignedFrom
                                    case { id }
                                }
                            }
                        }
                    }
                }
                wearableNode: node(id: $wearableId) {
                    ... on Wearable {
                        id
                        caseAssignments(first: 10) {
                            edges {
                                node {
                                    caseId
                                    wearableId
                                    assignedFrom
                                    case { id }
                                }
                            }
                        }
                    }
                }
            }
        """
        response = await integration_client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {
                    "caseId": _relay_global_id("Case", str(ongoing_case.id)),
                    "deviceId": _relay_global_id("Device", str(device.id)),
                    "wearableId": _relay_global_id("Wearable", str(wearable.id)),
                },
            },
        )
        payload = _assert_graphql_ok(response)

        case_node = payload["data"]["caseNode"]
        assert case_node is not None
        case_device_edges = case_node["deviceAssignments"]["edges"]
        assert len(case_device_edges) == 1
        assert case_device_edges[0]["node"]["caseId"] == str(ongoing_case.id)
        assert case_device_edges[0]["node"]["deviceId"] == str(device.id)
        assert _relay_node_id(case_device_edges[0]["node"]["device"]["id"]) == str(device.id)

        case_wearable_edges = case_node["wearableAssignments"]["edges"]
        assert len(case_wearable_edges) == 1
        assert case_wearable_edges[0]["node"]["caseId"] == str(ongoing_case.id)
        assert case_wearable_edges[0]["node"]["wearableId"] == str(wearable.id)
        assert _relay_node_id(case_wearable_edges[0]["node"]["wearable"]["id"]) == str(wearable.id)

        device_node = payload["data"]["deviceNode"]
        assert device_node is not None
        device_assignment_edges = device_node["caseAssignments"]["edges"]
        assert len(device_assignment_edges) == 1
        assert device_assignment_edges[0]["node"]["deviceId"] == str(device.id)
        assert _relay_node_id(device_assignment_edges[0]["node"]["case"]["id"]) == str(ongoing_case.id)

        wearable_node = payload["data"]["wearableNode"]
        assert wearable_node is not None
        wearable_assignment_edges = wearable_node["caseAssignments"]["edges"]
        assert len(wearable_assignment_edges) == 1
        assert wearable_assignment_edges[0]["node"]["wearableId"] == str(wearable.id)
        assert _relay_node_id(wearable_assignment_edges[0]["node"]["case"]["id"]) == str(ongoing_case.id)

    async def test_relay_cursor_pagination_and_invalid_cursor(self, integration_client: AsyncClient):
        for i in range(5):
            await _create_patient_helper(integration_client, name=f"GraphQL Cursor Patient {i}")

        first_query = """
            query {
                patients(
                    first: 2
                    filter: {
                        condition: {
                            field: "name"
                            op: ILIKE
                            value: { string: "%GraphQL Cursor Patient%" }
                        }
                    }
                ) {
                    edges { cursor node { id name } }
                    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
                }
            }
        """
        first_response = await integration_client.post("/graphql", json={"query": first_query})
        first_payload = _assert_graphql_ok(first_response)

        first_page = first_payload["data"]["patients"]
        assert len(first_page["edges"]) == 2
        assert first_page["pageInfo"]["hasNextPage"] is True
        assert first_page["pageInfo"]["hasPreviousPage"] is False
        assert first_page["pageInfo"]["startCursor"] is not None
        end_cursor = first_page["pageInfo"]["endCursor"]
        assert end_cursor is not None

        second_query = """
            query($after: String!) {
                patients(
                    first: 3
                    after: $after
                    filter: {
                        condition: {
                            field: "name"
                            op: ILIKE
                            value: { string: "%GraphQL Cursor Patient%" }
                        }
                    }
                ) {
                    edges { node { id } }
                    pageInfo { hasNextPage }
                }
            }
        """
        second_response = await integration_client.post(
            "/graphql",
            json={"query": second_query, "variables": {"after": end_cursor}},
        )
        second_payload = _assert_graphql_ok(second_response)

        first_ids = {edge["node"]["id"] for edge in first_page["edges"]}
        second_ids = {edge["node"]["id"] for edge in second_payload["data"]["patients"]["edges"]}
        assert first_ids.isdisjoint(second_ids)

        backward_query = """
            query($before: String!) {
                patients(
                    last: 1
                    before: $before
                    filter: {
                        condition: {
                            field: "name"
                            op: ILIKE
                            value: { string: "%GraphQL Cursor Patient%" }
                        }
                    }
                ) {
                    edges { node { id } }
                    pageInfo { hasNextPage hasPreviousPage startCursor endCursor }
                }
            }
        """
        backward_response = await integration_client.post(
            "/graphql",
            json={"query": backward_query, "variables": {"before": end_cursor}},
        )
        backward_payload = _assert_graphql_ok(backward_response)
        backward_page = backward_payload["data"]["patients"]
        assert len(backward_page["edges"]) == 1
        assert backward_page["pageInfo"]["hasNextPage"] is True
        assert backward_page["pageInfo"]["hasPreviousPage"] is False

        invalid_response = await integration_client.post(
            "/graphql",
            json={"query": second_query, "variables": {"after": "not-a-valid-cursor"}},
        )
        invalid_payload = _assert_graphql_error(invalid_response)
        assert "Argument 'after'" in invalid_payload["errors"][0]["message"]
        assert "non-existing value" in invalid_payload["errors"][0]["message"]

        wrong_prefix_response = await integration_client.post(
            "/graphql",
            json={"query": second_query, "variables": {"after": to_base64("wrong-prefix", str(uuid7()))}},
        )
        wrong_prefix_payload = _assert_graphql_error(wrong_prefix_response)
        assert "Argument 'after'" in wrong_prefix_payload["errors"][0]["message"]
        assert "non-existing value" in wrong_prefix_payload["errors"][0]["message"]

        invalid_uuid_response = await integration_client.post(
            "/graphql",
            json={"query": second_query, "variables": {"after": to_base64("keyset", "not-a-uuid")}},
        )
        invalid_uuid_payload = _assert_graphql_error(invalid_uuid_response)
        assert "Argument 'after'" in invalid_uuid_payload["errors"][0]["message"]
        assert "non-existing value" in invalid_uuid_payload["errors"][0]["message"]

    async def test_root_relay_connections_for_fhir_mappings_and_dot_dependency_files(
        self, integration_client: AsyncClient
    ):
        mapping_payload = {
            "resourceType": "Observation",
            "map": {"heart_rate": "valueQuantity.value"},
        }
        mapping_response = await integration_client.post(
            "/fhir-mappings/",
            json={
                "version": f"gql-relay-map-{uuid7().hex[:8]}",
                "full_mapping": mapping_payload,
            },
        )
        mapping = _assert_json_response(mapping_response, status_code=201)

        dot_payload = {
            "version": mapping["version"],
            "category": "incremental",
            "digraph": {
                "format": "dot",
                "source": REALISTIC_DOT_DIGRAPH,
                "entrypoint": "value",
                "nodes": [
                    "value",
                    "start",
                    "type",
                    "codeCodingCodeZero",
                    "codeCodingDisplayZero",
                    "codeCodingSystemZero",
                    "valueUnit",
                    "valueCode",
                    "valueSystem",
                    "codeCodingCodeOne",
                    "codeCodingDisplayOne",
                    "codeCodingSystemOne",
                    "end",
                    "device",
                ],
            },
            "mapping_id": mapping["id"],
        }
        dot_response = await integration_client.post("/fhir-mappings/dot_dependency_file", json=dot_payload)
        dot_file = _assert_json_response(dot_response, status_code=201)

        query = """
            query MappingConnections($version: String!, $category: String!) {
                fhirMappings(
                    first: 10
                    filter: {
                        condition: {
                            field: "version"
                            op: EQ
                            value: { string: $version }
                        }
                    }
                ) {
                    edges {
                        node {
                            id
                            version
                            fullMapping
                        }
                    }
                    pageInfo { hasNextPage hasPreviousPage }
                }
                dotDependencyFiles(
                    first: 10
                    filter: {
                        condition: {
                            field: "category"
                            op: EQ
                            value: { string: $category }
                        }
                    }
                ) {
                    edges {
                        node {
                            id
                            version
                            category
                            mappingId
                            digraph
                        }
                    }
                    pageInfo { hasNextPage hasPreviousPage }
                }
            }
        """
        response = await integration_client.post(
            "/graphql",
            json={"query": query, "variables": {"version": mapping["version"], "category": dot_payload["category"]}},
        )
        payload = _assert_graphql_ok(response)

        mapping_edges = payload["data"]["fhirMappings"]["edges"]
        assert len(mapping_edges) == 1
        assert _relay_node_id(mapping_edges[0]["node"]["id"]) == mapping["id"]
        assert mapping_edges[0]["node"]["version"] == mapping["version"]
        assert mapping_edges[0]["node"]["fullMapping"] == mapping_payload
        assert payload["data"]["fhirMappings"]["pageInfo"]["hasNextPage"] is False

        dot_edges = payload["data"]["dotDependencyFiles"]["edges"]
        assert len(dot_edges) == 1
        assert _relay_node_id(dot_edges[0]["node"]["id"]) == dot_file["id"]
        assert dot_edges[0]["node"]["version"] == dot_file["version"]
        assert dot_edges[0]["node"]["category"] == dot_file["category"]
        assert dot_edges[0]["node"]["mappingId"] == mapping["id"]
        assert dot_edges[0]["node"]["digraph"] == dot_payload["digraph"]
        assert payload["data"]["dotDependencyFiles"]["pageInfo"]["hasNextPage"] is False

    async def test_relay_node_refetch_by_global_id(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="GraphQL Node Refetch Patient")
        global_id = _relay_global_id("Patient", str(patient.id))
        assert _relay_node_id(global_id) == str(patient.id)

        node_query = """
            query($id: ID!) {
                node(id: $id) {
                    __typename
                    ... on Patient {
                        id
                        name
                    }
                }
            }
        """
        node_response = await integration_client.post(
            "/graphql",
            json={"query": node_query, "variables": {"id": global_id}},
        )
        node_payload = _assert_graphql_ok(node_response)
        node = node_payload["data"]["node"]
        assert node["__typename"] == "Patient"
        assert _relay_node_id(node["id"]) == str(patient.id)
        assert node["name"] == "GraphQL Node Refetch Patient"

    async def test_relay_node_refetch_supports_all_node_types(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="Relay All Types Patient")
        case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        device = await _create_device(integration_client, serial_nr=f"GQL-ALL-DEV-{uuid7().hex[:8]}")
        wearable = await _create_wearable(integration_client, serial_nr=f"GQL-ALL-WEAR-{uuid7().hex[:8]}")
        context = await _create_context(integration_client, group_name="Relay-All-Types-Ward")

        query = """
            query AllNodes($patientId: ID!, $caseId: ID!, $deviceId: ID!, $wearableId: ID!, $contextId: ID!) {
                patientNode: node(id: $patientId) {
                    __typename
                    ... on Patient {
                        id
                        name
                    }
                }
                caseNode: node(id: $caseId) {
                    __typename
                    ... on Case {
                        id
                        status
                        patientId
                    }
                }
                deviceNode: node(id: $deviceId) {
                    __typename
                    ... on Device {
                        id
                        serialNr
                        status
                    }
                }
                wearableNode: node(id: $wearableId) {
                    __typename
                    ... on Wearable {
                        id
                        serialNr
                        status
                    }
                }
                contextNode: node(id: $contextId) {
                    __typename
                    ... on Context {
                        id
                        groupName
                    }
                }
            }
        """
        response = await integration_client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {
                    "patientId": _relay_global_id("Patient", str(patient.id)),
                    "caseId": _relay_global_id("Case", str(case.id)),
                    "deviceId": _relay_global_id("Device", str(device.id)),
                    "wearableId": _relay_global_id("Wearable", str(wearable.id)),
                    "contextId": _relay_global_id("Context", str(context.id)),
                },
            },
        )
        payload = _assert_graphql_ok(response)

        assert payload["data"]["patientNode"]["__typename"] == "Patient"
        assert _relay_node_id(payload["data"]["patientNode"]["id"]) == str(patient.id)
        assert payload["data"]["patientNode"]["name"] == "Relay All Types Patient"

        assert payload["data"]["caseNode"]["__typename"] == "Case"
        assert _relay_node_id(payload["data"]["caseNode"]["id"]) == str(case.id)
        assert payload["data"]["caseNode"]["status"] == "ONGOING"
        assert payload["data"]["caseNode"]["patientId"] == str(patient.id)

        assert payload["data"]["deviceNode"]["__typename"] == "Device"
        assert _relay_node_id(payload["data"]["deviceNode"]["id"]) == str(device.id)
        assert payload["data"]["deviceNode"]["serialNr"] == device.serial_nr
        assert payload["data"]["deviceNode"]["status"] == "AVAILABLE"

        assert payload["data"]["wearableNode"]["__typename"] == "Wearable"
        assert _relay_node_id(payload["data"]["wearableNode"]["id"]) == str(wearable.id)
        assert payload["data"]["wearableNode"]["serialNr"] == wearable.serial_nr
        assert payload["data"]["wearableNode"]["status"] == "AVAILABLE"

        assert payload["data"]["contextNode"]["__typename"] == "Context"
        assert _relay_node_id(payload["data"]["contextNode"]["id"]) == str(context.id)
        assert payload["data"]["contextNode"]["groupName"] == "Relay-All-Types-Ward"

    async def test_relay_node_refetch_returns_null_for_nonexistent_node(self, integration_client: AsyncClient):
        missing_patient_id = str(uuid7())
        query = """
            query MissingNode($id: ID!) {
                node(id: $id) {
                    __typename
                }
            }
        """
        response = await integration_client.post(
            "/graphql",
            json={"query": query, "variables": {"id": _relay_global_id("Patient", missing_patient_id)}},
        )
        payload = _assert_graphql_ok(response)
        assert payload["data"]["node"] is None

    async def test_connection_rejects_first_and_last_together(self, integration_client: AsyncClient):
        await _create_patient_helper(integration_client, name="GraphQL Invalid Pagination")

        query = """
            query {
                patients(first: 1, last: 1) {
                    edges { node { id } }
                }
            }
        """
        response = await integration_client.post("/graphql", json={"query": query})
        _assert_graphql_error(response)

    async def test_connection_rejects_negative_window_sizes(self, integration_client: AsyncClient):
        await _create_patient_helper(integration_client, name="GraphQL Negative Pagination")

        for arg_name in ("first", "last"):
            query = f"""
                query {{
                    patients({arg_name}: -1) {{
                        edges {{ node {{ id }} }}
                    }}
                }}
            """
            response = await integration_client.post("/graphql", json={"query": query})
            payload = _assert_graphql_error(response)
            assert f"Argument '{arg_name}'" in payload["errors"][0]["message"]
            assert "non-negative integer" in payload["errors"][0]["message"]

    async def test_connection_zero_window_sizes_have_stable_page_info(self, integration_client: AsyncClient):
        await _create_patient_helper(integration_client, name="GraphQL Zero Pagination 1")
        await _create_patient_helper(integration_client, name="GraphQL Zero Pagination 2")

        first_zero_query = """
            query {
                patients(first: 0) {
                    edges { node { id } }
                    pageInfo { hasNextPage hasPreviousPage }
                }
            }
        """
        first_zero_response = await integration_client.post("/graphql", json={"query": first_zero_query})
        first_zero_payload = _assert_graphql_ok(first_zero_response)
        first_zero_page = first_zero_payload["data"]["patients"]
        assert first_zero_page["edges"] == []
        assert first_zero_page["pageInfo"]["hasNextPage"] is True
        assert first_zero_page["pageInfo"]["hasPreviousPage"] is False

        last_zero_query = """
            query {
                patients(last: 0) {
                    edges { node { id } }
                    pageInfo { hasNextPage hasPreviousPage }
                }
            }
        """
        last_zero_response = await integration_client.post("/graphql", json={"query": last_zero_query})
        last_zero_payload = _assert_graphql_ok(last_zero_response)
        last_zero_page = last_zero_payload["data"]["patients"]
        assert last_zero_page["edges"] == []
        assert last_zero_page["pageInfo"]["hasNextPage"] is False
        assert last_zero_page["pageInfo"]["hasPreviousPage"] is True

    async def test_filter_input_one_of_rejects_multiple_branches(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="GraphQL OneOf Filter Patient")
        await _create_case_helper(integration_client, patient_id=patient.id, status="PLANNED")

        query = """
            query {
                cases(
                    first: 10
                    filter: {
                        condition: {
                            field: "status"
                            op: EQ
                            value: { string: "PLANNED" }
                        }
                        or: [
                            {
                                condition: {
                                    field: "status"
                                    op: EQ
                                    value: { string: "ONGOING" }
                                }
                            }
                        ]
                    }
                ) {
                    edges { node { id } }
                }
            }
        """
        response = await integration_client.post("/graphql", json={"query": query})
        _assert_graphql_error(response)

    async def test_telemetry_tag_match_one_of_rejects_multiple_branches(self, integration_client: AsyncClient):
        query = """
            query {
                telemetry(
                    query: {
                        measurement: "one_of_validation_measurement"
                        tags: [{ key: "sensor_type", match: { value: "ecg", values: ["ecg", "ppg"] } }]
                        limit: 5
                    }
                ) {
                    items { measurement }
                }
            }
        """
        response = await integration_client.post("/graphql", json={"query": query})
        _assert_graphql_error(response)


class TestGraphQLInfluxAndCrossDbIntegration:
    async def test_influx_telemetry_window_and_codes(self, integration_client: AsyncClient):
        measurement = f"gql_telemetry_{uuid7().hex[:10]}"
        heart_rate_dot_id = str(uuid7())
        resp_rate_dot_id = str(uuid7())

        patient_id = str(uuid7())
        case_id = str(uuid7())
        device_id = str(uuid7())
        wearable_id = str(uuid7())
        mapping_id = str(uuid7())
        context_id = str(uuid7())

        now_utc = datetime.now(UTC).replace(microsecond=0)
        timestamps = [
            now_utc - timedelta(minutes=2),
            now_utc - timedelta(minutes=1),
            now_utc,
        ]

        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=case_id,
            device_id=device_id,
            wearable_id=wearable_id,
            mapping_id=mapping_id,
            context_id=context_id,
            dot_dependency_file_id=heart_rate_dot_id,
            timestamp=timestamps[0],
            fields={"heart_rate": 71},
            other_tags={"sensor_type": "ecg"},
        )
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=case_id,
            device_id=device_id,
            wearable_id=wearable_id,
            mapping_id=mapping_id,
            context_id=context_id,
            dot_dependency_file_id=resp_rate_dot_id,
            timestamp=timestamps[1],
            fields={"resp_rate": 19},
            other_tags={"sensor_type": "ecg"},
        )
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=case_id,
            device_id=device_id,
            wearable_id=wearable_id,
            mapping_id=mapping_id,
            context_id=context_id,
            dot_dependency_file_id=heart_rate_dot_id,
            timestamp=timestamps[2],
            fields={"heart_rate": 73},
            other_tags={"sensor_type": "ecg"},
        )

        query = """
            query Telemetry(
                $measurement: String!,
                $patientId: String!,
                $dotDependencyFileIds: [UUID!]!,
                $end: AwareDateTime
            ) {
                telemetry(
                    query: {
                        measurement: $measurement
                        tags: [
                            { key: "patient_id", match: { value: $patientId } }
                            { key: "sensor_type", match: { value: "ecg" } }
                        ]
                        dotDependencyFileIds: $dotDependencyFileIds
                        limit: 2
                        end: $end
                    }
                ) {
                    items {
                        timestamp
                        measurement
                        tags
                        fields
                    }
                    hasMore
                    nextEnd
                }
            }
        """

        async def fetch_first_page():
            response = await integration_client.post(
                "/graphql",
                json={
                    "query": query,
                    "variables": {
                        "measurement": measurement,
                        "patientId": patient_id,
                        "dotDependencyFileIds": [heart_rate_dot_id, resp_rate_dot_id],
                        "end": (timestamps[2] + timedelta(minutes=1)).isoformat(),
                    },
                },
            )
            payload = _assert_graphql_ok(response)
            telemetry = payload["data"]["telemetry"]
            return telemetry if telemetry["items"] else None

        first_page = await _eventually(fetch_first_page)
        assert first_page is not None, "GraphQL Influx query did not return telemetry data"
        assert len(first_page["items"]) == 2
        assert first_page["hasMore"] is True
        assert first_page["nextEnd"] is not None

        async def fetch_second_page():
            response = await integration_client.post(
                "/graphql",
                json={
                    "query": query,
                    "variables": {
                        "measurement": measurement,
                        "patientId": patient_id,
                        "dotDependencyFileIds": [heart_rate_dot_id, resp_rate_dot_id],
                        "end": first_page["nextEnd"],
                    },
                },
            )
            payload = _assert_graphql_ok(response)
            telemetry = payload["data"]["telemetry"]
            return telemetry if telemetry["items"] else None

        second_page = await _eventually(fetch_second_page)
        assert second_page is not None, "GraphQL Influx second page did not return data"
        assert len(second_page["items"]) == 1
        assert second_page["hasMore"] is False

        merged_items = first_page["items"] + second_page["items"]
        assert {item["tags"]["dot_dependency_file_id"] for item in merged_items} == {
            heart_rate_dot_id,
            resp_rate_dot_id,
        }
        assert all(item["measurement"] == measurement for item in merged_items)

    async def test_influx_db_introspection_reports_measurements_tags_and_fields(self, integration_client: AsyncClient):
        measurement = f"gql_introspect_{uuid7().hex[:10]}"
        patient_id = str(uuid7())
        heart_rate_dot_id = str(uuid7())
        resp_rate_dot_id = str(uuid7())
        now_utc = datetime.now(UTC).replace(microsecond=0)

        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=str(uuid7()),
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=str(uuid7()),
            context_id=str(uuid7()),
            dot_dependency_file_id=heart_rate_dot_id,
            timestamp=now_utc - timedelta(minutes=1),
            fields={"heart_rate": 68},
            other_tags={"sensor_type": "ecg"},
        )
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=str(uuid7()),
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=str(uuid7()),
            context_id=str(uuid7()),
            dot_dependency_file_id=resp_rate_dot_id,
            timestamp=now_utc,
            fields={"resp_rate": 19},
            other_tags={"sensor_type": "ppg"},
        )

        measurement_query = """
            query InfluxMeasurementIntrospection($measurement: String!) {
                influxDbIntrospection(
                    measurement: $measurement
                    includeTagValues: true
                    tagValueLimit: 50
                ) {
                    bucket
                    measurements {
                        measurement
                        tagKeys
                        fieldKeys
                        tags {
                            key
                            values
                        }
                    }
                }
            }
        """

        async def fetch_measurement_introspection():
            response = await integration_client.post(
                "/graphql",
                json={"query": measurement_query, "variables": {"measurement": measurement}},
            )
            payload = _assert_graphql_ok(response)

            introspection = payload["data"]["influxDbIntrospection"]
            measurements = introspection["measurements"]
            if not measurements:
                return None

            measurement_info = measurements[0]
            field_keys = set(measurement_info["fieldKeys"])
            tag_values_by_key = {tag["key"]: set(tag["values"]) for tag in measurement_info["tags"]}
            if {"heart_rate", "resp_rate"}.issubset(field_keys) and {"ecg", "ppg"}.issubset(
                tag_values_by_key.get("sensor_type", set())
            ):
                return introspection
            return None

        introspection = await _eventually(fetch_measurement_introspection)
        assert introspection is not None, "Influx measurement introspection did not expose expected schema details"
        assert introspection["bucket"] == settings.INFLUX_BUCKET
        assert len(introspection["measurements"]) == 1
        measurement_info = introspection["measurements"][0]
        assert measurement_info["measurement"] == measurement
        required_tag_keys = {
            "patient_id",
            "case_id",
            "device_id",
            "wearable_id",
            "mapping_id",
            "context_id",
            "dot_dependency_file_id",
        }
        assert required_tag_keys.issubset(set(measurement_info["tagKeys"]))
        assert {"heart_rate", "resp_rate"}.issubset(set(measurement_info["fieldKeys"]))

        all_query = """
            query InfluxAllMeasurements {
                influxDbIntrospection(includeTagValues: false) {
                    measurements {
                        measurement
                        tags {
                            key
                            values
                        }
                    }
                }
            }
        """
        all_response = await integration_client.post("/graphql", json={"query": all_query})
        all_payload = _assert_graphql_ok(all_response)
        all_measurements = {
            item["measurement"] for item in all_payload["data"]["influxDbIntrospection"]["measurements"]
        }
        assert measurement in all_measurements
        matching_measurements = [
            item
            for item in all_payload["data"]["influxDbIntrospection"]["measurements"]
            if item["measurement"] == measurement
        ]
        assert len(matching_measurements) == 1
        assert all(tag["values"] == [] for tag in matching_measurements[0]["tags"])

    async def test_influx_db_introspection_rejects_invalid_arguments(self, integration_client: AsyncClient):
        invalid_measurement_query = """
            query InvalidMeasurement {
                influxDbIntrospection(measurement: "   ") {
                    bucket
                }
            }
        """
        invalid_measurement_response = await integration_client.post(
            "/graphql",
            json={"query": invalid_measurement_query},
        )
        invalid_measurement_payload = _assert_graphql_error(invalid_measurement_response)
        invalid_measurement_message = invalid_measurement_payload["errors"][0]["message"]
        assert "measurement must be a non-empty string" in invalid_measurement_message

        invalid_tag_limit_query = """
            query InvalidTagLimit {
                influxDbIntrospection(tagValueLimit: 0) {
                    bucket
                }
            }
        """
        invalid_tag_limit_response = await integration_client.post(
            "/graphql",
            json={"query": invalid_tag_limit_query},
        )
        invalid_tag_limit_payload = _assert_graphql_error(invalid_tag_limit_response)
        invalid_tag_limit_message = invalid_tag_limit_payload["errors"][0]["message"]
        assert "tag_value_limit" in invalid_tag_limit_message
        assert ">= 1" in invalid_tag_limit_message

    async def test_graphql_rejects_ilike_on_non_string_field(self, integration_client: AsyncClient):
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

        response = await integration_client.post("/graphql", json={"query": query})
        payload = _assert_graphql_error(response)
        assert "Filter operator ILIKE" in payload["errors"][0]["message"]
        assert "only supported for string fields" in payload["errors"][0]["message"]
        assert "Case" in payload["errors"][0]["message"]

    async def test_graphql_rejects_legacy_dot_dependency_file_ids(self, integration_client: AsyncClient):
        query = """
            query {
                telemetry(query: {
                    measurement: "sensor_readings"
                    dotDependencyFileIds: ["heart_rate"]
                    limit: 5
                }) {
                    items { measurement }
                }
            }
        """

        response = await integration_client.post("/graphql", json={"query": query})
        payload = _assert_graphql_error(response)
        assert "UUID" in payload["errors"][0]["message"]

    async def test_telemetry_subscription_stream_with_real_influx(
        self,
        integration_client: AsyncClient,
        integration_db_session: AsyncSession,
        integration_influx_client,
    ):
        from app.db.influx.telemetry import TelemetryRepo
        from app.graphql.context import GraphQLContext
        from app.graphql.dataloaders import Loaders
        from app.graphql.schema import schema
        from app.services.telemetry_service import TelemetryService

        measurement = f"gql_stream_{uuid7().hex[:10]}"
        patient_id = str(uuid7())
        heart_rate_dot_id = str(uuid7())
        now_utc = datetime.now(UTC).replace(microsecond=0)

        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=str(uuid7()),
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=str(uuid7()),
            context_id=str(uuid7()),
            dot_dependency_file_id=heart_rate_dot_id,
            timestamp=now_utc - timedelta(minutes=1),
            fields={"heart_rate": 68},
            other_tags={"sensor_type": "ecg"},
        )
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient_id,
            case_id=str(uuid7()),
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=str(uuid7()),
            context_id=str(uuid7()),
            dot_dependency_file_id=heart_rate_dot_id,
            timestamp=now_utc,
            fields={"heart_rate": 72},
            other_tags={"sensor_type": "ecg"},
        )

        # Wait for writes to be queryable before opening the subscription stream.
        warmup_query = """
            query Warmup($measurement: String!, $patientId: String!) {
                telemetry(
                    query: {
                        measurement: $measurement
                        tags: [{ key: "patient_id", match: { value: $patientId } }]
                        limit: 2
                    }
                ) {
                    items { tags }
                }
            }
        """

        async def fetch_warmup_items():
            response = await integration_client.post(
                "/graphql",
                json={"query": warmup_query, "variables": {"measurement": measurement, "patientId": patient_id}},
            )
            payload = _assert_graphql_ok(response)
            items = payload["data"]["telemetry"]["items"]
            return items if len(items) == 2 else None

        assert await _eventually(fetch_warmup_items) is not None

        subscription = """
            subscription StreamTelemetry($measurement: String!, $patientId: String!) {
                telemetryStream(
                    query: {
                        measurement: $measurement
                        tags: [{ key: "patient_id", match: { value: $patientId } }]
                        limit: 2
                    }
                ) {
                    measurement
                    tags
                    fields
                }
            }
        """

        session_factory = async_sessionmaker(
            integration_db_session.bind,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        db_semaphore = asyncio.Semaphore(1)
        result = await schema.subscribe(
            subscription,
            variable_values={"measurement": measurement, "patientId": patient_id},
            context_value=GraphQLContext(
                session_factory=session_factory,
                db_semaphore=db_semaphore,
                loaders=Loaders(session_factory, db_semaphore),
                telemetry_service=TelemetryService(TelemetryRepo(integration_influx_client)),
            ),
        )

        assert hasattr(result, "__aiter__"), "Expected an async event stream"

        first_event = await anext(result)
        second_event = await anext(result)

        assert first_event.errors is None
        assert second_event.errors is None
        assert first_event.data is not None
        assert second_event.data is not None

        first_payload = first_event.data["telemetryStream"]
        second_payload = second_event.data["telemetryStream"]

        assert first_payload["measurement"] == measurement
        assert second_payload["measurement"] == measurement
        assert first_payload["tags"]["patient_id"] == patient_id
        assert second_payload["tags"]["patient_id"] == patient_id
        assert first_payload["tags"]["dot_dependency_file_id"] == heart_rate_dot_id
        assert second_payload["tags"]["dot_dependency_file_id"] == heart_rate_dot_id
        assert first_payload["fields"]["heart_rate"] == 72
        assert second_payload["fields"]["heart_rate"] == 68

        with pytest.raises(StopAsyncIteration):
            await anext(result)

    async def test_cross_db_query_postgres_and_influx_in_single_operation(self, integration_client: AsyncClient):
        spo2_dot_id = str(uuid7())
        patient = await _create_patient_helper(integration_client, name="GraphQL CrossDB Patient")
        case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")

        measurement = f"gql_crossdb_{uuid7().hex[:10]}"
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=patient.id,
            case_id=case.id,
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=str(uuid7()),
            context_id=str(uuid7()),
            dot_dependency_file_id=spo2_dot_id,
            timestamp=datetime.now(UTC).replace(microsecond=0),
            fields={"spo2": 98},
            other_tags={"sensor_type": "pulse_ox"},
        )

        query = """
            query Mixed($patientNodeId: ID!, $measurement: String!, $patientTag: String!) {
                node(id: $patientNodeId) {
                    ... on Patient {
                        id
                        name
                        cases(first: 10) {
                            edges {
                                node {
                                    id
                                    status
                                }
                            }
                        }
                    }
                }
                telemetry(
                    query: {
                        measurement: $measurement
                        tags: [{ key: "patient_id", match: { value: $patientTag } }]
                        limit: 5
                    }
                ) {
                    items {
                        tags
                        fields
                    }
                    hasMore
                }
            }
        """

        async def fetch_mixed_payload():
            response = await integration_client.post(
                "/graphql",
                json={
                    "query": query,
                    "variables": {
                        "patientNodeId": _relay_global_id("Patient", str(patient.id)),
                        "measurement": measurement,
                        "patientTag": str(patient.id),
                    },
                },
            )
            payload = _assert_graphql_ok(response)
            telemetry_items = payload["data"]["telemetry"]["items"]
            return payload if telemetry_items else None

        payload = await _eventually(
            fetch_mixed_payload,
            message="Cross-db GraphQL query did not return the written telemetry point",
        )
        assert payload is not None, "Cross-db GraphQL query did not return telemetry data"

        patient_node = payload["data"]["node"]
        assert _relay_node_id(patient_node["id"]) == str(patient.id)
        assert patient_node["name"] == "GraphQL CrossDB Patient"
        assert {_relay_node_id(edge["node"]["id"]) for edge in patient_node["cases"]["edges"]} == {str(case.id)}

        telemetry_items = payload["data"]["telemetry"]["items"]
        assert len(telemetry_items) == 1
        assert payload["data"]["telemetry"]["hasMore"] is False
        telemetry_item = telemetry_items[0]
        assert telemetry_item["tags"]["patient_id"] == str(patient.id)
        assert telemetry_item["tags"]["case_id"] == str(case.id)
        assert telemetry_item["tags"]["dot_dependency_file_id"] == spo2_dot_id
        assert telemetry_item["tags"]["sensor_type"] == "pulse_ox"
        assert telemetry_item["fields"] == {"spo2": 98}

    async def test_cross_db_patient_filter_with_arbitrary_tag_in(self, integration_client: AsyncClient):
        heart_rate_dot_id = str(uuid7())
        older_patient = await _create_patient_helper(
            integration_client,
            name="CrossDB Older Patient",
            dob="1960-01-01",
        )
        younger_patient = await _create_patient_helper(
            integration_client,
            name="CrossDB Younger Patient",
            dob="2010-01-01",
        )

        measurement = f"gql_age_in_{uuid7().hex[:10]}"
        common = {
            "measurement": measurement,
            "dot_dependency_file_id": heart_rate_dot_id,
            "case_id": str(uuid7()),
            "device_id": str(uuid7()),
            "wearable_id": str(uuid7()),
            "mapping_id": str(uuid7()),
            "context_id": str(uuid7()),
        }

        now_utc = datetime.now(UTC).replace(microsecond=0)
        await _record_telemetry_helper(
            integration_client,
            patient_id=older_patient.id,
            timestamp=now_utc - timedelta(minutes=1),
            fields={"heart_rate": 72},
            other_tags={"sensor_type": "ecg"},
            **common,
        )
        await _record_telemetry_helper(
            integration_client,
            patient_id=younger_patient.id,
            timestamp=now_utc,
            fields={"heart_rate": 74},
            other_tags={"sensor_type": "ppg"},
            **common,
        )

        query = """
            query CrossDbAgeIn($measurement: String!) {
                telemetry(
                    query: {
                        measurement: $measurement
                        patientFilter: {
                            condition: {
                                field: "dob"
                                op: LTE
                                value: { date: "1976-01-01" }
                            }
                        }
                        tags: [{ key: "sensor_type", match: { values: ["ecg", "ppg"] } }]
                        limit: 20
                    }
                ) {
                    items {
                        tags
                        fields
                    }
                    hasMore
                }
            }
        """

        async def fetch_page():
            response = await integration_client.post(
                "/graphql",
                json={"query": query, "variables": {"measurement": measurement}},
            )
            payload = _assert_graphql_ok(response)
            telemetry = payload["data"]["telemetry"]
            return telemetry if telemetry["items"] else None

        page = await _eventually(
            fetch_page,
            message="Cross-db patient filter did not return the expected older patient telemetry point",
        )
        assert page is not None, "Cross-db filtered GraphQL telemetry query returned no data"
        assert len(page["items"]) == 1
        assert page["hasMore"] is False
        item = page["items"][0]
        assert item["tags"]["patient_id"] == str(older_patient.id)
        assert item["tags"]["dot_dependency_file_id"] == heart_rate_dot_id
        assert item["tags"]["sensor_type"] == "ecg"
        assert item["fields"] == {"heart_rate": 72}

    async def test_cross_db_patient_filter_can_return_resolved_metadata(self, integration_client: AsyncClient):
        heart_rate_dot_id = str(uuid7())
        older_patient = await _create_patient_helper(
            integration_client,
            name="Resolved Older Patient",
            dob="1960-01-01",
        )
        await _create_patient_helper(
            integration_client,
            name="Resolved Younger Patient",
            dob="2010-01-01",
        )

        measurement = f"gql_resolved_{uuid7().hex[:10]}"
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=older_patient.id,
            case_id=str(uuid7()),
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=str(uuid7()),
            context_id=str(uuid7()),
            dot_dependency_file_id=heart_rate_dot_id,
            timestamp=datetime.now(UTC).replace(microsecond=0),
            fields={"heart_rate": 70},
            other_tags={"sensor_type": "ecg"},
        )

        query = """
            query CrossDbResolved($measurement: String!) {
                telemetry(
                    query: {
                        measurement: $measurement
                        patientFilter: {
                            condition: {
                                field: "dob"
                                op: LTE
                                value: { date: "1976-01-01" }
                            }
                        }
                        includeResolvedMetadata: true
                        limit: 20
                    }
                ) {
                    items {
                        tags
                    }
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

        async def fetch_page():
            response = await integration_client.post(
                "/graphql",
                json={"query": query, "variables": {"measurement": measurement}},
            )
            payload = _assert_graphql_ok(response)
            telemetry = payload["data"]["telemetry"]
            return telemetry if telemetry["items"] else None

        page = await _eventually(
            fetch_page,
            message="Cross-db resolved metadata query did not return the expected patient telemetry point",
        )
        assert page is not None, "Cross-db resolved metadata query returned no telemetry data"
        assert len(page["items"]) == 1
        assert page["hasMore"] is False
        assert page["items"][0]["tags"]["patient_id"] == str(older_patient.id)
        assert page["items"][0]["tags"]["dot_dependency_file_id"] == heart_rate_dot_id
        assert page["resolved"] is not None
        assert len(page["resolved"]["patients"]) == 1
        assert _relay_node_id(page["resolved"]["patients"][0]["id"]) == str(older_patient.id)
        assert page["resolved"]["patients"][0]["name"] == "Resolved Older Patient"

    async def test_cross_db_device_filter_with_arbitrary_tag_in(self, integration_client: AsyncClient):
        spo2_dot_id = str(uuid7())
        patient = await _create_patient_helper(integration_client, name="CrossDB Device Filter Patient")
        case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        target_device = await _create_device(integration_client, serial_nr=f"TARGET-{uuid7().hex[:8]}")
        other_device = await _create_device(integration_client, serial_nr=f"OTHER-{uuid7().hex[:8]}")

        measurement = f"gql_device_in_{uuid7().hex[:10]}"
        common = {
            "measurement": measurement,
            "patient_id": str(patient.id),
            "case_id": str(case.id),
            "wearable_id": str(uuid7()),
            "mapping_id": str(uuid7()),
            "context_id": str(uuid7()),
            "dot_dependency_file_id": spo2_dot_id,
        }
        now_utc = datetime.now(UTC).replace(microsecond=0)
        await _record_telemetry_helper(
            integration_client,
            device_id=target_device.id,
            timestamp=now_utc - timedelta(minutes=1),
            fields={"spo2": 98},
            other_tags={"sensor_type": "pulse_ox"},
            **common,
        )
        await _record_telemetry_helper(
            integration_client,
            device_id=other_device.id,
            timestamp=now_utc,
            fields={"spo2": 95},
            other_tags={"sensor_type": "ecg"},
            **common,
        )

        query = """
            query CrossDbDeviceIn($measurement: String!) {
                telemetry(
                    query: {
                        measurement: $measurement
                        deviceFilter: {
                            condition: {
                                field: "serial_nr"
                                op: ILIKE
                                value: { string: "%TARGET%" }
                            }
                        }
                        tags: [{ key: "sensor_type", match: { values: ["pulse_ox", "ecg"] } }]
                        limit: 20
                    }
                ) {
                    items {
                        tags
                        fields
                    }
                    hasMore
                }
            }
        """

        async def fetch_page():
            response = await integration_client.post(
                "/graphql",
                json={"query": query, "variables": {"measurement": measurement}},
            )
            payload = _assert_graphql_ok(response)
            telemetry = payload["data"]["telemetry"]
            return telemetry if telemetry["items"] else None

        page = await _eventually(
            fetch_page,
            message="Cross-db device filter did not return the expected target device telemetry point",
        )
        assert page is not None, "Cross-db device-filter GraphQL telemetry query returned no data"
        assert len(page["items"]) == 1
        assert page["hasMore"] is False
        item = page["items"][0]
        assert item["tags"]["device_id"] == str(target_device.id)
        assert item["tags"]["dot_dependency_file_id"] == spo2_dot_id
        assert item["tags"]["sensor_type"] == "pulse_ox"
        assert item["fields"] == {"spo2": 98}

    async def test_cross_db_mapping_filter_can_return_full_mapping_json(self, integration_client: AsyncClient):
        mapping_payload = {
            "resourceType": "Observation",
            "map": {"spo2": "valueQuantity.value"},
        }
        mapping_response = await integration_client.post(
            "/fhir-mappings/",
            json={
                "version": f"gql-map-{uuid7().hex[:8]}",
                "full_mapping": mapping_payload,
            },
        )
        mapping = _assert_json_response(mapping_response, status_code=201)

        measurement = f"gql_map_json_{uuid7().hex[:10]}"
        spo2_dot_id = str(uuid7())
        await _record_telemetry_helper(
            integration_client,
            measurement=measurement,
            patient_id=str(uuid7()),
            case_id=str(uuid7()),
            device_id=str(uuid7()),
            wearable_id=str(uuid7()),
            mapping_id=mapping["id"],
            context_id=str(uuid7()),
            dot_dependency_file_id=spo2_dot_id,
            timestamp=datetime.now(UTC).replace(microsecond=0),
            fields={"spo2": 97},
            other_tags={"sensor_type": "pulse_ox"},
        )

        query = """
            query CrossDbMappingJson($measurement: String!, $version: String!) {
                telemetry(
                    query: {
                        measurement: $measurement
                        mappingFilter: {
                            condition: {
                                field: "version"
                                op: EQ
                                value: { string: $version }
                            }
                        }
                        includeResolvedMetadata: true
                        limit: 20
                    }
                ) {
                    items {
                        tags
                    }
                    hasMore
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

        async def fetch_page():
            response = await integration_client.post(
                "/graphql",
                json={
                    "query": query,
                    "variables": {
                        "measurement": measurement,
                        "version": mapping["version"],
                    },
                },
            )
            payload = _assert_graphql_ok(response)
            telemetry = payload["data"]["telemetry"]
            return telemetry if telemetry["items"] else None

        page = await _eventually(
            fetch_page,
            message="Cross-db mapping filter did not return the expected mapping telemetry point",
        )
        assert page is not None, "Cross-db mapping-filter GraphQL telemetry query returned no data"
        assert len(page["items"]) == 1
        assert page["hasMore"] is False
        assert page["items"][0]["tags"]["mapping_id"] == mapping["id"]
        assert page["items"][0]["tags"]["dot_dependency_file_id"] == spo2_dot_id
        assert page["resolved"] is not None
        assert len(page["resolved"]["mappings"]) == 1
        assert _relay_node_id(page["resolved"]["mappings"][0]["id"]) == mapping["id"]
        assert page["resolved"]["mappings"][0]["version"] == mapping["version"]
        assert page["resolved"]["mappings"][0]["fullMapping"] == mapping_payload
