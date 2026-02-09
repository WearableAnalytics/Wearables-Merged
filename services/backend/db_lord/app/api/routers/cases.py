from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi_filters import FilterSet
from fastapi_pagination.cursor import CursorPage

from app.api.dependencies import AssignmentServiceDep, CaseServiceDep
from app.api.streaming import stream_as_ndjson
from app.filters import CaseFilters, CaseSorting, SortingValues
from app.schemas.assignment import ContextAssignmentResponse, DeviceAssignmentResponse, WearableAssignmentResponse
from app.schemas.case import CaseCreate, CaseExpanded, CaseResponse, CaseUpdate

router = APIRouter()
OptionalDateTimeQuery = Annotated[datetime | None, Query()]


@router.post("/", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(item_in: CaseCreate, service: CaseServiceDep):
    return await service.create(item_in)


@router.get("/", response_model=CursorPage[CaseResponse], status_code=status.HTTP_200_OK)
async def list_cases(
    service: CaseServiceDep,
    filters: Annotated[FilterSet, Depends(CaseFilters)],
    sorting: Annotated[SortingValues, Depends(CaseSorting)],
):
    return await service.list(filters=filters, sorting=sorting)


@router.get("/stream")
async def stream_cases(
    service: CaseServiceDep,
    filters: Annotated[FilterSet, Depends(CaseFilters)],
    sorting: Annotated[SortingValues, Depends(CaseSorting)],
    batch_size: int = Query(500, ge=1, le=10_000),
):
    return stream_as_ndjson(service.stream_all(filters, sorting, batch_size))


@router.get("/{id}", response_model=CaseResponse, status_code=status.HTTP_200_OK)
async def get_case(id: UUID, service: CaseServiceDep):
    return await service.get(id)


@router.get("/{id}/expanded", response_model=CaseExpanded, status_code=status.HTTP_200_OK)
async def get_case_expanded(id: UUID, service: CaseServiceDep, expand: Annotated[list[str] | None, Query()] = None):
    return await service.get_with_relations(id, expand=expand)


@router.put("/{id}", response_model=CaseResponse, status_code=status.HTTP_200_OK)
async def update_case(id: UUID, item_in: CaseUpdate, service: CaseServiceDep):
    return await service.update(id, item_in)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(id: UUID, service: CaseServiceDep):
    await service.delete(id)


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


@router.post(
    "/{case_id}/contexts/{context_id}", response_model=ContextAssignmentResponse, status_code=status.HTTP_201_CREATED
)
async def link_context(case_id: UUID, context_id: UUID, service: AssignmentServiceDep):
    return await service.link_context(case_id, context_id)


@router.delete("/{case_id}/contexts/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_context(case_id: UUID, context_id: UUID, service: AssignmentServiceDep):
    await service.unlink_context(case_id, context_id)
    return None


@router.delete("/{case_id}/devices/last", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_last_device(case_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None):
    await service.unassign_last_device(case_id, end_time=end_time)
    return None


@router.delete("/{case_id}/wearables/last", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_last_wearable(case_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None):
    await service.unassign_last_wearable(case_id, end_time=end_time)
    return None


@router.delete("/{case_id}/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_device(
    case_id: UUID, device_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None
):
    await service.unassign_device(case_id, device_id, end_time=end_time)
    return None


@router.delete("/{case_id}/wearables/{wearable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_wearable(
    case_id: UUID, wearable_id: UUID, service: AssignmentServiceDep, end_time: OptionalDateTimeQuery = None
):
    await service.unassign_wearable(case_id, wearable_id, end_time=end_time)
    return None


@router.delete("/{case_id}/devices/{device_id}/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device_assignment(
    case_id: UUID, device_id: UUID, service: AssignmentServiceDep, assigned_from: OptionalDateTimeQuery = None
):
    result = await service.delete_device_assignment(case_id, device_id, assigned_from=assigned_from)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Device assignment not found or ambiguous without assigned_from",
        )
    return None


@router.delete("/{case_id}/wearables/{wearable_id}/assignments", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wearable_assignment(
    case_id: UUID, wearable_id: UUID, service: AssignmentServiceDep, assigned_from: OptionalDateTimeQuery = None
):
    result = await service.delete_wearable_assignment(case_id, wearable_id, assigned_from=assigned_from)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Wearable assignment not found or ambiguous without assigned_from",
        )
    return None
