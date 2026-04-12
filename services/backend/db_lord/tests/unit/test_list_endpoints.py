"""
API tests for paginated list endpoints
"""

import json

import pytest
from httpx import AsyncClient

from tests.helpers.api import assert_json_response as _assert_json_response

pytestmark = pytest.mark.anyio


class TestPaginatedListEndpoints:
    async def test_list_patients_pagination(self, client: AsyncClient, patient_factory):
        for i in range(3):
            await patient_factory(name=f"Patient {i}")

        response1 = await client.get("/patients/", params={"size": 2})
        data1 = _assert_json_response(response1, status_code=200)
        assert len(data1["items"]) == 2
        assert data1["next_page"] is not None

        response2 = await client.get("/patients/", params={"size": 2, "cursor": data1["next_page"]})
        data2 = _assert_json_response(response2, status_code=200)
        ids1 = {item["id"] for item in data1["items"]}
        ids2 = {item["id"] for item in data2["items"]}
        assert ids1.isdisjoint(ids2)

    async def test_list_devices_pagination(self, client: AsyncClient, device_factory):
        await device_factory()
        await device_factory()

        response = await client.get("/devices/", params={"size": 1})
        data = _assert_json_response(response, status_code=200)
        assert len(data["items"]) == 1
        assert data["next_page"] is not None

    async def test_list_wearables_pagination(self, client: AsyncClient, wearable_factory):
        await wearable_factory()
        await wearable_factory()

        response = await client.get("/wearables/", params={"size": 1})
        data = _assert_json_response(response, status_code=200)
        assert len(data["items"]) == 1
        assert data["next_page"] is not None

    async def test_list_contexts_pagination(self, client: AsyncClient, context_factory):
        await context_factory()
        await context_factory()

        response = await client.get("/contexts/", params={"size": 1})
        data = _assert_json_response(response, status_code=200)
        assert len(data["items"]) == 1
        assert data["next_page"] is not None

    async def test_list_cases_pagination(self, client: AsyncClient, patient_factory, case_factory):
        patient = await patient_factory()
        await case_factory(patient_id=patient["id"])
        await case_factory(patient_id=patient["id"])

        response = await client.get("/cases/", params={"size": 1})
        data = _assert_json_response(response, status_code=200)
        assert len(data["items"]) == 1
        assert data["next_page"] is not None

    async def test_stream_patients_endpoint(self, client: AsyncClient, patient_factory):
        created = await patient_factory(name="Stream Patient")

        response = await client.get("/patients/stream")
        assert response.status_code == 200
        assert "application/x-ndjson" in response.headers["content-type"]

        lines = [line for line in response.text.splitlines() if line.strip()]
        payloads = [json.loads(line) for line in lines]
        assert [item["id"] for item in payloads] == [str(created["id"])]

    async def test_stream_cases_endpoint(self, client: AsyncClient, patient_factory, case_factory):
        patient = await patient_factory()
        created_case = await case_factory(patient_id=patient["id"])

        response = await client.get("/cases/stream")
        assert response.status_code == 200
        assert "application/x-ndjson" in response.headers["content-type"]

        lines = [line for line in response.text.splitlines() if line.strip()]
        payloads = [json.loads(line) for line in lines]
        assert [item["id"] for item in payloads] == [str(created_case["id"])]

    async def test_update_case_endpoint(self, client: AsyncClient, patient_factory, case_factory):
        patient = await patient_factory()
        created_case = await case_factory(patient_id=patient["id"], status="PLANNED")

        response = await client.patch(f"/cases/{created_case['id']}", json={"status": "ONGOING"})
        body = _assert_json_response(response, status_code=200)
        assert body["id"] == str(created_case["id"])
        assert body["status"] == "ONGOING"
