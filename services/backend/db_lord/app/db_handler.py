from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncConnection

from models.sql_schema import Context, ContextBase, Device, DeviceBase, Patient, PatientBase, Wearable


def get_async_db_handler() -> AsyncConnection:
    return AsyncConnection()


class AsyncDbHandler(Protocol):
    async def create_patient(
        self,
        conn: AsyncConnection,
        patient_data: PatientBase,
    ) -> Patient: ...

    async def get_patient(self, conn: AsyncConnection, patient_id: str) -> Optional[Patient]: ...

    async def update_patient(
        self,
        conn: AsyncConnection,
        patient_id: str,
        patient_data: PatientBase,
    ) -> Optional[Patient]: ...

    async def delete_patient(self, conn: AsyncConnection, patient_id: str) -> Optional[bool]: ...

    async def get_wearable(self, conn: AsyncConnection, wearable_id: str) -> Optional[Wearable]: ...

    async def create_wearable(self, conn: AsyncConnection, wearable_base: DeviceBase) -> Wearable: ...

    async def update_wearable(
        self, conn: AsyncConnection, wearable_id: str, wearable_base: DeviceBase
    ) -> Optional[Wearable]: ...

    async def delete_wearable(self, conn: AsyncConnection, wearable_id: str) -> bool: ...

    async def get_device(self, conn: AsyncConnection, device_id: str) -> Optional[Device]: ...

    async def create_device(self, conn: AsyncConnection, device_base: DeviceBase) -> Device: ...

    async def update_device(self, conn: AsyncConnection, device_id: str, device_base: DeviceBase) -> Device: ...

    async def delete_device(self, conn: AsyncConnection, device_id: str): ...

    async def get_context(self, conn: AsyncConnection, context_id: str) -> Optional[Context]: ...

    async def create_context(self, conn: AsyncConnection, context_base: ContextBase) -> Context: ...

    async def update_context(self, conn: AsyncConnection, context_id: str, context_base: ContextBase) -> Context: ...

    async def delete_context(self, conn: AsyncConnection, context_id: str): ...
