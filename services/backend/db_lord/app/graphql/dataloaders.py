from asyncio import Semaphore
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from strawberry.dataloader import DataLoader
from strawberry.types.cast import cast as strawberry_cast

from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import CaseContext, CaseDevice, CaseWearable
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel


def _active_assignment_window(model: type[CaseDevice] | type[CaseWearable], now_ts: datetime):
    return or_(
        model.assigned_to.is_(None),
        and_(model.assigned_from <= now_ts, model.assigned_to > now_ts),
    )


class Loaders:
    """
    Creates one instance per GraphQL request context.
    """

    MAX_BATCH_SIZE = 500

    def __init__(self, session_factory: async_sessionmaker[AsyncSession], db_semaphore: Semaphore):
        self._session_factory = session_factory
        self._db_semaphore = db_semaphore

        # Entity loaders (ID)
        self.patient_by_id: DataLoader[UUID, PatientModel | None] = DataLoader(
            self._load_patients_by_id, self.MAX_BATCH_SIZE
        )
        self.case_by_id: DataLoader[UUID, CaseModel | None] = DataLoader(self._load_cases_by_id, self.MAX_BATCH_SIZE)
        self.device_by_id: DataLoader[UUID, DeviceModel | None] = DataLoader(
            self._load_devices_by_id, self.MAX_BATCH_SIZE
        )
        self.wearable_by_id: DataLoader[UUID, WearableModel | None] = DataLoader(
            self._load_wearables_by_id, self.MAX_BATCH_SIZE
        )
        self.context_by_id: DataLoader[UUID, ContextModel | None] = DataLoader(
            self._load_contexts_by_id, self.MAX_BATCH_SIZE
        )

        # Relationship loaders (FK)
        self.cases_by_patient: DataLoader[UUID, list[CaseModel]] = self._loader(self._load_cases_by_patient)
        self.cases_by_context: DataLoader[UUID, list[CaseModel]] = self._loader(self._load_cases_by_context)

        # Assignment loaders
        self.device_assignments_by_case: DataLoader[UUID, list[CaseDevice]] = self._loader(
            self._load_device_assignments_by_case
        )
        self.device_assignments_by_device: DataLoader[UUID, list[CaseDevice]] = self._loader(
            self._load_device_assignments_by_device
        )
        self.wearable_assignments_by_case: DataLoader[UUID, list[CaseWearable]] = self._loader(
            self._load_wearable_assignments_by_case
        )
        self.wearable_assignments_by_wearable: DataLoader[UUID, list[CaseWearable]] = self._loader(
            self._load_wearable_assignments_by_wearable
        )

        # m2m loaders
        self.contexts_by_case: DataLoader[UUID, list[ContextModel]] = self._loader(self._load_contexts_by_case)
        self.devices_by_case: DataLoader[UUID, list[DeviceModel]] = self._loader(self._load_devices_by_case)
        self.wearables_by_case: DataLoader[UUID, list[WearableModel]] = self._loader(self._load_wearables_by_case)

    def _loader[K, T](self, load_fn: Callable[[list[K]], Awaitable[list[T]]]) -> DataLoader[K, T]:
        return DataLoader(load_fn, self.MAX_BATCH_SIZE)

    async def _load_by_id[TModel, TGraphQL](
        self,
        ids: list[UUID],
        model: type[TModel],
        graphql_type: type[TGraphQL],
    ) -> list[TGraphQL | None]:
        if not ids:
            return []

        async with self._db_semaphore, self._session_factory() as db:
            result = await db.execute(select(model).where(model.id.in_(ids)))
            entities = {entity.id: strawberry_cast(graphql_type, entity) for entity in result.scalars()}
        return [entities.get(id) for id in ids]

    async def _load_patients_by_id(self, ids: list[UUID]) -> list[PatientModel | None]:
        from app.graphql.types import Patient

        return await self._load_by_id(ids, PatientModel, Patient)

    async def _load_cases_by_id(self, ids: list[UUID]) -> list[CaseModel | None]:
        from app.graphql.types import Case

        return await self._load_by_id(ids, CaseModel, Case)

    async def _load_devices_by_id(self, ids: list[UUID]) -> list[DeviceModel | None]:
        from app.graphql.types import Device

        return await self._load_by_id(ids, DeviceModel, Device)

    async def _load_wearables_by_id(self, ids: list[UUID]) -> list[WearableModel | None]:
        from app.graphql.types import Wearable

        return await self._load_by_id(ids, WearableModel, Wearable)

    async def _load_contexts_by_id(self, ids: list[UUID]) -> list[ContextModel | None]:
        from app.graphql.types import Context

        return await self._load_by_id(ids, ContextModel, Context)

    async def _load_assignments[TAssignment, TGraphQL](
        self,
        *,
        ids: list[UUID],
        model: type[TAssignment],
        group_attr: str,
        graphql_type: type[TGraphQL],
    ) -> list[list[TGraphQL]]:
        if not ids:
            return []

        grouped: dict[UUID, list[TGraphQL]] = defaultdict(list)
        group_column = getattr(model, group_attr)

        async with self._db_semaphore, self._session_factory() as db:
            result = await db.execute(
                select(model).where(group_column.in_(ids)).order_by(group_column, model.assigned_from.desc())
            )
            for assignment in result.scalars():
                grouped[getattr(assignment, group_attr)].append(strawberry_cast(graphql_type, assignment))

        return [grouped.get(entity_id, []) for entity_id in ids]

    async def _load_cases_by_patient(self, patient_ids: list[UUID]) -> list[list[CaseModel]]:
        from app.graphql.types import Case

        grouped: dict[UUID, list[CaseModel]] = defaultdict(list)

        async with self._db_semaphore, self._session_factory() as db:
            result = await db.execute(select(CaseModel).where(CaseModel.patient_id.in_(patient_ids)))
            for case in result.scalars():
                grouped[case.patient_id].append(strawberry_cast(Case, case))

        return [grouped.get(pid, []) for pid in patient_ids]

    async def _load_cases_by_context(self, context_ids: list[UUID]) -> list[list[CaseModel]]:
        from app.graphql.types import Case

        grouped: dict[UUID, list[CaseModel]] = defaultdict(list)

        async with self._db_semaphore, self._session_factory() as db:
            result = await db.execute(
                select(CaseModel, CaseContext.context_id)
                .join(CaseContext, CaseModel.id == CaseContext.case_id)
                .where(CaseContext.context_id.in_(context_ids))
            )
            for case, context_id in result:
                if case is None:
                    continue
                grouped[context_id].append(strawberry_cast(Case, case))

        return [grouped.get(cid, []) for cid in context_ids]

    async def _load_device_assignments_by_case(self, case_ids: list[UUID]) -> list[list[CaseDevice]]:
        from app.graphql.types import DeviceAssignment

        return await self._load_assignments(
            ids=case_ids,
            model=CaseDevice,
            group_attr="case_id",
            graphql_type=DeviceAssignment,
        )

    async def _load_device_assignments_by_device(self, device_ids: list[UUID]) -> list[list[CaseDevice]]:
        from app.graphql.types import DeviceAssignment

        return await self._load_assignments(
            ids=device_ids,
            model=CaseDevice,
            group_attr="device_id",
            graphql_type=DeviceAssignment,
        )

    async def _load_wearable_assignments_by_case(self, case_ids: list[UUID]) -> list[list[CaseWearable]]:
        from app.graphql.types import WearableAssignment

        return await self._load_assignments(
            ids=case_ids,
            model=CaseWearable,
            group_attr="case_id",
            graphql_type=WearableAssignment,
        )

    async def _load_wearable_assignments_by_wearable(self, wearable_ids: list[UUID]) -> list[list[CaseWearable]]:
        from app.graphql.types import WearableAssignment

        return await self._load_assignments(
            ids=wearable_ids,
            model=CaseWearable,
            group_attr="wearable_id",
            graphql_type=WearableAssignment,
        )

    async def _load_contexts_by_case(self, case_ids: list[UUID]) -> list[list[ContextModel]]:
        from app.graphql.types import Context

        grouped: dict[UUID, list[ContextModel]] = defaultdict(list)

        if not case_ids:
            return []

        async with self._db_semaphore, self._session_factory() as db:
            result = await db.execute(
                select(ContextModel, CaseContext.case_id)
                .join(CaseContext, ContextModel.id == CaseContext.context_id)
                .where(CaseContext.case_id.in_(case_ids))
            )
            for context, case_id in result:
                if context is None:
                    continue
                grouped[case_id].append(strawberry_cast(Context, context))

        return [grouped.get(cid, []) for cid in case_ids]

    async def _load_devices_by_case(self, case_ids: list[UUID]) -> list[list[DeviceModel]]:
        from app.graphql.types import Device

        if not case_ids:
            return []

        now_ts = datetime.now(UTC)
        grouped: dict[UUID, list[DeviceModel]] = defaultdict(list)

        async with self._db_semaphore, self._session_factory() as db:
            assignment_result = await db.execute(
                select(CaseDevice)
                .where(CaseDevice.case_id.in_(case_ids), _active_assignment_window(CaseDevice, now_ts))
                .order_by(CaseDevice.case_id, CaseDevice.assigned_from.desc())
            )
            assignments = assignment_result.scalars().all()

            device_ids_by_case: dict[UUID, list[UUID]] = defaultdict(list)
            unique_device_ids: list[UUID] = []
            seen_device_ids: set[UUID] = set()
            for assignment in assignments:
                device_ids_by_case[assignment.case_id].append(assignment.device_id)
                if assignment.device_id not in seen_device_ids:
                    seen_device_ids.add(assignment.device_id)
                    unique_device_ids.append(assignment.device_id)

            if not unique_device_ids:
                return [[] for _ in case_ids]

            result = await db.execute(select(DeviceModel).where(DeviceModel.id.in_(unique_device_ids)))
            devices_by_id = {device.id: strawberry_cast(Device, device) for device in result.scalars()}

            for case_id, device_ids in device_ids_by_case.items():
                seen_case_device_ids: set[UUID] = set()
                for device_id in device_ids:
                    if device_id in seen_case_device_ids:
                        continue
                    seen_case_device_ids.add(device_id)
                    device = devices_by_id.get(device_id)
                    if device is not None:
                        grouped[case_id].append(device)

        return [grouped.get(cid, []) for cid in case_ids]

    async def _load_wearables_by_case(self, case_ids: list[UUID]) -> list[list[WearableModel]]:
        from app.graphql.types import Wearable

        if not case_ids:
            return []

        now_ts = datetime.now(UTC)
        grouped: dict[UUID, list[WearableModel]] = defaultdict(list)

        async with self._db_semaphore, self._session_factory() as db:
            assignment_result = await db.execute(
                select(CaseWearable)
                .where(CaseWearable.case_id.in_(case_ids), _active_assignment_window(CaseWearable, now_ts))
                .order_by(CaseWearable.case_id, CaseWearable.assigned_from.desc())
            )
            assignments = assignment_result.scalars().all()

            wearable_ids_by_case: dict[UUID, list[UUID]] = defaultdict(list)
            unique_wearable_ids: list[UUID] = []
            seen_wearable_ids: set[UUID] = set()
            for assignment in assignments:
                wearable_ids_by_case[assignment.case_id].append(assignment.wearable_id)
                if assignment.wearable_id not in seen_wearable_ids:
                    seen_wearable_ids.add(assignment.wearable_id)
                    unique_wearable_ids.append(assignment.wearable_id)

            if not unique_wearable_ids:
                return [[] for _ in case_ids]

            result = await db.execute(select(WearableModel).where(WearableModel.id.in_(unique_wearable_ids)))
            wearables_by_id = {wearable.id: strawberry_cast(Wearable, wearable) for wearable in result.scalars()}

            for case_id, wearable_ids in wearable_ids_by_case.items():
                seen_case_wearable_ids: set[UUID] = set()
                for wearable_id in wearable_ids:
                    if wearable_id in seen_case_wearable_ids:
                        continue
                    seen_case_wearable_ids.add(wearable_id)
                    wearable = wearables_by_id.get(wearable_id)
                    if wearable is not None:
                        grouped[case_id].append(wearable)

        return [grouped.get(cid, []) for cid in case_ids]
