from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from old_code.services.postgres_impl import PostgresHandler
from models.sql_schema import Case, CaseCreate, Context, ContextBase, Device, DeviceBase, Patient, PatientBase, Wearable


class ResourceConflictError(Exception):
    def __init__(self, message: str):
        self.message = message


class AsyncDbHandler(Protocol):
    # Patients
    async def create_patient(
        self,
        conn: AsyncConnection,
        patient_data: PatientBase,
        id: str | None = None,
    ) -> Patient: ...

    async def upsert_patient(self, conn: AsyncConnection, patient_id: str, patient_data: PatientBase) -> Patient: ...

    async def get_patient(self, conn: AsyncConnection, patient_id: str) -> Patient | None: ...

    async def update_patient(
        self,
        conn: AsyncConnection,
        patient_id: str,
        patient_data: PatientBase,
    ) -> Patient | None: ...

    async def delete_patient(self, conn: AsyncConnection, patient_id: str) -> bool: ...

    # Wearables
    async def get_wearable(self, conn: AsyncConnection, wearable_id: str) -> Wearable | None: ...

    async def create_wearable(
        self, conn: AsyncConnection, wearable_base: DeviceBase, id: str | None = None
    ) -> Wearable: ...

    async def upsert_wearable(self, conn: AsyncConnection, wearable_id: str, wearable_base: DeviceBase) -> Wearable: ...

    async def update_wearable(
        self, conn: AsyncConnection, wearable_id: str, wearable_base: DeviceBase
    ) -> Wearable | None: ...

    async def delete_wearable(self, conn: AsyncConnection, wearable_id: str) -> bool: ...

    # Devices
    async def get_device(self, conn: AsyncConnection, device_id: str) -> Device | None: ...

    async def create_device(self, conn: AsyncConnection, device_base: DeviceBase, id: str | None = None) -> Device: ...

    async def upsert_device(self, conn: AsyncConnection, device_id: str, device_base: DeviceBase) -> Device: ...

    async def update_device(self, conn: AsyncConnection, device_id: str, device_base: DeviceBase) -> Device | None: ...

    async def delete_device(self, conn: AsyncConnection, device_id: str) -> bool: ...

    # Contexts
    async def get_context(self, conn: AsyncConnection, context_id: str) -> Context | None: ...

    async def create_context(
        self, conn: AsyncConnection, context_base: ContextBase, id: str | None = None
    ) -> Context: ...

    async def upsert_context(self, conn: AsyncConnection, context_id: str, context_base: ContextBase) -> Context: ...

    async def update_context(
        self, conn: AsyncConnection, context_id: str, context_base: ContextBase
    ) -> Context | None: ...

    async def delete_context(self, conn: AsyncConnection, context_id: str) -> bool: ...

    # Cases
    async def create_case(self, conn: AsyncConnection, case_data: CaseCreate) -> Case: ...

    async def get_case(self, conn: AsyncConnection, case_id: str, expand: list[str] | None = None) -> Case | None: ...

    # Linking
    async def link_device(
        self, conn: AsyncConnection, case_id: str, device_id: str, assigned_from: datetime | None = None
    ): ...

    async def link_wearable(
        self, conn: AsyncConnection, case_id: str, wearable_id: str, assigned_from: datetime | None = None
    ): ...

    async def link_context(self, conn: AsyncConnection, case_id: str, context_id: str): ...


def get_async_db_handler() -> AsyncDbHandler:
    return PostgresHandler()
