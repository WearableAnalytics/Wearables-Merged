import pytest
from httpx import AsyncClient

from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.api import assert_no_content as _assert_no_content

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("resource_path", "factory_name", "factory_kwargs"),
    [
        pytest.param("patients", "patient_factory", {"name": "Delete Patient"}, id="patients"),
        pytest.param("devices", "device_factory", {"model": "Error Test Device"}, id="devices"),
        pytest.param("wearables", "wearable_factory", {"model": "Error Test Wearable"}, id="wearables"),
        pytest.param("contexts", "context_factory", {"group_name": "Ward A"}, id="contexts"),
    ],
)
async def test_entity_delete_and_missing_errors(
    client: AsyncClient,
    request: pytest.FixtureRequest,
    resource_path: str,
    factory_name: str,
    factory_kwargs: dict[str, str],
):
    factory = request.getfixturevalue(factory_name)
    entity = await factory(**factory_kwargs)

    delete_response = await client.delete(f"/{resource_path}/{entity['id']}")
    _assert_no_content(delete_response)

    get_response = await client.get(f"/{resource_path}/{entity['id']}")
    _assert_api_error(get_response, status_code=404, code="not_found")

    delete_again_response = await client.delete(f"/{resource_path}/{entity['id']}")
    _assert_api_error(delete_again_response, status_code=404, code="not_found")


async def test_case_delete_and_missing_errors(client: AsyncClient, patient_factory, case_factory):
    patient = await patient_factory(name="Delete Case Patient")
    case = await case_factory(patient_id=patient["id"])

    delete_response = await client.delete(f"/cases/{case['id']}")
    _assert_no_content(delete_response)

    get_response = await client.get(f"/cases/{case['id']}")
    _assert_api_error(get_response, status_code=404, code="not_found")

    delete_again_response = await client.delete(f"/cases/{case['id']}")
    _assert_api_error(delete_again_response, status_code=404, code="not_found")
