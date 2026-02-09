from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Annotated

import strawberry
from strawberry.experimental.pydantic import type as pydantic_type

from app.schemas.assignment import DeviceAssignmentResponse as DeviceAssignmentPydantic
from app.schemas.assignment import WearableAssignmentResponse as WearableAssignmentPydantic
from app.schemas.case import CaseResponse as CasePydantic
from app.schemas.context import ContextResponse as ContextPydantic
from app.schemas.device import DeviceResponse as DevicePydantic
from app.schemas.patient import PatientResponse as PatientPydantic
from app.schemas.wearable import WearableResponse as WearablePydantic

if TYPE_CHECKING:
    from app.graphql.dataloaders import Loaders


@pydantic_type(model=PatientPydantic, all_fields=True)
class Patient:
    @strawberry.field
    async def cases(self, info: strawberry.Info) -> list[Annotated[Case, strawberry.lazy(".types")]]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.cases_by_patient.load(self.id)


@pydantic_type(model=DevicePydantic, all_fields=True)
class Device:
    @strawberry.field
    async def case_assignments(
        self, info: strawberry.Info
    ) -> list[Annotated[DeviceAssignment, strawberry.lazy(".types")]]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.device_assignments_by_device.load(self.id)


@pydantic_type(model=WearablePydantic, all_fields=True)
class Wearable:
    @strawberry.field
    async def case_assignments(
        self, info: strawberry.Info
    ) -> list[Annotated[WearableAssignment, strawberry.lazy(".types")]]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearable_assignments_by_wearable.load(self.id)


@pydantic_type(model=ContextPydantic, all_fields=True)
class Context:
    @strawberry.field
    async def cases(self, info: strawberry.Info) -> list[Annotated[Case, strawberry.lazy(".types")]]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.cases_by_context.load(self.id)


@strawberry.type
class FHIRMapping:
    id: uuid.UUID
    version: str
    full_mapping: strawberry.scalars.JSON


@pydantic_type(model=DeviceAssignmentPydantic, all_fields=True)
class DeviceAssignment:
    @strawberry.field
    async def device(self, info: strawberry.Info) -> Device | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.device_by_id.load(self.device_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Annotated[Case, strawberry.lazy(".types")] | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.case_by_id.load(self.case_id)


@pydantic_type(model=WearableAssignmentPydantic, all_fields=True)
class WearableAssignment:
    @strawberry.field
    async def wearable(self, info: strawberry.Info) -> Wearable | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearable_by_id.load(self.wearable_id)

    @strawberry.field
    async def case(self, info: strawberry.Info) -> Annotated[Case, strawberry.lazy(".types")] | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.case_by_id.load(self.case_id)


@pydantic_type(model=CasePydantic, all_fields=True)
class Case:
    @strawberry.field
    async def patient(self, info: strawberry.Info) -> Patient | None:
        loaders: Loaders = info.context["loaders"]
        return await loaders.patient_by_id.load(self.patient_id)

    @strawberry.field
    async def devices(self, info: strawberry.Info) -> list[Device]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.devices_by_case.load(self.id)

    @strawberry.field
    async def device_assignments(self, info: strawberry.Info) -> list[DeviceAssignment]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.device_assignments_by_case.load(self.id)

    @strawberry.field
    async def wearables(self, info: strawberry.Info) -> list[Wearable]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearables_by_case.load(self.id)

    @strawberry.field
    async def wearable_assignments(self, info: strawberry.Info) -> list[WearableAssignment]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.wearable_assignments_by_case.load(self.id)

    @strawberry.field
    async def contexts(self, info: strawberry.Info) -> list[Context]:
        loaders: Loaders = info.context["loaders"]
        return await loaders.contexts_by_case.load(self.id)


@strawberry.type
class TelemetryPoint:
    timestamp: datetime
    measurement: str
    patient_id: str | None
    device_id: str | None
    wearable_id: str | None
    case_id: str | None
    mapping_id: str | None
    code: str | None
    context_id: str | None
    other_tags: strawberry.scalars.JSON
    fields: strawberry.scalars.JSON


@strawberry.type
class TelemetryResolvedMetadata:
    patients: list[Patient]
    cases: list[Case]
    devices: list[Device]
    wearables: list[Wearable]
    contexts: list[Context]
    mappings: list[FHIRMapping]


@strawberry.type
class TelemetryPage:
    items: list[TelemetryPoint]
    next_cursor: str | None
    resolved: TelemetryResolvedMetadata | None = None
