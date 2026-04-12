from datetime import datetime
from typing import Any
from uuid import UUID, uuid7

from httpx import AsyncClient, Response
from pydantic import BaseModel

from app.core.json_types import JsonObject
from app.schemas.case import CaseResponse
from app.schemas.context import ContextResponse
from app.schemas.device import DeviceResponse
from app.schemas.patient import PatientResponse
from app.schemas.wearable import WearableResponse

type IdLike = UUID | str


async def _post_and_validate[TModel: BaseModel](
    client: AsyncClient,
    path: str,
    payload: JsonObject,
    schema: type[TModel],
    *,
    status_code: int = 201,
) -> TModel:
    response = await client.post(path, json=payload)
    assert response.status_code == status_code, response.text
    return schema.model_validate(response.json())


async def create_patient(
    client: AsyncClient,
    *,
    name: str,
    sex: str = "M",
    charite_id: IdLike | None = None,
    dob: str | None = None,
) -> PatientResponse:
    payload: JsonObject = {
        "charite_id": str(charite_id) if charite_id is not None else str(uuid7()),
        "name": name,
        "sex": sex,
    }
    if dob is not None:
        payload["dob"] = dob

    return await _post_and_validate(client, "/patients/", payload, PatientResponse)


async def create_case(client: AsyncClient, *, patient_id: IdLike, status: str = "ONGOING") -> CaseResponse:
    return await _post_and_validate(
        client,
        "/cases/",
        {"patient_id": str(patient_id), "status": status},
        CaseResponse,
    )


async def create_device(
    client: AsyncClient,
    *,
    serial_nr: str,
    model: str,
    status: str = "AVAILABLE",
) -> DeviceResponse:
    return await _post_and_validate(
        client,
        "/devices/",
        {
            "serial_nr": serial_nr,
            "model": model,
            "manufacturer": "Apple" if "iphone" in model.lower() else "Samsung",
            "os_version": "iOS 17.5" if "iphone" in model.lower() else "Android 14",
            "status": status,
        },
        DeviceResponse,
    )


async def create_wearable(
    client: AsyncClient,
    *,
    serial_nr: str,
    model: str,
    status: str = "AVAILABLE",
) -> WearableResponse:
    return await _post_and_validate(
        client,
        "/wearables/",
        {
            "serial_nr": serial_nr,
            "model": model,
            "manufacturer": "Apple" if "watch" in model.lower() else "Polar",
            "os_version": "watchOS 10.4" if "watch" in model.lower() else "Firmware 2.8.0",
            "status": status,
        },
        WearableResponse,
    )


async def create_context(client: AsyncClient, *, group_name: str, coordinator: str) -> ContextResponse:
    return await _post_and_validate(
        client,
        "/contexts/",
        {
            "group_name": group_name,
            "coordinator": coordinator,
        },
        ContextResponse,
    )


async def record_telemetry(
    client: AsyncClient,
    *,
    measurement: str,
    patient_id: IdLike,
    case_id: IdLike,
    device_id: IdLike,
    wearable_id: IdLike,
    mapping_id: IdLike,
    dot_dependency_file_id: IdLike,
    timestamp: datetime,
    fields: JsonObject,
    context_id: IdLike | None = None,
    other_tags: dict[str, str] | None = None,
) -> None:
    other_tags_payload: JsonObject = dict(other_tags or {})
    payload: JsonObject = {
        "patient_id": str(patient_id),
        "case_id": str(case_id),
        "device_id": str(device_id),
        "wearable_id": str(wearable_id),
        "mapping_id": str(mapping_id),
        "dot_dependency_file_id": str(dot_dependency_file_id),
        "measurement": measurement,
        "timestamp": timestamp.isoformat(),
        "fields": fields,
        "other_tags": other_tags_payload,
    }
    if context_id is not None:
        payload["context_id"] = str(context_id)

    response = await client.post(
        "/telemetry/",
        json=payload,
    )
    assert response.status_code == 201, response.text


def assert_api_error(
    response: Response,
    *,
    status_code: int,
    code: str | None = None,
    detail_contains: str | None = None,
) -> dict[str, Any]:
    """Assert structured API error payload shape and return parsed JSON body."""
    assert response.status_code == status_code, response.text
    payload = response.json()
    assert "detail" in payload, payload
    if code is not None:
        assert payload.get("code") == code, payload
    if detail_contains is not None:
        assert detail_contains.lower() in str(payload.get("detail", "")).lower(), payload
    return payload


def assert_json_response(response: Response, *, status_code: int) -> dict[str, Any]:
    assert response.status_code == status_code, response.text
    return response.json()


def assert_no_content(response: Response) -> None:
    assert response.status_code == 204, response.text
    assert response.content == b""


def assert_graphql_ok(response: Response) -> dict[str, Any]:
    payload = assert_json_response(response, status_code=200)
    assert "errors" not in payload, payload.get("errors")
    return payload


def assert_graphql_error(response: Response) -> dict[str, Any]:
    payload = assert_json_response(response, status_code=200)
    assert payload.get("errors"), payload
    return payload
