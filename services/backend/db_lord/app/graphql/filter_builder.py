"""
Filter builder for converting GraphQL FilterInput to SQLAlchemy expressions.
"""

from typing import Any

from sqlalchemy import ColumnElement, and_, not_, or_
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase
from strawberry.types.maybe import Some

from app.graphql.inputs import FilterCondition, FilterInput, FilterOperator, FilterValue


def _extract_filter_value(value: FilterValue) -> object:
    if isinstance(value.string, Some):
        return value.string.value
    if isinstance(value.integer, Some):
        return value.integer.value
    if isinstance(value.float_val, Some):
        return value.float_val.value
    if isinstance(value.boolean, Some):
        return value.boolean.value
    if isinstance(value.uuid, Some):
        return value.uuid.value
    if isinstance(value.date, Some):
        return value.date.value
    if isinstance(value.datetime, Some):
        return value.datetime.value
    if isinstance(value.decimal, Some):
        return value.decimal.value
    if isinstance(value.string_list, Some):
        return value.string_list.value
    if isinstance(value.integer_list, Some):
        return value.integer_list.value
    if isinstance(value.uuid_list, Some):
        return value.uuid_list.value

    raise ValueError("FilterValue must specify exactly one value")


class FilterBuilder:
    """
    Builds SQLAlchemy filter expressions from GraphQL FilterInput
    """

    def __init__(self, model: type[DeclarativeBase]):
        self.model = model
        mapper = sa_inspect(model)
        self._columns: dict[str, Any] = {attr.key: getattr(model, attr.key) for attr in mapper.column_attrs}

    def build(self, filter_input: FilterInput | None) -> ColumnElement[bool] | None:
        """
        Convert a FilterInput to a SQLAlchemy WHERE clause.

        Returns None if no filter is provided (select all).
        """
        if filter_input is None:
            return None
        return self._build_node(filter_input)

    def _build_node(self, node: FilterInput) -> ColumnElement[bool]:
        """Recursively build filter expression from FilterInput node."""
        branch_count = sum(
            [
                node.condition is not None,
                node.and_ is not None,
                node.or_ is not None,
                node.not_ is not None,
            ]
        )
        if branch_count != 1:
            raise ValueError("FilterInput must include exactly one of: condition, and, or, not")
        if node.condition is not None:
            return self._build_condition(node.condition)
        if node.and_ is not None:
            if not node.and_:
                raise ValueError("FilterInput and must contain at least one nested filter")
            clauses = [self._build_node(child) for child in node.and_]
            return and_(*clauses) if clauses else and_(True)
        if node.or_ is not None:
            if not node.or_:
                raise ValueError("FilterInput or must contain at least one nested filter")
            clauses = [self._build_node(child) for child in node.or_]
            return or_(*clauses) if clauses else or_(False)
        if node.not_ is not None:
            return not_(self._build_node(node.not_))

        # Empty node -> return true (no filtering)
        return and_(True)

    def _build_condition(self, cond: FilterCondition) -> ColumnElement[bool]:
        """Build a single condition expression."""
        column = self._columns.get(cond.field)
        if column is None:
            raise ValueError(f"Unknown field '{cond.field}' on {self.model.__name__}")

        value = _extract_filter_value(cond.value) if cond.value else None

        # Build expression based on operator
        match cond.op:
            case FilterOperator.EQ:
                return column == value
            case FilterOperator.NE:
                return column != value
            case FilterOperator.GT:
                return column > value
            case FilterOperator.GTE:
                return column >= value
            case FilterOperator.LT:
                return column < value
            case FilterOperator.LTE:
                return column <= value
            case FilterOperator.IN:
                return column.in_(value) if value else column.in_([])
            case FilterOperator.NOT_IN:
                return column.not_in(value) if value else column.not_in([])
            case FilterOperator.IS_NULL:
                if value is True or value is None:
                    return column.is_(None)
                return column.is_not(None)
            case FilterOperator.ILIKE:
                return column.ilike(value) if value else column.ilike("")
            case FilterOperator.CONTAINS:
                # Probably disallow this cause it can lead to very expensive queries. Probably better to just use ILIKE
                pattern = f"%{value}%" if value else "%%"
                return column.ilike(pattern)
            case _:
                raise ValueError(f"Unsupported operator: {cond.op}")


def apply_filter(model: type[DeclarativeBase], filter_input: FilterInput | None) -> ColumnElement[bool] | None:
    """
    Returns None if no filter, allowing:
        where_clause = apply_filter(Model, filter_input)
        query = select(Model)
        if where_clause is not None:
            query = query.where(where_clause)
    """
    return FilterBuilder(model).build(filter_input)
