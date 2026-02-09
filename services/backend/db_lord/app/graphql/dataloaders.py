from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.dataloader import DataLoader
from strawberry.types.cast import cast as strawberry_cast

from app.db.postgres.orm import Case as CaseModel
from app.db.postgres.orm import CaseContext, CaseDevice, CaseWearable
from app.db.postgres.orm import Context as ContextModel
from app.db.postgres.orm import Device as DeviceModel
from app.db.postgres.orm import Patient as PatientModel
from app.db.postgres.orm import Wearable as WearableModel
from app.db.postgres.repos.assignment_repo import AssignmentRepo
from app.db.postgres.repos.case_repo import CaseRepo
from app.db.postgres.repos.device_repo import DeviceRepo
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.services.assignment_service import AssignmentService


class Loaders:
    """
    Creates one instance per request in the GraphQL context.
    """

    MAX_BATCH_SIZE = 500

    def __init__(self, db: AsyncSession):
        self.db = db
        self.assignment_service = AssignmentService(
            db, DeviceRepo(db), WearableRepo(db), CaseRepo(db), AssignmentRepo(db)
        )

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

    # Entity loaders (ID)
    async def _load_patients_by_id(self, ids: list[UUID]) -> list[PatientModel | None]:
        from app.graphql.types import Patient

        result = await self.db.execute(select(PatientModel).where(PatientModel.id.in_(ids)))
        patients = {p.id: strawberry_cast(Patient, p) for p in result.scalars()}
        return [patients.get(id) for id in ids]

    async def _load_cases_by_id(self, ids: list[UUID]) -> list[CaseModel | None]:
        from app.graphql.types import Case

        result = await self.db.execute(select(CaseModel).where(CaseModel.id.in_(ids)))
        cases = {c.id: strawberry_cast(Case, c) for c in result.scalars()}
        return [cases.get(id) for id in ids]

    async def _load_devices_by_id(self, ids: list[UUID]) -> list[DeviceModel | None]:
        from app.graphql.types import Device

        result = await self.db.execute(select(DeviceModel).where(DeviceModel.id.in_(ids)))
        devices = {d.id: strawberry_cast(Device, d) for d in result.scalars()}
        return [devices.get(id) for id in ids]

    async def _load_wearables_by_id(self, ids: list[UUID]) -> list[WearableModel | None]:
        from app.graphql.types import Wearable

        result = await self.db.execute(select(WearableModel).where(WearableModel.id.in_(ids)))
        wearables = {w.id: strawberry_cast(Wearable, w) for w in result.scalars()}
        return [wearables.get(id) for id in ids]

    async def _load_contexts_by_id(self, ids: list[UUID]) -> list[ContextModel | None]:
        from app.graphql.types import Context

        result = await self.db.execute(select(ContextModel).where(ContextModel.id.in_(ids)))
        contexts = {c.id: strawberry_cast(Context, c) for c in result.scalars()}
        return [contexts.get(id) for id in ids]

    # Relationship loaders (FK)
    async def _load_cases_by_patient(self, patient_ids: list[UUID]) -> list[list[CaseModel]]:
        from app.graphql.types import Case

        result = await self.db.execute(select(CaseModel).where(CaseModel.patient_id.in_(patient_ids)))
        # Group by patient_id
        grouped: dict[UUID, list[CaseModel]] = defaultdict(list)
        for c in result.scalars():
            grouped[c.patient_id].append(strawberry_cast(Case, c))
        return [grouped.get(pid, []) for pid in patient_ids]

    async def _load_cases_by_context(self, context_ids: list[UUID]) -> list[list[CaseModel]]:
        from app.graphql.types import Case

        # Join through case_contexts
        result = await self.db.execute(
            select(CaseModel, CaseContext.context_id)
            .join(CaseContext, CaseModel.id == CaseContext.case_id)
            .where(CaseContext.context_id.in_(context_ids))
        )
        grouped: dict[UUID, list[CaseModel]] = defaultdict(list)
        for case, context_id in result:
            if case is None:
                continue
            case_model: CaseModel = case
            grouped[context_id].append(strawberry_cast(Case, case_model))
        return [grouped.get(cid, []) for cid in context_ids]

    # Assignment loaders
    async def _load_device_assignments_by_case(self, case_ids: list[UUID]) -> list[list[CaseDevice]]:
        from app.graphql.types import DeviceAssignment

        assignments = await self.assignment_service.list_device_assignments_by_case_ids(case_ids)
        grouped: dict[UUID, list[CaseDevice]] = defaultdict(list)
        for assignment in assignments:
            grouped[assignment.case_id].append(strawberry_cast(DeviceAssignment, assignment))
        return [grouped.get(cid, []) for cid in case_ids]

    async def _load_device_assignments_by_device(self, device_ids: list[UUID]) -> list[list[CaseDevice]]:
        from app.graphql.types import DeviceAssignment

        assignments = await self.assignment_service.list_device_assignments_by_device_ids(device_ids)
        grouped: dict[UUID, list[CaseDevice]] = defaultdict(list)
        for assignment in assignments:
            grouped[assignment.device_id].append(strawberry_cast(DeviceAssignment, assignment))
        return [grouped.get(did, []) for did in device_ids]

    async def _load_wearable_assignments_by_case(self, case_ids: list[UUID]) -> list[list[CaseWearable]]:
        from app.graphql.types import WearableAssignment

        assignments = await self.assignment_service.list_wearable_assignments_by_case_ids(case_ids)
        grouped: dict[UUID, list[CaseWearable]] = defaultdict(list)
        for assignment in assignments:
            grouped[assignment.case_id].append(strawberry_cast(WearableAssignment, assignment))
        return [grouped.get(cid, []) for cid in case_ids]

    async def _load_wearable_assignments_by_wearable(self, wearable_ids: list[UUID]) -> list[list[CaseWearable]]:
        from app.graphql.types import WearableAssignment

        assignments = await self.assignment_service.list_wearable_assignments_by_wearable_ids(wearable_ids)
        grouped: dict[UUID, list[CaseWearable]] = defaultdict(list)
        for assignment in assignments:
            grouped[assignment.wearable_id].append(strawberry_cast(WearableAssignment, assignment))
        return [grouped.get(wid, []) for wid in wearable_ids]

    # m2m loaders
    async def _load_contexts_by_case(self, case_ids: list[UUID]) -> list[list[ContextModel]]:
        from app.graphql.types import Context

        result = await self.db.execute(
            select(ContextModel, CaseContext.case_id)
            .join(CaseContext, ContextModel.id == CaseContext.context_id)
            .where(CaseContext.case_id.in_(case_ids))
        )
        grouped: dict[UUID, list[ContextModel]] = defaultdict(list)
        for context, case_id in result:
            if context is None:
                continue
            context_model: ContextModel = context
            grouped[case_id].append(strawberry_cast(Context, context_model))
        return [grouped.get(cid, []) for cid in case_ids]

    async def _load_devices_by_case(self, case_ids: list[UUID]) -> list[list[DeviceModel]]:
        """Load devices with currently active assignments."""
        from app.graphql.types import Device

        assignments = await self.assignment_service.list_active_device_assignments_by_case_ids(case_ids)
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

        result = await self.db.execute(select(DeviceModel).where(DeviceModel.id.in_(unique_device_ids)))
        devices_by_id = {device.id: strawberry_cast(Device, device) for device in result.scalars()}
        grouped: dict[UUID, list[DeviceModel]] = defaultdict(list)
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
        """Load wearables with currently active assignments."""
        from app.graphql.types import Wearable

        assignments = await self.assignment_service.list_active_wearable_assignments_by_case_ids(case_ids)
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

        result = await self.db.execute(select(WearableModel).where(WearableModel.id.in_(unique_wearable_ids)))
        wearables_by_id = {wearable.id: strawberry_cast(Wearable, wearable) for wearable in result.scalars()}
        grouped: dict[UUID, list[WearableModel]] = defaultdict(list)
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
