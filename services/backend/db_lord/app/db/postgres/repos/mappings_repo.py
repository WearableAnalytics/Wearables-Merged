from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.models.mapping import map_trees, mappings
from app.db.postgres.repos.base import BaseRepo
from app.schemas.mappings import MappingsCreate, MappingsUpdate, MapTreesCreate, MapTreesUpdate


class MappingsRepo(BaseRepo[mappings, MappingsCreate, MappingsUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(mappings, db)


class MapTreesRepo(BaseRepo[map_trees, MapTreesCreate, MapTreesUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(map_trees, db)
