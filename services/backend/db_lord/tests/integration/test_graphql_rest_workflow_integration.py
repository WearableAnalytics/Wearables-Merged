from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import pytest
from httpx import AsyncClient

from app.schemas.case import CaseResponse
from app.schemas.context import ContextResponse
from app.schemas.device import DeviceResponse
from app.schemas.patient import PatientResponse
from app.schemas.wearable import WearableResponse
from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.api import assert_graphql_ok as _assert_graphql_ok
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.api import assert_no_content as _assert_no_content
from tests.helpers.api import create_case as _create_case_helper
from tests.helpers.api import create_context as _create_context_helper
from tests.helpers.api import create_device as _create_device_helper
from tests.helpers.api import create_patient as _create_patient_helper
from tests.helpers.api import create_wearable as _create_wearable_helper
from tests.helpers.api import record_telemetry as _record_telemetry
from tests.helpers.common import eventually as _eventually
from tests.helpers.common import relay_global_id as _relay_global_id
from tests.helpers.common import relay_node_id as _relay_node_id

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def _create_patient(client: AsyncClient, name: str) -> PatientResponse:
    return await _create_patient_helper(client, name=name, charite_id=uuid7())


async def _create_case(client: AsyncClient, patient_id: str, status: str = "ONGOING") -> CaseResponse:
    return await _create_case_helper(client, patient_id=patient_id, status=status)


async def _create_device(client: AsyncClient, serial_nr: str) -> DeviceResponse:
    return await _create_device_helper(client, serial_nr=serial_nr, model="Integration Device")


async def _create_wearable(client: AsyncClient, serial_nr: str) -> WearableResponse:
    return await _create_wearable_helper(client, serial_nr=serial_nr, model="Integration Wearable")


async def _create_context(client: AsyncClient, group_name: str) -> ContextResponse:
    return await _create_context_helper(client, group_name=group_name, coordinator="Test Coordinator")


class TestGraphQLWorkflowIntegration:
    async def test_graphql_real_postgres_and_influx(
        self,
        integration_client: AsyncClient,
    ):
        patient = await _create_patient(integration_client, "GraphQL Integration Patient")
        case = await _create_case(integration_client, str(patient.id), status="ONGOING")
        patient_node_id = _relay_global_id("Patient", str(patient.id))

        patient_query = f"""
            query {{
                node(id: "{patient_node_id}") {{
                    ... on Patient {{
                        id
                        name
                        cases(first: 10) {{
                            edges {{
                                node {{
                                    id
                                    status
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        """

        patient_response = await integration_client.post("/graphql", json={"query": patient_query})
        patient_body = _assert_graphql_ok(patient_response)

        patient_data = patient_body["data"]["node"]
        assert _relay_node_id(patient_data["id"]) == str(patient.id)
        assert patient_data["name"] == "GraphQL Integration Patient"
        assert {_relay_node_id(edge["node"]["id"]) for edge in patient_data["cases"]["edges"]} == {str(case.id)}

        measurement = f"it_graphql_{uuid7().hex[:10]}"
        dot_dependency_file_id = str(uuid7())
        await _record_telemetry(
            integration_client,
            measurement=measurement,
            patient_id=patient.id,
            case_id=case.id,
            device_id=uuid7(),
            wearable_id=uuid7(),
            mapping_id=uuid7(),
            dot_dependency_file_id=dot_dependency_file_id,
            timestamp=datetime.now(UTC).replace(microsecond=0),
            fields={"spo2": 98},
            other_tags={"sensor_type": "pulse_ox"},
        )

        telemetry_query = f"""
            query {{
                telemetry(query: {{
                    measurement: "{measurement}"
                    tags: [
                        {{ key: "patient_id", match: {{ value: "{patient.id}" }} }}
                        {{ key: "case_id", match: {{ value: "{case.id}" }} }}
                    ]
                    limit: 10
                }}) {{
                    items {{
                        measurement
                        tags
                        fields
                    }}
                    hasMore
                }}
            }}
        """

        async def fetch_graphql_telemetry() -> dict[str, Any] | None:
            response = await integration_client.post("/graphql", json={"query": telemetry_query})
            body = _assert_graphql_ok(response)
            payload = body["data"]["telemetry"]
            return payload if payload["items"] else None

        telemetry_page = await _eventually(
            fetch_graphql_telemetry,
            message="GraphQL telemetry query did not return the written REST telemetry point",
        )
        assert telemetry_page is not None, "GraphQL telemetry query did not return newly written data"
        assert len(telemetry_page["items"]) == 1
        assert telemetry_page["hasMore"] is False

        item = telemetry_page["items"][0]
        assert item["measurement"] == measurement
        assert item["tags"]["patient_id"] == str(patient.id)
        assert item["tags"]["case_id"] == str(case.id)
        assert item["tags"]["dot_dependency_file_id"] == dot_dependency_file_id
        assert item["fields"]["spo2"] == 98


