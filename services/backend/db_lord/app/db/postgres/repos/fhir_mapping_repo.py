from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import FHIRMapping, FHIRMappingTree
from app.db.postgres.repos.base import BaseRepo
from app.schemas.fhir_mapping import FHIRMappingCreate, FHIRMappingTreeBase, FHIRMappingTreeCreate, FHIRMappingUpdate


class FHIRMappingRepo(BaseRepo[FHIRMapping, FHIRMappingCreate, FHIRMappingUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(FHIRMapping, db)


class FHIRMappingTreeRepo(BaseRepo[FHIRMappingTree, FHIRMappingTreeCreate, FHIRMappingTreeBase]):
    def __init__(self, db: AsyncSession):
        super().__init__(FHIRMappingTree, db)
