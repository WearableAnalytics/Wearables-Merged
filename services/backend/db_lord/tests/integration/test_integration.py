from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest
from httpx import AsyncClient

from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.api import create_case as _create_case_helper
from tests.helpers.api import create_device as _create_device_helper
from tests.helpers.api import create_patient as _create_patient_helper

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


class TestEndpointLevelIntegration:
    async def test_create_patient_returns_recent_uuidv7(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(
            integration_client,
            name="Endpoint UUID Patient",
            charite_id=uuid7(),
        )

        patient_id = UUID(str(patient.id))
        # first 6 bytes of UUIDv7 are the timestamp
        timestamp_ms = int.from_bytes(patient_id.bytes[:6], "big")
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        # The timestamp embedded in the UUID should be within the last minute to ensure its actually recent
        assert now_ms - timestamp_ms < 60_000

    async def test_duplicate_active_device_assignment_returns_endpoint_error(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="Endpoint Assignment Patient")
        case_one = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        case_two = await _create_case_helper(integration_client, patient_id=patient.id, status="PLANNED")
        device = await _create_device_helper(
            integration_client,
            serial_nr=f"ENDPOINT-DEV-{uuid7().hex[:8]}",
            model="Endpoint Assignment Device",
        )

        first_assignment_response = await integration_client.post(f"/cases/{case_one.id}/devices/{device.id}")
        first_assignment = _assert_json_response(first_assignment_response, status_code=201)
        assert first_assignment["case_id"] == str(case_one.id)
        assert first_assignment["device_id"] == str(device.id)

        duplicate_assignment_response = await integration_client.post(f"/cases/{case_two.id}/devices/{device.id}")
        duplicate_assignment = _assert_api_error(duplicate_assignment_response, status_code=400, code="bad_request")
        detail = duplicate_assignment["detail"]
        assert "Device is not available" in detail
        assert "ASSIGNED" in detail

    async def test_assignment_endpoints_return_timezone_aware_timestamps(self, integration_client: AsyncClient):
        patient = await _create_patient_helper(integration_client, name="Endpoint Timezone Patient")
        case = await _create_case_helper(integration_client, patient_id=patient.id, status="ONGOING")
        device = await _create_device_helper(
            integration_client,
            serial_nr=f"ENDPOINT-TZ-{uuid7().hex[:8]}",
            model="Endpoint Timezone Device",
        )

        assign_response = await integration_client.post(f"/cases/{case.id}/devices/{device.id}")
        assignment = _assert_json_response(assign_response, status_code=201)

        assigned_from = datetime.fromisoformat(assignment["assigned_from"])
        assert assigned_from.tzinfo is not None

        active_response = await integration_client.get(f"/cases/{case.id}/devices/{device.id}/active-assignment")
        active_assignment = _assert_json_response(active_response, status_code=200)
        assert active_assignment == assignment
        assert datetime.fromisoformat(active_assignment["assigned_from"]).tzinfo is not None