class TestRestWorkflowIntegration:
    async def test_rest_unique_violation_returns_structured_error(self, integration_client: AsyncClient):
        duplicate_charite_id = str(uuid7())
        payload = {"charite_id": duplicate_charite_id, "name": "Dup Patient", "sex": "F"}

        first_response = await integration_client.post("/patients/", json=payload)
        _assert_json_response(first_response, status_code=201)

        duplicate_response = await integration_client.post("/patients/", json=payload)
        duplicate_payload = _assert_api_error(
            duplicate_response,
            status_code=409,
            code="unique_violation",
        )
        assert "already exists" in duplicate_payload["detail"]
        if "constraint" in duplicate_payload:
            assert duplicate_payload["constraint"] == "uq_patients_charite_id"
        assert "entity_type" not in duplicate_payload

    async def test_real_world_rest_assignment_workflow(self, integration_client: AsyncClient):
        patient = await _create_patient(integration_client, "REST Integration Patient")
        case = await _create_case(integration_client, str(patient.id), status="ONGOING")

        device = await _create_device(integration_client, serial_nr=f"DEV-{uuid7().hex[:10]}")
        wearable = await _create_wearable(integration_client, serial_nr=f"WEAR-{uuid7().hex[:10]}")
        context = await _create_context(integration_client, group_name="ICU-A")

        assign_device_response = await integration_client.post(f"/cases/{case.id}/devices/{device.id}")
        _assert_json_response(assign_device_response, status_code=201)

        assign_wearable_response = await integration_client.post(f"/cases/{case.id}/wearables/{wearable.id}")
        _assert_json_response(assign_wearable_response, status_code=201)

        link_context_response = await integration_client.post(f"/cases/{case.id}/contexts/{context.id}")
        _assert_json_response(link_context_response, status_code=201)

        second_case = await _create_case(integration_client, str(patient.id), status="PLANNED")
        conflict_response = await integration_client.post(f"/cases/{second_case.id}/devices/{device.id}")
        _assert_api_error(
            conflict_response,
            status_code=400,
            code="bad_request",
        )
        conflict_detail = conflict_response.json()["detail"]
        assert "Device is not available" in conflict_detail
        assert "ASSIGNED" in conflict_detail

        expanded_response = await integration_client.get(
            f"/cases/{case.id}/expanded",
            params=[
                ("expand", "patient"),
                ("expand", "devices"),
                ("expand", "wearables"),
                ("expand", "contexts"),
            ],
        )
        expanded = _assert_json_response(expanded_response, status_code=200)

        assert expanded["patient"]["id"] == str(patient.id)
        assert {item["id"] for item in expanded["contexts"]} == {str(context.id)}
        assert {item["device"]["id"] for item in expanded["devices"]} == {str(device.id)}
        assert {item["wearable"]["id"] for item in expanded["wearables"]} == {str(wearable.id)}

        device_response = await integration_client.get(f"/devices/{device.id}")
        assert _assert_json_response(device_response, status_code=200)["status"] == "ASSIGNED"

        wearable_response = await integration_client.get(f"/wearables/{wearable.id}")
        assert _assert_json_response(wearable_response, status_code=200)["status"] == "ASSIGNED"

        unassign_device_response = await integration_client.delete(f"/cases/{case.id}/devices/last")
        _assert_no_content(unassign_device_response)

        unassign_wearable_response = await integration_client.delete(f"/cases/{case.id}/wearables/last")
        _assert_no_content(unassign_wearable_response)

        unlink_context_response = await integration_client.delete(f"/cases/{case.id}/contexts/{context.id}")
        _assert_no_content(unlink_context_response)

        device_after_unassign = await integration_client.get(f"/devices/{device.id}")
        assert _assert_json_response(device_after_unassign, status_code=200)["status"] == "AVAILABLE"

        wearable_after_unassign = await integration_client.get(f"/wearables/{wearable.id}")
        assert _assert_json_response(wearable_after_unassign, status_code=200)["status"] == "AVAILABLE"

    async def test_rest_cursor_pagination_with_filters(self, integration_client: AsyncClient):
        expected_ids: set[str] = set()
        for i in range(7):
            sex = "F" if i % 2 == 0 else "M"
            response = await integration_client.post(
                "/patients/",
                json={
                    "charite_id": str(uuid7()),
                    "name": f"RealWorld Pagination Patient {i}",
                    "sex": sex,
                },
            )
            created = _assert_json_response(response, status_code=201)
            if sex == "F":
                expected_ids.add(created["id"])

        collected_ids: list[str] = []
        cursor: str | None = None

        for _ in range(10):
            response = await integration_client.get(
                "/patients/",
                params={
                    "size": 2,
                    "sex": "F",
                    "name__ilike": "%RealWorld Pagination%",
                    **({"cursor": cursor} if cursor else {}),
                },
            )
            page = _assert_json_response(response, status_code=200)

            items = page["items"]
            collected_ids.extend(item["id"] for item in items)
            assert all(item["sex"] == "F" for item in items)

            cursor = page["next_page"]
            if cursor is None:
                break
        else:
            raise AssertionError("Pagination did not terminate after expected number of pages")

        assert len(collected_ids) == len(set(collected_ids))
        assert set(collected_ids) == expected_ids
