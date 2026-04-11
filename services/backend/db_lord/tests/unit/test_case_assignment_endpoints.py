import pytest
from httpx import AsyncClient

from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.api import assert_no_content as _assert_no_content

pytestmark = pytest.mark.anyio


async def test_context_link_unlink(client: AsyncClient, patient_factory, case_factory, context_factory):
    patient = await patient_factory()
    case = await case_factory(patient_id=patient["id"], status="PLANNED")
    context = await context_factory()

    link_resp = await client.post(f"/cases/{case['id']}/contexts/{context['id']}")
    linked = _assert_json_response(link_resp, status_code=201)
    assert linked["case_id"] == str(case["id"])
    assert linked["context_id"] == str(context["id"])

    unlink_resp = await client.delete(f"/cases/{case['id']}/contexts/{context['id']}")
    _assert_no_content(unlink_resp)

    unlink_again_resp = await client.delete(f"/cases/{case['id']}/contexts/{context['id']}")
    _assert_api_error(unlink_again_resp, status_code=404, code="not_found")
