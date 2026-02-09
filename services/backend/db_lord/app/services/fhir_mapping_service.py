from app.db.postgres.orm import FHIRMapping, FHIRMappingTree
from app.db.postgres.repos.fhir_mapping_repo import FHIRMappingRepo, FHIRMappingTreeRepo
from app.schemas.fhir_mapping import FHIRMappingCreate, FHIRMappingTreeCreate, FHIRMappingTreeUpdate, FHIRMappingUpdate
from app.services.base import BaseService


class FHIRMappingService(BaseService[FHIRMapping, FHIRMappingCreate, FHIRMappingUpdate, FHIRMappingRepo]):
    def __init__(self, repo: FHIRMappingRepo):
        super().__init__(repo)


class FHIRMappingTreeService(
    BaseService[FHIRMappingTree, FHIRMappingTreeCreate, FHIRMappingTreeUpdate, FHIRMappingTreeRepo]
):
    def __init__(self, repo: FHIRMappingTreeRepo):
        super().__init__(repo)
