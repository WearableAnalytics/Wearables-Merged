from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import DotDependencyFile, FHIRMapping
from app.db.postgres.repos.base import BaseRepo
from app.schemas.fhir_mapping import (
    DotDependencyFileBase,
    DotDependencyFileCreate,
    FHIRMappingCreate,
    FHIRMappingUpdate,
)


class FHIRMappingRepo(BaseRepo[FHIRMapping, FHIRMappingCreate, FHIRMappingUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(FHIRMapping, db)


class DotDependencyFileRepo(BaseRepo[DotDependencyFile, DotDependencyFileCreate, DotDependencyFileBase]):
    def __init__(self, db: AsyncSession):
        super().__init__(DotDependencyFile, db)
