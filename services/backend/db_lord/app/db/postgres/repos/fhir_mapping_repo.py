from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import DotDependencyFile, FHIRMapping
from app.db.postgres.repos.base import BaseRepo, GroupedConnectionPage, grouped_page_from_ranked_subquery
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

    async def list_by_mapping_ids_connection(
        self,
        mapping_ids: list[UUID],
        page_size: int,
        fetch_backward: bool,
        after_id: UUID | None = None,
        before_id: UUID | None = None,
    ) -> GroupedConnectionPage[DotDependencyFile]:
        """GraphQL connection helper: dot dependency files grouped by mapping id."""
        if not mapping_ids:
            return GroupedConnectionPage(items_by_parent={}, has_extra_by_parent={})

        order_expr = DotDependencyFile.id.asc() if fetch_backward else DotDependencyFile.id.desc()
        ranked = select(
            DotDependencyFile.mapping_id.label("parent_id"),
            DotDependencyFile.id.label("node_id"),
            func.row_number().over(partition_by=DotDependencyFile.mapping_id, order_by=order_expr).label("rn"),
        ).where(DotDependencyFile.mapping_id.in_(mapping_ids))

        if after_id is not None:
            ranked = ranked.where(DotDependencyFile.id < after_id)
        if before_id is not None:
            ranked = ranked.where(DotDependencyFile.id > before_id)

        ranked_subquery = ranked.subquery()
        return await grouped_page_from_ranked_subquery(
            db=self.db,
            parent_ids=mapping_ids,
            ranked_subquery=ranked_subquery,
            page_size=page_size,
            fetch_backward=fetch_backward,
            value_from_row=lambda row: row.node_id,
            load_nodes_by_value=self.map_by_ids,
            cursor_values_from=lambda _node, node_id: (node_id,),
        )
