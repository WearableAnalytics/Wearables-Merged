from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from httpx import AsyncClient

from app.schemas.device import DeviceResponse
from app.schemas.wearable import WearableResponse
from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.api import assert_no_content as _assert_no_content
from tests.helpers.api import create_case as _create_case
from tests.helpers.api import create_device as _create_device
from tests.helpers.api import create_patient as _create_patient
from tests.helpers.api import create_wearable as _create_wearable

pytestmark = pytest.mark.anyio


@dataclass(frozen=True)
class _HardwareCase:
    resource_path: str
    resource_id_key: str
    model: str
    hour: int


async def _create_hardware(
    client: AsyncClient,
    hardware_case: _HardwareCase,
    *,
    status: str = "AVAILABLE",
) -> DeviceResponse | WearableResponse:
    serial_nr = f"{hardware_case.resource_path.upper()}-{uuid7().hex[:10]}"
    if hardware_case.resource_path == "devices":
        return await _create_device(client, serial_nr=serial_nr, model=hardware_case.model, status=status)
    return await _create_wearable(client, serial_nr=serial_nr, model=hardware_case.model, status=status)


@pytest.mark.parametrize(
    "hardware_case",
    [
        pytest.param(_HardwareCase("devices", "device_id", "Device", 0), id="devices"),
        pytest.param(_HardwareCase("wearables", "wearable_id", "Wearable", 1), id="wearables"),
    ],
)
async def test_hardware_assignment_lifecycle_integration(
    integration_client: AsyncClient,
    hardware_case: _HardwareCase,
):
    patient = await _create_patient(integration_client, name=f"{hardware_case.model} Lifecycle Patient")
    case = await _create_case(integration_client, patient_id=patient.id, status="PLANNED")
    hardware = await _create_hardware(integration_client, hardware_case)

    assign_resp = await integration_client.post(f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}")
    assigned = _assert_json_response(assign_resp, status_code=201)
    assert assigned["case_id"] == str(case.id)
    assert assigned[hardware_case.resource_id_key] == str(hardware.id)
    assert assigned["assigned_to"] is None

    unassign_last_resp = await integration_client.delete(f"/cases/{case.id}/{hardware_case.resource_path}/last")
    _assert_no_content(unassign_last_resp)

    assign_resp_2 = await integration_client.post(f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}")
    assigned_2 = _assert_json_response(assign_resp_2, status_code=201)

    hard_delete_resp = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}/assignments",
        params={"assigned_from": assigned_2["assigned_from"]},
    )
    _assert_no_content(hard_delete_resp)

    hardware_resp = await integration_client.get(f"/{hardware_case.resource_path}/{hardware.id}")
    assert _assert_json_response(hardware_resp, status_code=200)["status"] == "AVAILABLE"


@pytest.mark.parametrize(
    "hardware_case",
    [
        pytest.param(_HardwareCase("devices", "device_id", "Specific Device", 0), id="devices"),
        pytest.param(_HardwareCase("wearables", "wearable_id", "Specific Wearable", 1), id="wearables"),
    ],
)
async def test_unassign_hardware_by_specific_route_integration(
    integration_client: AsyncClient,
    hardware_case: _HardwareCase,
):
    patient = await _create_patient(integration_client, name=f"{hardware_case.model} Patient")
    case = await _create_case(integration_client, patient_id=patient.id, status="ONGOING")
    hardware = await _create_hardware(integration_client, hardware_case)

    assign_response = await integration_client.post(f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}")
    _assert_json_response(assign_response, status_code=201)

    unassign_response = await integration_client.delete(f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}")
    _assert_no_content(unassign_response)

    unassign_again_response = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}"
    )
    _assert_api_error(unassign_again_response, status_code=404, code="not_found")

    hardware_response = await integration_client.get(f"/{hardware_case.resource_path}/{hardware.id}")
    assert _assert_json_response(hardware_response, status_code=200)["status"] == "AVAILABLE"


@pytest.mark.parametrize(
    "hardware_case",
    [
        pytest.param(_HardwareCase("devices", "device_id", "Future Device", 0), id="devices"),
        pytest.param(_HardwareCase("wearables", "wearable_id", "Future Wearable", 1), id="wearables"),
    ],
)
async def test_future_assignment_does_not_mark_hardware_assigned_integration(
    integration_client: AsyncClient,
    hardware_case: _HardwareCase,
):
    patient = await _create_patient(integration_client, name=f"{hardware_case.model} Patient")
    case = await _create_case(integration_client, patient_id=patient.id, status="ONGOING")
    hardware = await _create_hardware(integration_client, hardware_case)

    start_time = (datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)).isoformat()
    assign_response = await integration_client.post(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}",
        params={"start_time": start_time},
    )
    _assert_json_response(assign_response, status_code=201)

    hardware_response = await integration_client.get(f"/{hardware_case.resource_path}/{hardware.id}")
    assert _assert_json_response(hardware_response, status_code=200)["status"] == "AVAILABLE"


