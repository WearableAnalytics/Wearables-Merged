from app.db.postgres.orm import DotDependencyFile, FHIRMapping
from app.db.postgres.repos.fhir_mapping_repo import DotDependencyFileRepo, FHIRMappingRepo
from app.schemas.fhir_mapping import (
    DotDependencyFileCreate,
    DotDependencyFileUpdate,
    FHIRMappingCreate,
    FHIRMappingUpdate,
)
from app.services.base import BaseService


class FHIRMappingService(BaseService[FHIRMapping, FHIRMappingCreate, FHIRMappingUpdate, FHIRMappingRepo]):
    def __init__(self, repo: FHIRMappingRepo):
        super().__init__(repo)


class DotDependencyFileService(
    BaseService[DotDependencyFile, DotDependencyFileCreate, DotDependencyFileUpdate, DotDependencyFileRepo]
):
    def __init__(self, repo: DotDependencyFileRepo):
        super().__init__(repo)
