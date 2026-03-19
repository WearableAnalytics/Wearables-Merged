from __future__ import annotations

from asyncio import Semaphore
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry import cast as strawberry_cast
from strawberry.dataloader import DataLoader

from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel
from app.graphql.connection_batching import NestedConnectionLoader

if TYPE_CHECKING:
    from app.graphql.types import Case, Context, Device, Patient, Wearable


class Loaders:
    """
    Creates one instance per GraphQL request context.
    """

    MAX_BATCH_SIZE = 500

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], db_semaphore: Semaphore):
        self._session_factory = session_factory
        self._db_semaphore = db_semaphore

        self.nested_connections = NestedConnectionLoader(session_factory, db_semaphore)

        self.patient_by_id: DataLoader[UUID, Patient | None] = DataLoader(
            load_fn=self._load_patients_by_id, max_batch_size=self.MAX_BATCH_SIZE
        )
        self.case_by_id: DataLoader[UUID, Case | None] = DataLoader(
            load_fn=self._load_cases_by_id, max_batch_size=self.MAX_BATCH_SIZE
        )
        self.device_by_id: DataLoader[UUID, Device | None] = DataLoader(
            load_fn=self._load_devices_by_id, max_batch_size=self.MAX_BATCH_SIZE
        )
        self.wearable_by_id: DataLoader[UUID, Wearable | None] = DataLoader(
            load_fn=self._load_wearables_by_id, max_batch_size=self.MAX_BATCH_SIZE
        )
        self.context_by_id: DataLoader[UUID, Context | None] = DataLoader(
            load_fn=self._load_contexts_by_id, max_batch_size=self.MAX_BATCH_SIZE
        )

    async def _load_by_id[TGraphQL](
        self, ids: list[UUID], model: type[Any], graphql_type: type[TGraphQL]
    ) -> list[TGraphQL | None]:
        if not ids:
            return []

        entities: dict[UUID, TGraphQL] = {}
        async with self._db_semaphore, self._session_factory() as db:
            result = await db.scalars(select(model).where(model.id.in_(ids)))
            for entity in result:
                graphql_entity = strawberry_cast(graphql_type, entity)
                if graphql_entity is not None:
                    entities[entity.id] = graphql_entity
        return [entities.get(id) for id in ids]

    async def _load_patients_by_id(self, ids: list[UUID]) -> list[Patient | None]:
        from app.graphql.types import Patient

        return await self._load_by_id(ids, PatientModel, Patient)

    async def _load_cases_by_id(self, ids: list[UUID]) -> list[Case | None]:
        from app.graphql.types import Case

        return await self._load_by_id(ids, CaseModel, Case)

    async def _load_devices_by_id(self, ids: list[UUID]) -> list[Device | None]:
        from app.graphql.types import Device

        return await self._load_by_id(ids, DeviceModel, Device)

    async def _load_wearables_by_id(self, ids: list[UUID]) -> list[Wearable | None]:
        from app.graphql.types import Wearable

        return await self._load_by_id(ids, WearableModel, Wearable)

    async def _load_contexts_by_id(self, ids: list[UUID]) -> list[Context | None]:
        from app.graphql.types import Context

        return await self._load_by_id(ids, ContextModel, Context)
