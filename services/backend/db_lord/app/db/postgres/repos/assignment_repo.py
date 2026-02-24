from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, func, insert, or_, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.db.postgres.orm import CaseContext, CaseDevice, CaseWearable, Device, Wearable
from app.db.postgres.repos.base import GroupedConnectionPage, grouped_page_from_ranked_subquery, ordered_unique
from app.db.postgres.repos.types import AssignmentCursorKey


def _active_assignment_window(
    model: type[CaseDevice] | type[CaseWearable], now_ref: datetime | ColumnElement[datetime]
) -> ColumnElement[bool]:
    return and_(
        model.assigned_from <= now_ref,
        or_(
            model.assigned_to.is_(None),
            model.assigned_to > now_ref,
        ),
    )


def _seek_lt_datetime_uuid(
    dt_col: ColumnElement[datetime] | InstrumentedAttribute[datetime],
    uuid_col: ColumnElement[UUID] | InstrumentedAttribute[UUID],
    key: AssignmentCursorKey,
) -> ColumnElement[bool]:
    dt_value, uuid_value = key
    return or_(dt_col < dt_value, and_(dt_col == dt_value, uuid_col < uuid_value))


def _seek_gt_datetime_uuid(
    dt_col: ColumnElement[datetime] | InstrumentedAttribute[datetime],
    uuid_col: ColumnElement[UUID] | InstrumentedAttribute[UUID],
    key: AssignmentCursorKey,
) -> ColumnElement[bool]:
    dt_value, uuid_value = key
    return or_(dt_col > dt_value, and_(dt_col == dt_value, uuid_col > uuid_value))


class AssignmentRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _db_now_expr(self) -> ColumnElement[datetime]:
        return func.clock_timestamp()

    async def _get_active_assignment[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        case_id_column: InstrumentedAttribute[UUID],
        asset_id_column: InstrumentedAttribute[UUID],
        case_id: UUID,
        asset_id: UUID,
    ) -> TAssignment | None:
        now_expr = self._db_now_expr()
        query = select(model).where(
            and_(case_id_column == case_id, asset_id_column == asset_id, _active_assignment_window(model, now_expr))
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_last_assignment[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        case_id_column: InstrumentedAttribute[UUID],
        tie_breaker_column: InstrumentedAttribute[UUID],
        case_id: UUID,
    ) -> TAssignment | None:
        query = (
            select(model)
            .where(case_id_column == case_id)
            .order_by(model.assigned_from.desc(), tie_breaker_column.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _list_assignments_connection[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        parent_ids: list[UUID],
        parent_column: InstrumentedAttribute[UUID],
        case_id_column: InstrumentedAttribute[UUID],
        asset_id_column: InstrumentedAttribute[UUID],
        cursor_tie_column: InstrumentedAttribute[UUID],
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[TAssignment]:
        if not parent_ids:
            return GroupedConnectionPage(items_by_parent={}, has_extra_by_parent={})

        assigned_from_order = model.assigned_from.asc() if fetch_backward else model.assigned_from.desc()
        tie_breaker_order = cursor_tie_column.asc() if fetch_backward else cursor_tie_column.desc()
        ranked = select(
            parent_column.label("parent_id"),
            case_id_column.label("case_id"),
            asset_id_column.label("asset_id"),
            model.assigned_from.label("assigned_from"),
            func.row_number()
            .over(partition_by=parent_column, order_by=(assigned_from_order, tie_breaker_order))
            .label("rn"),
        ).where(parent_column.in_(parent_ids))

        if after_key is not None:
            ranked = ranked.where(_seek_lt_datetime_uuid(model.assigned_from, cursor_tie_column, after_key))
        if before_key is not None:
            ranked = ranked.where(_seek_gt_datetime_uuid(model.assigned_from, cursor_tie_column, before_key))

        ranked_subquery = ranked.subquery()

        async def _load_assignments_by_key(
            unique_keys: list[tuple[UUID, UUID, datetime]],
        ) -> dict[tuple[UUID, UUID, datetime], TAssignment]:
            assignments_stmt = select(model).where(
                tuple_(case_id_column, asset_id_column, model.assigned_from).in_(unique_keys)
            )
            assignments_result = await self.db.execute(assignments_stmt)
            return {
                (assignment.case_id, getattr(assignment, asset_id_column.key), assignment.assigned_from): assignment
                for assignment in assignments_result.scalars()
            }

        return await grouped_page_from_ranked_subquery(
            db=self.db,
            parent_ids=parent_ids,
            ranked_subquery=ranked_subquery,
            page_size=page_size,
            fetch_backward=fetch_backward,
            value_from_row=lambda row: (row.case_id, row.asset_id, row.assigned_from),
            load_nodes_by_value=_load_assignments_by_key,
            cursor_values_from=lambda assignment, _key: (
                assignment.assigned_from,
                getattr(assignment, cursor_tie_column.key),
            ),
        )

    async def _assign[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        case_id_column: InstrumentedAttribute[UUID],
        asset_id_column: InstrumentedAttribute[UUID],
        case_id: UUID,
        asset_id: UUID,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> TAssignment:
        stmt = (
            insert(model)
            .values(
                **{
                    case_id_column.key: case_id,
                    asset_id_column.key: asset_id,
                    "assigned_from": start_time if start_time is not None else self._db_now_expr(),
                    "assigned_to": end_time,
                }
            )
            .returning(model)
        )
        assignment = await self.db.scalar(stmt)
        if assignment is None:
            raise RuntimeError("Assignment INSERT did not return a row.")
        return assignment

    async def _unassign[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        case_id_column: InstrumentedAttribute[UUID],
        asset_id_column: InstrumentedAttribute[UUID],
        case_id: UUID,
        asset_id: UUID,
        end_time: datetime | None = None,
    ) -> TAssignment | None:
        now_expr = self._db_now_expr()
        effective_end_time = end_time if end_time is not None else self._db_now_expr()
        query = (
            update(model)
            .where(
                and_(
                    case_id_column == case_id,
                    asset_id_column == asset_id,
                    _active_assignment_window(model, now_expr),
                )
            )
            .values(assigned_to=effective_end_time)
            .returning(model)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _unassign_last[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        case_id_column: InstrumentedAttribute[UUID],
        asset_id_column: InstrumentedAttribute[UUID],
        case_id: UUID,
        end_time: datetime | None = None,
    ) -> TAssignment | None:
        now_expr = self._db_now_expr()
        effective_end_time = end_time if end_time is not None else self._db_now_expr()
        subquery = (
            select(asset_id_column)
            .where(case_id_column == case_id, _active_assignment_window(model, now_expr))
            .order_by(model.assigned_from.desc(), asset_id_column.desc())
            .limit(1)
            .scalar_subquery()
        )
        query = (
            update(model)
            .where(
                and_(
                    case_id_column == case_id,
                    asset_id_column == subquery,
                    _active_assignment_window(model, now_expr),
                )
            )
            .values(assigned_to=effective_end_time)
            .returning(model)
        )
        return await self.db.scalar(query)

    async def _delete_assignment[TAssignment: CaseDevice | CaseWearable](
        self,
        *,
        model: type[TAssignment],
        case_id_column: InstrumentedAttribute[UUID],
        asset_id_column: InstrumentedAttribute[UUID],
        case_id: UUID,
        asset_id: UUID,
        assigned_from: datetime | None = None,
    ) -> TAssignment | None:
        if assigned_from is not None:
            stmt = (
                delete(model)
                .where(
                    and_(
                        case_id_column == case_id,
                        asset_id_column == asset_id,
                        model.assigned_from == assigned_from,
                    )
                )
                .returning(model)
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()

        candidates_cte = (
            select(
                case_id_column.label("case_id"),
                asset_id_column.label("asset_id"),
                model.assigned_from.label("assigned_from"),
            )
            .where(and_(case_id_column == case_id, asset_id_column == asset_id))
            .cte("candidates")
        )
        stmt = (
            delete(model)
            .where(
                tuple_(case_id_column, asset_id_column, model.assigned_from).in_(
                    select(candidates_cte.c.case_id, candidates_cte.c.asset_id, candidates_cte.c.assigned_from)
                )
            )
            .where(select(func.count()).select_from(candidates_cte).scalar_subquery() == 1)
            .returning(model)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    # Devices
    async def get_active_device(self, case_id: UUID, device_id: UUID) -> CaseDevice | None:
        return await self._get_active_assignment(
            model=CaseDevice,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            case_id=case_id,
            asset_id=device_id,
        )

    async def get_last_device_assignment(self, case_id: UUID) -> CaseDevice | None:
        return await self._get_last_assignment(
            model=CaseDevice,
            case_id_column=CaseDevice.case_id,
            tie_breaker_column=CaseDevice.device_id,
            case_id=case_id,
        )

    async def list_device_assignments_by_case_ids_connection(
        self,
        case_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[CaseDevice]:
        return await self._list_assignments_connection(
            model=CaseDevice,
            parent_ids=case_ids,
            parent_column=CaseDevice.case_id,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            cursor_tie_column=CaseDevice.device_id,
            page_size=page_size,
            fetch_backward=fetch_backward,
            after_key=after_key,
            before_key=before_key,
        )

    async def list_device_assignments_by_device_ids_connection(
        self,
        device_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[CaseDevice]:
        return await self._list_assignments_connection(
            model=CaseDevice,
            parent_ids=device_ids,
            parent_column=CaseDevice.device_id,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            cursor_tie_column=CaseDevice.case_id,
            page_size=page_size,
            fetch_backward=fetch_backward,
            after_key=after_key,
            before_key=before_key,
        )

    async def assign_device(
        self, case_id: UUID, device_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> CaseDevice | None:
        return await self._assign(
            model=CaseDevice,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            case_id=case_id,
            asset_id=device_id,
            start_time=start_time,
            end_time=end_time,
        )

    async def unassign_last_device(self, case_id: UUID, end_time: datetime | None = None) -> CaseDevice | None:
        return await self._unassign_last(
            model=CaseDevice,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            case_id=case_id,
            end_time=end_time,
        )

    async def unassign_device(
        self, case_id: UUID, device_id: UUID, end_time: datetime | None = None
    ) -> CaseDevice | None:
        return await self._unassign(
            model=CaseDevice,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            case_id=case_id,
            asset_id=device_id,
            end_time=end_time,
        )

    async def delete_device_assignment(
        self, case_id: UUID, device_id: UUID, assigned_from: datetime | None = None
    ) -> CaseDevice | None:
        return await self._delete_assignment(
            model=CaseDevice,
            case_id_column=CaseDevice.case_id,
            asset_id_column=CaseDevice.device_id,
            case_id=case_id,
            asset_id=device_id,
            assigned_from=assigned_from,
        )

    # Wearables
    async def get_active_wearable(self, case_id: UUID, wearable_id: UUID) -> CaseWearable | None:
        return await self._get_active_assignment(
            model=CaseWearable,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            case_id=case_id,
            asset_id=wearable_id,
        )

    async def get_last_wearable_assignment(self, case_id: UUID) -> CaseWearable | None:
        return await self._get_last_assignment(
            model=CaseWearable,
            case_id_column=CaseWearable.case_id,
            tie_breaker_column=CaseWearable.wearable_id,
            case_id=case_id,
        )

    async def list_wearable_assignments_by_case_ids_connection(
        self,
        case_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[CaseWearable]:
        return await self._list_assignments_connection(
            model=CaseWearable,
            parent_ids=case_ids,
            parent_column=CaseWearable.case_id,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            cursor_tie_column=CaseWearable.wearable_id,
            page_size=page_size,
            fetch_backward=fetch_backward,
            after_key=after_key,
            before_key=before_key,
        )

    async def list_wearable_assignments_by_wearable_ids_connection(
        self,
        wearable_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[CaseWearable]:
        return await self._list_assignments_connection(
            model=CaseWearable,
            parent_ids=wearable_ids,
            parent_column=CaseWearable.wearable_id,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            cursor_tie_column=CaseWearable.case_id,
            page_size=page_size,
            fetch_backward=fetch_backward,
            after_key=after_key,
            before_key=before_key,
        )

    async def list_active_devices_by_case_ids_connection(
        self,
        case_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[Device]:
        return await self._list_active_assets_by_case_ids_connection(
            case_ids=case_ids,
            page_size=page_size,
            fetch_backward=fetch_backward,
            after_key=after_key,
            before_key=before_key,
            assignment_model=CaseDevice,
            node_model=Device,
            node_id_column=CaseDevice.device_id,
            node_pk_column=Device.id,
        )

    async def list_active_wearables_by_case_ids_connection(
        self,
        case_ids: list[UUID],
        *,
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None = None,
        before_key: AssignmentCursorKey | None = None,
    ) -> GroupedConnectionPage[Wearable]:
        return await self._list_active_assets_by_case_ids_connection(
            case_ids=case_ids,
            page_size=page_size,
            fetch_backward=fetch_backward,
            after_key=after_key,
            before_key=before_key,
            assignment_model=CaseWearable,
            node_model=Wearable,
            node_id_column=CaseWearable.wearable_id,
            node_pk_column=Wearable.id,
        )

    async def _list_active_assets_by_case_ids_connection[TNode](
        self,
        *,
        case_ids: list[UUID],
        page_size: int,
        fetch_backward: bool,
        after_key: AssignmentCursorKey | None,
        before_key: AssignmentCursorKey | None,
        assignment_model: type[CaseDevice] | type[CaseWearable],
        node_model: type[TNode],
        node_id_column: InstrumentedAttribute[UUID],
        node_pk_column: InstrumentedAttribute[UUID],
    ) -> GroupedConnectionPage[TNode]:
        if not case_ids:
            return GroupedConnectionPage(items_by_parent={}, has_extra_by_parent={})

        now_expr = self._db_now_expr()
        latest_assignments = (
            select(
                assignment_model.case_id.label("parent_id"),
                node_id_column.label("node_id"),
                func.max(assignment_model.assigned_from).label("latest_assigned_from"),
            )
            .where(assignment_model.case_id.in_(case_ids), _active_assignment_window(assignment_model, now_expr))
            .group_by(assignment_model.case_id, node_id_column)
        )

        latest_subquery = latest_assignments.subquery()
        ranked_order = (
            (
                latest_subquery.c.latest_assigned_from.asc(),
                latest_subquery.c.node_id.asc(),
            )
            if fetch_backward
            else (
                latest_subquery.c.latest_assigned_from.desc(),
                latest_subquery.c.node_id.desc(),
            )
        )
        ranked = select(
            latest_subquery.c.parent_id,
            latest_subquery.c.node_id,
            latest_subquery.c.latest_assigned_from,
            func.row_number().over(partition_by=latest_subquery.c.parent_id, order_by=ranked_order).label("rn"),
        )

        if after_key is not None:
            ranked = ranked.where(
                _seek_lt_datetime_uuid(
                    latest_subquery.c.latest_assigned_from,
                    latest_subquery.c.node_id,
                    after_key,
                )
            )
        if before_key is not None:
            ranked = ranked.where(
                _seek_gt_datetime_uuid(
                    latest_subquery.c.latest_assigned_from,
                    latest_subquery.c.node_id,
                    before_key,
                )
            )

        ranked_subquery = ranked.subquery()

        async def _load_nodes_by_value(values: list[tuple[UUID, datetime]]) -> dict[tuple[UUID, datetime], TNode]:
            unique_node_ids = ordered_unique(node_id for node_id, _timestamp in values)
            if not unique_node_ids:
                return {}

            nodes_stmt = select(node_pk_column, node_model).where(node_pk_column.in_(unique_node_ids))
            nodes_result = await self.db.execute(nodes_stmt)
            nodes_by_id: dict[UUID, TNode] = {node_id: node for node_id, node in nodes_result}
            return {
                (node_id, timestamp): node
                for node_id, timestamp in values
                if (node := nodes_by_id.get(node_id)) is not None
            }

        return await grouped_page_from_ranked_subquery(
            db=self.db,
            parent_ids=case_ids,
            ranked_subquery=ranked_subquery,
            page_size=page_size,
            fetch_backward=fetch_backward,
            value_from_row=lambda row: (row.node_id, row.latest_assigned_from),
            load_nodes_by_value=_load_nodes_by_value,
            cursor_values_from=lambda _node, key: (key[1], key[0]),
        )

    async def assign_wearable(
        self, case_id: UUID, wearable_id: UUID, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> CaseWearable | None:
        return await self._assign(
            model=CaseWearable,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            case_id=case_id,
            asset_id=wearable_id,
            start_time=start_time,
            end_time=end_time,
        )

    async def unassign_last_wearable(self, case_id: UUID, end_time: datetime | None = None) -> CaseWearable | None:
        return await self._unassign_last(
            model=CaseWearable,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            case_id=case_id,
            end_time=end_time,
        )

    async def unassign_wearable(
        self, case_id: UUID, wearable_id: UUID, end_time: datetime | None = None
    ) -> CaseWearable | None:
        return await self._unassign(
            model=CaseWearable,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            case_id=case_id,
            asset_id=wearable_id,
            end_time=end_time,
        )

    async def delete_wearable_assignment(
        self, case_id: UUID, wearable_id: UUID, assigned_from: datetime | None = None
    ) -> CaseWearable | None:
        return await self._delete_assignment(
            model=CaseWearable,
            case_id_column=CaseWearable.case_id,
            asset_id_column=CaseWearable.wearable_id,
            case_id=case_id,
            asset_id=wearable_id,
            assigned_from=assigned_from,
        )

    # Contexts
    async def link_context(self, case_id: UUID, context_id: UUID) -> CaseContext | None:
        query = (
            pg_insert(CaseContext)
            .values(case_id=case_id, context_id=context_id)
            .on_conflict_do_nothing(index_elements=["case_id", "context_id"])
        ).returning(CaseContext)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def unlink_context(self, case_id: UUID, context_id: UUID) -> CaseContext | None:
        query = (
            delete(CaseContext)
            .where(and_(CaseContext.case_id == case_id, CaseContext.context_id == context_id))
            .returning(CaseContext)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
