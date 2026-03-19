from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import AssignmentServiceDep, CaseFiltersDep, CaseServiceDep, CaseSortingDep
from app.api.params import STREAM_BATCH_SIZE_DEFAULT, StreamBatchSizeParam
from app.api.streaming import stream_as_ndjson
from app.schemas.assignment import ContextAssignmentResponse, DeviceAssignmentResponse, WearableAssignmentResponse
from app.schemas.case import CaseCreate, CaseExpandableFields, CaseExpanded, CaseResponse, CaseUpdate

router = APIRouter()
OptionalDateTimeQuery = Annotated[datetime | None, Query()]


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(item_in: CaseCreate, service: CaseServiceDep):
    return await service.create(item_in)


@router.patch("/{id:uuid}", response_model=CaseResponse)
async def update_case(id: UUID, item_in: CaseUpdate, service: CaseServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id:uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(id: UUID, service: CaseServiceDep):
    await service.delete(id)


@router.get("/{id:uuid}", response_model=CaseResponse)
async def get_case(id: UUID, service: CaseServiceDep):
    return await service.get(id)


@router.get("/{id:uuid}/expanded", response_model=CaseExpanded, response_model_exclude_unset=True)
async def get_case_expanded(
    id: UUID, service: CaseServiceDep, expand: Annotated[list[CaseExpandableFields], Query(min_length=1)]
):
    return await service.get_with_relations(id, expand)


@router.get("/", response_model=CursorPage[CaseResponse])
async def list_cases(service: CaseServiceDep, filters: CaseFiltersDep, sorting: CaseSortingDep):
    return await service.list(filters, sorting)


@router.get("/stream")
async def stream_cases(
    service: CaseServiceDep,
    filters: CaseFiltersDep,
    sorting: CaseSortingDep,
    batch_size: StreamBatchSizeParam = STREAM_BATCH_SIZE_DEFAULT,
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size, as_mapping=True), schema=CaseResponse)


# Assignment Endpoints
@router.post(
    "/{case_id}/devices/{device_id}", response_model=DeviceAssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def assign_device(
    case_id: UUID,
    device_id: UUID,
    service: AssignmentServiceDep,
    start_time: OptionalDateTimeQuery = None,
    end_time: OptionalDateTimeQuery = None,
):
    return await service.assign_device(case_id, device_id, start_time, end_time)


@router.get("/{case_id}/devices/{device_id}/active-assignment", response_model=DeviceAssignmentResponse)
async def get_active_device_assignment(case_id: UUID, device_id: UUID, service: AssignmentServiceDep):
    return await service.get_active_device_assignment(case_id, device_id)


@router.get("/{case_id}/devices/last-assignment", response_model=DeviceAssignmentResponse)
async def get_last_device_assignment(case_id: UUID, service: AssignmentServiceDep):
    return await service.get_last_device_assignment(case_id)


@router.post(
    "/{case_id}/wearables/{wearable_id}", response_model=WearableAssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def assign_wearable(
    case_id: UUID,
    wearable_id: UUID,
    service: AssignmentServiceDep,
    start_time: OptionalDateTimeQuery = None,
    end_time: OptionalDateTimeQuery = None,
):
    return await service.assign_wearable(case_id, wearable_id, start_time, end_time)


@router.get("/{case_id}/wearables/{wearable_id}/active-assignment", response_model=WearableAssignmentResponse)
async def get_active_wearable_assignment(case_id: UUID, wearable_id: UUID, service: AssignmentServiceDep):
    return await service.get_active_wearable_assignment(case_id, wearable_id)


@router.get("/{case_id}/wearables/last-assignment", response_model=WearableAssignmentResponse)
async def get_last_wearable_assignment(case_id: UUID, service: AssignmentServiceDep):
    return await service.get_last_wearable_assignment(case_id)


@router.post(
    "/{case_id}/contexts/{context_id}", response_model=ContextAssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def link_context(case_id: UUID, context_id: UUID, service: AssignmentServiceDep):
    return await service.link_context(case_id, context_id)


@router.delete("/{case_id}/contexts/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_context(case_id: UUID, context_id: UUID, service: AssignmentServiceDep):
    await service.unlink_context(case_id, context_id)


@router.delete("/{case_id}/devices/last", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_last_device(case_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None):
    await service.unassign_last_device(case_id, end_time)


@router.delete("/{case_id}/wearables/last", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_last_wearable(case_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None):
    await service.unassign_last_wearable(case_id, end_time)


@router.delete("/{case_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_device(
    case_id: UUID, device_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None
):
    await service.unassign_device(case_id, device_id, end_time)


@router.delete("/{case_id}/wearables/{wearable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_wearable(
    case_id: UUID, wearable_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None
):
    await service.unassign_wearable(case_id, wearable_id, end_time)


@router.delete("/{case_id}/devices/{device_id}/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_assignment(
    case_id: UUID, device_id: UUID, service: AssignmentServiceDep, assigned_from: OptionalDateTimeQuery = None
):
    result = await service.delete_device_assignment(case_id, device_id, assigned_from)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Device assignment not found or ambiguous without assigned_from",
        )


@router.delete("/{case_id}/wearables/{wearable_id}/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wearable_assignment(
    case_id: UUID, wearable_id: UUID, service: AssignmentServiceDep, assigned_from: OptionalDateTimeQuery = None
):
    result = await service.delete_wearable_assignment(case_id, wearable_id, assigned_from)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Wearable assignment not found or ambiguous without assigned_from",
        )
