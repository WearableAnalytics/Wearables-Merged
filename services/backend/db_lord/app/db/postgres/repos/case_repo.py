from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.postgres.orm import Case, CaseContext, CaseDevice, CaseWearable
from app.db.postgres.repos.base import (
    BaseRepo,
    GroupedConnectionPage,
    grouped_page_from_ranked_subquery,
)
from app.schemas.case import CaseCreate, CaseExpandableFields, CaseUpdate


class CaseRepo(BaseRepo[Case, CaseCreate, CaseUpdate]):
    def __init__(self, db: AsyncSession):
        super().__init__(Case, db)

    async def get_with_relations(self, id: UUID, expand: list[CaseExpandableFields]) -> Case | None:
        """
        Get a case with optional relationship expansion using ORM.
        """
        query = select(Case).where(Case.id == id)

        if CaseExpandableFields.DEVICES in expand:
            query = query.options(selectinload(Case.device_assignments).selectinload(CaseDevice.device))
        if CaseExpandableFields.WEARABLES in expand:
            query = query.options(selectinload(Case.wearable_assignments).selectinload(CaseWearable.wearable))
        if CaseExpandableFields.CONTEXTS in expand:
            query = query.options(selectinload(Case.contexts))
        if CaseExpandableFields.PATIENT in expand:
            query = query.options(joinedload(Case.patient))

        return await self.db.scalar(query)

    async def get_by_patient_id(self, patient_id: UUID) -> list[Case]:
        """Get all cases for a specific patient."""
        stmt = select(Case).where(Case.patient_id == patient_id)
        return list(await self.db.scalars(stmt))

    async def list_by_patient_ids_connection(
        self,
        patient_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_id: UUID | None = None,
        before_id: UUID | None = None,
    ) -> GroupedConnectionPage[Case]:
        if not patient_ids:
            return GroupedConnectionPage(items_by_parent={}, has_extra_by_parent={})

        order_expr = Case.id.asc() if fetch_backward else Case.id.desc()
        ranked = select(
            Case.patient_id.label("parent_id"),
            Case.id.label("node_id"),
            func.row_number().over(partition_by=Case.patient_id, order_by=order_expr).label("rn"),
        ).where(Case.patient_id.in_(patient_ids))

        if after_id is not None:
            ranked = ranked.where(Case.id < after_id)
        if before_id is not None:
            ranked = ranked.where(Case.id > before_id)

        ranked_subquery = ranked.subquery()
        return await grouped_page_from_ranked_subquery(
            db=self.db,
            parent_ids=patient_ids,
            ranked_subquery=ranked_subquery,
            page_size=page_size,
            fetch_backward=fetch_backward,
            value_from_row=lambda row: row.node_id,
            load_nodes_by_value=self.map_by_ids,
            cursor_values_from=lambda node, _node_id: (node.id,),
        )

    async def list_by_context_ids_connection(
        self,
        context_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_id: UUID | None = None,
        before_id: UUID | None = None,
    ) -> GroupedConnectionPage[Case]:
        if not context_ids:
            return GroupedConnectionPage(items_by_parent={}, has_extra_by_parent={})

        order_expr = CaseContext.case_id.asc() if fetch_backward else CaseContext.case_id.desc()
        ranked = select(
            CaseContext.context_id.label("parent_id"),
            CaseContext.case_id.label("node_id"),
            func.row_number().over(partition_by=CaseContext.context_id, order_by=order_expr).label("rn"),
        ).where(CaseContext.context_id.in_(context_ids))

        if after_id is not None:
            ranked = ranked.where(CaseContext.case_id < after_id)
        if before_id is not None:
            ranked = ranked.where(CaseContext.case_id > before_id)

        ranked_subquery = ranked.subquery()
        return await grouped_page_from_ranked_subquery(
            db=self.db,
            parent_ids=context_ids,
            ranked_subquery=ranked_subquery,
            page_size=page_size,
            fetch_backward=fetch_backward,
            value_from_row=lambda row: row.node_id,
            load_nodes_by_value=self.map_by_ids,
            cursor_values_from=lambda node, _node_id: (node.id,),
        )
