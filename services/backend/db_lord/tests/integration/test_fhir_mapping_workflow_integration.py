import json
from uuid import uuid7

import pytest
from httpx import AsyncClient

from tests.helpers.api import assert_api_error as _assert_api_error
from tests.helpers.api import assert_json_response as _assert_json_response
from tests.helpers.api import assert_no_content as _assert_no_content

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

UPDATED_DOT_DIGRAPH = """strict digraph G {
  value;
  code;
  unit;
  system;
  display;
  value -> code;
  value -> unit;
  unit -> system;
  code -> display;
}"""


class TestFHIRMappingWorkflowIntegration:
    async def test_fhir_mapping_and_dot_dependency_file_lifecycle(self, integration_client: AsyncClient):
        version = f"it-v-{uuid7().hex[:8]}"
        mapping_payload = {
            "version": version,
            "full_mapping": {
                "resourceType": "Observation",
                "map": {"heart_rate": "valueQuantity.value"},
            },
        }
        create_mapping_response = await integration_client.post("/fhir-mappings/", json=mapping_payload)
        mapping = _assert_json_response(create_mapping_response, status_code=201)

        list_mappings_response = await integration_client.get("/fhir-mappings/", params={"size": 1})
        list_payload = _assert_json_response(list_mappings_response, status_code=200)
        assert [item["id"] for item in list_payload["items"]] == [mapping["id"]]

        dot_dependency_file_payload = {
            "version": version,
            "category": "continuous",
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
        create_dot_dependency_file_response = await integration_client.post(
            "/fhir-mappings/dot_dependency_file", json=dot_dependency_file_payload
        )
        dot_dependency_file = _assert_json_response(create_dot_dependency_file_response, status_code=201)

        list_dot_dependency_file_response = await integration_client.get(
            "/fhir-mappings/dot_dependency_file", params={"size": 10}
        )
        list_dot_dependency_file_payload = _assert_json_response(list_dot_dependency_file_response, status_code=200)
        assert [item["id"] for item in list_dot_dependency_file_payload["items"]] == [dot_dependency_file["id"]]

        stream_mappings_response = await integration_client.get("/fhir-mappings/stream", params={"batch_size": 10})
        assert stream_mappings_response.status_code == 200, stream_mappings_response.text
        stream_mapping_items = [json.loads(line) for line in stream_mappings_response.text.splitlines() if line.strip()]
        assert [item["id"] for item in stream_mapping_items] == [mapping["id"]]

        stream_dot_dependency_file_response = await integration_client.get(
            "/fhir-mappings/dot_dependency_file/stream", params={"batch_size": 10}
        )
        assert stream_dot_dependency_file_response.status_code == 200, stream_dot_dependency_file_response.text
        stream_dot_dependency_file_items = [
            json.loads(line) for line in stream_dot_dependency_file_response.text.splitlines() if line.strip()
        ]
        assert [item["id"] for item in stream_dot_dependency_file_items] == [dot_dependency_file["id"]]

        update_dot_dependency_file_response = await integration_client.patch(
            f"/fhir-mappings/dot_dependency_file/{dot_dependency_file['id']}",
            json={
                "category": "incremental",
                "digraph": {
                    "format": "dot",
                    "source": UPDATED_DOT_DIGRAPH,
                    "entrypoint": "value",
                    "nodes": ["value", "code", "unit", "system", "display"],
                },
            },
        )
        updated_dot_dependency_file = _assert_json_response(update_dot_dependency_file_response, status_code=200)
        assert updated_dot_dependency_file["category"] == "incremental"

        delete_mapping_response = await integration_client.delete(f"/fhir-mappings/{mapping['id']}")
        _assert_no_content(delete_mapping_response)

        get_dot_dependency_file_response = await integration_client.get(
            f"/fhir-mappings/dot_dependency_file/{dot_dependency_file['id']}"
        )
        _assert_api_error(get_dot_dependency_file_response, status_code=404, code="not_found")
