from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres.orm import CaseContext, Context
from app.db.postgres.repos.base import BaseRepo, GroupedConnectionPage, grouped_page_from_ranked_subquery
from app.schemas.context import ContextCreate, ContextUpdate


class ContextRepo(BaseRepo[Context, ContextCreate, ContextUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Context, db)

    async def list_by_case_ids_connection(
        self,
        case_ids: list[UUID],
        page_size: int,
        fetch_backward: bool,
        after_id: UUID | None = None,
        before_id: UUID | None = None,
    ) -> GroupedConnectionPage[Context]:
        """GraphQL connection helper: list contexts grouped by case id."""
        if not case_ids:
            return GroupedConnectionPage(items_by_parent={}, has_extra_by_parent={})

        order_expr = CaseContext.context_id.asc() if fetch_backward else CaseContext.context_id.desc()
        ranked = select(
            CaseContext.case_id.label("parent_id"),
            CaseContext.context_id.label("node_id"),
            func.row_number().over(partition_by=CaseContext.case_id, order_by=order_expr).label("rn"),
        ).where(CaseContext.case_id.in_(case_ids))

        if after_id is not None:
            ranked = ranked.where(CaseContext.context_id < after_id)
        if before_id is not None:
            ranked = ranked.where(CaseContext.context_id > before_id)

        ranked_subquery = ranked.subquery()
        return await grouped_page_from_ranked_subquery(
            db=self.db,
            parent_ids=case_ids,
            ranked_subquery=ranked_subquery,
            page_size=page_size,
            fetch_backward=fetch_backward,
            value_from_row=lambda row: row.node_id,
            load_nodes_by_value=self.map_by_ids,
            cursor_values_from=lambda node, node_id: (node_id if node.id == node_id else node.id,),
        )
