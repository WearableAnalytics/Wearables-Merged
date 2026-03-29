from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi_filters.filter_set import FilterSet
from fastapi_filters.types import SortingValues
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.engine import AsyncSessionLocal
from app.db.postgres.repos.assignment_repo import AssignmentRepo
from app.db.postgres.repos.case_repo import CaseRepo
from app.db.postgres.repos.context_repo import ContextRepo
from app.db.postgres.repos.device_repo import DeviceRepo
from app.db.postgres.repos.fhir_mapping_repo import DotDependencyFileRepo, FHIRMappingRepo
from app.db.postgres.repos.patient_repo import PatientRepo
from app.db.postgres.repos.wearable_repo import WearableRepo
from app.filters import (
    CaseFilters,
    CaseSorting,
    ContextFilters,
    ContextSorting,
    DeviceFilters,
    DeviceSorting,
    DotDependencyFileFilters,
    DotDependencyFileSorting,
    FHIRMappingFilters,
    FHIRMappingSorting,
    PatientFilters,
    PatientSorting,
    WearableFilters,
    WearableSorting,
)
from app.graphql.context import GraphQLContext
from app.graphql.dataloaders import Loaders
from app.services.assignment_service import AssignmentService
from app.services.case_service import CaseService
from app.services.context_service import ContextService
from app.services.device_service import DeviceService
from app.services.fhir_mapping_service import DotDependencyFileService, FHIRMappingService
from app.services.patient_service import PatientService
from app.services.telemetry_service import TelemetryService
from app.services.wearable_service import WearableService


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Provide a database session.
    - Service write methods own transaction boundaries via `async with session.begin()`
    - Services have to commit: rollback is enabled by default
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


PgSessionDep = Annotated[AsyncSession, Depends(get_db)]


# Repository dependencies
def get_patient_repo(db: PgSessionDep) -> PatientRepo:
    return PatientRepo(db)


def get_case_repo(db: PgSessionDep) -> CaseRepo:
    return CaseRepo(db)


def get_device_repo(db: PgSessionDep) -> DeviceRepo:
    return DeviceRepo(db)


def get_wearable_repo(db: PgSessionDep) -> WearableRepo:
    return WearableRepo(db)


def get_context_repo(db: PgSessionDep) -> ContextRepo:
    return ContextRepo(db)


def get_assignment_repo(db: PgSessionDep) -> AssignmentRepo:
    return AssignmentRepo(db)


def get_fhir_mapping_repo(db: PgSessionDep) -> FHIRMappingRepo:
    return FHIRMappingRepo(db)


def get_dot_dependency_file_repo(db: PgSessionDep) -> DotDependencyFileRepo:
    return DotDependencyFileRepo(db)


PatientRepoDep = Annotated[PatientRepo, Depends(get_patient_repo)]
CaseRepoDep = Annotated[CaseRepo, Depends(get_case_repo)]
DeviceRepoDep = Annotated[DeviceRepo, Depends(get_device_repo)]
WearableRepoDep = Annotated[WearableRepo, Depends(get_wearable_repo)]
ContextRepoDep = Annotated[ContextRepo, Depends(get_context_repo)]
AssignmentRepoDep = Annotated[AssignmentRepo, Depends(get_assignment_repo)]
FHIRMappingRepoDep = Annotated[FHIRMappingRepo, Depends(get_fhir_mapping_repo)]
DotDependencyFileRepoDep = Annotated[DotDependencyFileRepo, Depends(get_dot_dependency_file_repo)]


# Service dependencies
def get_patient_service(repo: PatientRepoDep) -> PatientService:
    return PatientService(repo)


def get_case_service(repo: CaseRepoDep) -> CaseService:
    return CaseService(repo)


def get_device_service(repo: DeviceRepoDep) -> DeviceService:
    return DeviceService(repo)


def get_wearable_service(repo: WearableRepoDep) -> WearableService:
    return WearableService(repo)


def get_context_service(repo: ContextRepoDep) -> ContextService:
    return ContextService(repo)


def get_assignment_service(
    db: PgSessionDep,
    device_repo: DeviceRepoDep,
    wearable_repo: WearableRepoDep,
    case_repo: CaseRepoDep,
    assignment_repo: AssignmentRepoDep,
) -> AssignmentService:
    return AssignmentService(db, device_repo, wearable_repo, case_repo, assignment_repo)


def get_telemetry_service(request: Request) -> TelemetryService:
    return request.app.state.telemetry_service


def get_fhir_mapping_service(repo: FHIRMappingRepoDep) -> FHIRMappingService:
    return FHIRMappingService(repo)


def get_dot_dependency_file_service(repo: DotDependencyFileRepoDep) -> DotDependencyFileService:
    return DotDependencyFileService(repo)


async def get_graphql_context(
    request: Request,
    telemetry_service: Annotated[TelemetryService, Depends(get_telemetry_service)],
) -> GraphQLContext:
    db_semaphore = request.app.state.graphql_db_semaphore

    return {
        "request": request,
        "session_factory": AsyncSessionLocal,
        "db_semaphore": db_semaphore,
        "loaders": Loaders(AsyncSessionLocal, db_semaphore),
        "telemetry_service": telemetry_service,
    }


PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
CaseServiceDep = Annotated[CaseService, Depends(get_case_service)]
DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
WearableServiceDep = Annotated[WearableService, Depends(get_wearable_service)]
ContextServiceDep = Annotated[ContextService, Depends(get_context_service)]
AssignmentServiceDep = Annotated[AssignmentService, Depends(get_assignment_service)]
TelemetryServiceDep = Annotated[TelemetryService, Depends(get_telemetry_service)]
FHIRMappingServiceDep = Annotated[FHIRMappingService, Depends(get_fhir_mapping_service)]
DotDependencyFileServiceDep = Annotated[DotDependencyFileService, Depends(get_dot_dependency_file_service)]

# Filter and sorting dependencies
PatientFiltersDep = Annotated[FilterSet, Depends(PatientFilters)]
PatientSortingDep = Annotated[SortingValues, Depends(PatientSorting)]
CaseFiltersDep = Annotated[FilterSet, Depends(CaseFilters)]
CaseSortingDep = Annotated[SortingValues, Depends(CaseSorting)]
DeviceFiltersDep = Annotated[FilterSet, Depends(DeviceFilters)]
DeviceSortingDep = Annotated[SortingValues, Depends(DeviceSorting)]
WearableFiltersDep = Annotated[FilterSet, Depends(WearableFilters)]
WearableSortingDep = Annotated[SortingValues, Depends(WearableSorting)]
ContextFiltersDep = Annotated[FilterSet, Depends(ContextFilters)]
ContextSortingDep = Annotated[SortingValues, Depends(ContextSorting)]
FHIRMappingFiltersDep = Annotated[FilterSet, Depends(FHIRMappingFilters)]
FHIRMappingSortingDep = Annotated[SortingValues, Depends(FHIRMappingSorting)]
DotDependencyFileFiltersDep = Annotated[FilterSet, Depends(DotDependencyFileFilters)]
DotDependencyFileSortingDep = Annotated[SortingValues, Depends(DotDependencyFileSorting)]