@pytest.mark.parametrize(
    "hardware_case",
    [
        pytest.param(_HardwareCase("devices", "device_id", "Broken Device", 0), id="devices"),
        pytest.param(_HardwareCase("wearables", "wearable_id", "Broken Wearable", 1), id="wearables"),
    ],
)
async def test_unassign_preserves_non_assigned_hardware_status_integration(
    integration_client: AsyncClient,
    hardware_case: _HardwareCase,
):
    patient = await _create_patient(integration_client, name=f"{hardware_case.model} Patient")
    case = await _create_case(integration_client, patient_id=patient.id, status="ONGOING")
    hardware = await _create_hardware(integration_client, hardware_case)

    assign_response = await integration_client.post(f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}")
    _assert_json_response(assign_response, status_code=201)

    patch_response = await integration_client.patch(
        f"/{hardware_case.resource_path}/{hardware.id}",
        json={"status": "BROKEN"},
    )
    _assert_json_response(patch_response, status_code=200)

    unassign_response = await integration_client.delete(f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}")
    _assert_no_content(unassign_response)

    hardware_response = await integration_client.get(f"/{hardware_case.resource_path}/{hardware.id}")
    assert _assert_json_response(hardware_response, status_code=200)["status"] == "BROKEN"


@pytest.mark.parametrize(
    "hardware_case",
    [
        pytest.param(_HardwareCase("devices", "device_id", "Future Delete Device", 0), id="devices"),
        pytest.param(_HardwareCase("wearables", "wearable_id", "Future Delete Wearable", 1), id="wearables"),
    ],
)
async def test_delete_future_assignment_keeps_hardware_available_integration(
    integration_client: AsyncClient,
    hardware_case: _HardwareCase,
):
    patient = await _create_patient(integration_client, name=f"{hardware_case.model} Patient")
    case = await _create_case(integration_client, patient_id=patient.id, status="ONGOING")
    hardware = await _create_hardware(integration_client, hardware_case)

    start_time = (datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)).isoformat()
    assign_response = await integration_client.post(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}",
        params={"start_time": start_time},
    )
    assigned = _assert_json_response(assign_response, status_code=201)

    delete_response = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}/assignments",
        params={"assigned_from": assigned["assigned_from"]},
    )
    _assert_no_content(delete_response)

    hardware_response = await integration_client.get(f"/{hardware_case.resource_path}/{hardware.id}")
    assert _assert_json_response(hardware_response, status_code=200)["status"] == "AVAILABLE"


@pytest.mark.parametrize(
    "hardware_case",
    [
        pytest.param(_HardwareCase("devices", "device_id", "Ambiguous Device", 0), id="devices"),
        pytest.param(_HardwareCase("wearables", "wearable_id", "Ambiguous Wearable", 1), id="wearables"),
    ],
)
async def test_assignment_delete_reports_ambiguity_without_assigned_from_integration(
    integration_client: AsyncClient,
    hardware_case: _HardwareCase,
):
    patient = await _create_patient(integration_client, name=f"{hardware_case.model} Patient")
    case = await _create_case(integration_client, patient_id=patient.id, status="ONGOING")
    hardware = await _create_hardware(integration_client, hardware_case)

    def _timestamp(minute: int) -> str:
        return f"2026-01-01T{hardware_case.hour:02d}:{minute:02d}:00+00:00"

    assign_one = await integration_client.post(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}",
        params={"start_time": _timestamp(0)},
    )
    assign_one_payload = _assert_json_response(assign_one, status_code=201)

    unassign_one = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}",
        params={"end_time": _timestamp(5)},
    )
    _assert_no_content(unassign_one)

    assign_two = await integration_client.post(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}",
        params={"start_time": _timestamp(10)},
    )
    assign_two_payload = _assert_json_response(assign_two, status_code=201)

    unassign_two = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}",
        params={"end_time": _timestamp(15)},
    )
    _assert_no_content(unassign_two)

    ambiguous_delete = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}/assignments"
    )
    ambiguous_payload = _assert_api_error(ambiguous_delete, status_code=404)
    detail = ambiguous_payload["detail"]
    if hardware_case.resource_path == "devices":
        assert "Device assignment" in detail
    else:
        assert "Wearable assignment" in detail
    assert "assigned_from" in detail
    assert "ambiguous" in detail

    delete_one = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}/assignments",
        params={"assigned_from": assign_one_payload["assigned_from"]},
    )
    _assert_no_content(delete_one)

    delete_two = await integration_client.delete(
        f"/cases/{case.id}/{hardware_case.resource_path}/{hardware.id}/assignments",
        params={"assigned_from": assign_two_payload["assigned_from"]},
    )
    _assert_no_content(delete_two)
