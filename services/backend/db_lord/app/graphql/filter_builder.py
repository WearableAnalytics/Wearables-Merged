"""
Filter builder for converting GraphQL FilterInput to SQLAlchemy expressions.
"""

from functools import cache
from typing import Any

from sqlalchemy import ColumnElement, and_, not_, or_
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, InstrumentedAttribute
from sqlalchemy.sql.sqltypes import Enum as SAEnumType
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import String
from strawberry.types.maybe import Some

from app.graphql.inputs import FilterCondition, FilterInput, FilterOperator, FilterValue

_FILTER_VALUE_FIELDS = (
    "string",
    "integer",
    "float_val",
    "boolean",
    "uuid",
    "date",
    "datetime",
    "decimal",
    "string_list",
    "integer_list",
    "uuid_list",
)


def _extract_filter_value(value: FilterValue) -> object:
    for field_name in _FILTER_VALUE_FIELDS:
        maybe_value = getattr(value, field_name)
        if isinstance(maybe_value, Some):
            return maybe_value.value

    raise ValueError("FilterValue must specify exactly one value")


def _is_text_column(column: InstrumentedAttribute[Any]) -> bool:
    column_type: TypeEngine[Any] = column.property.columns[0].type
    return isinstance(column_type, String) and not isinstance(column_type, SAEnumType)


class FilterBuilder:
    """
    Builds SQLAlchemy filter expressions from GraphQL FilterInput
    """

    def __init__(self, model: type[DeclarativeBase]):
        self.model = model
        self._columns = self._resolve_model_columns(model)

    @staticmethod
    @cache
    def _resolve_model_columns(model: type[DeclarativeBase]) -> dict[str, InstrumentedAttribute[Any]]:
        mapper = sa_inspect(model)
        return {attr.key: getattr(model, attr.key) for attr in mapper.column_attrs}

    def build(self, filter_input: FilterInput | None) -> ColumnElement[bool] | None:
        """
        Convert a FilterInput to a SQLAlchemy WHERE clause.

        Returns None if no filter is provided (select all).
        """
        if filter_input is None:
            return None
        return self._build_node(filter_input)

    def _build_node(self, node: FilterInput) -> ColumnElement[bool]:
        """Recursively build a filter expression from a FilterInput node."""
        if isinstance(node.condition, Some):
            return self._build_condition(node.condition.value)
        if isinstance(node.and_, Some):
            if not node.and_.value:
                raise ValueError("FilterInput and must contain at least one nested filter")
            return and_(*(self._build_node(child) for child in node.and_.value))
        if isinstance(node.or_, Some):
            if not node.or_.value:
                raise ValueError("FilterInput or must contain at least one nested filter")
            return or_(*(self._build_node(child) for child in node.or_.value))
        if isinstance(node.not_, Some):
            return not_(self._build_node(node.not_.value))

        raise ValueError("FilterInput must include exactly one of: condition, and, or, not")

    def _build_condition(self, cond: FilterCondition) -> ColumnElement[bool]:
        """Build a single condition expression."""
        column = self._columns.get(cond.field)
        if column is None:
            raise ValueError(f"Unknown field '{cond.field}' on {self.model.__name__}")

        value = _extract_filter_value(cond.value) if cond.value else None

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
                if not isinstance(value, (list, tuple, set, frozenset)):
                    raise ValueError("Filter operator IN requires a list-like value")
                iterable_values = list(value)
                if not iterable_values:
                    raise ValueError("Filter operator IN requires a non-empty list-like value")
                return column.in_(iterable_values)
            case FilterOperator.NOT_IN:
                if not isinstance(value, (list, tuple, set, frozenset)):
                    raise ValueError("Filter operator NOT_IN requires a list-like value")
                iterable_values = list(value)
                if not iterable_values:
                    raise ValueError("Filter operator NOT_IN requires a non-empty list-like value")
                return column.not_in(iterable_values)
            case FilterOperator.IS_NULL:
                if value is True or value is None:
                    return column.is_(None)
                return column.is_not(None)
            case FilterOperator.ILIKE:
                if not _is_text_column(column):
                    raise ValueError(
                        f"Filter operator ILIKE is only supported for string fields on {self.model.__name__}."
                    )
                if not isinstance(value, str) or value == "":
                    raise ValueError("Filter operator ILIKE requires a non-empty string value")
                return column.ilike(value)
            case FilterOperator.CONTAINS:
                if not _is_text_column(column):
                    raise ValueError(
                        f"Filter operator CONTAINS is only supported for string fields on {self.model.__name__}."
                    )
                if not isinstance(value, str) or value == "":
                    raise ValueError("Filter operator CONTAINS requires a non-empty string value")
                pattern = f"%{value}%"
                return column.ilike(pattern)


def apply_filter(model: type[DeclarativeBase], filter_input: FilterInput | None) -> ColumnElement[bool] | None:
    """
    Returns None if no filter, allowing:
        where_clause = apply_filter(Model, filter_input)
        query = select(Model)
        if where_clause is not None:
            query = query.where(where_clause)
    """
    return FilterBuilder(model).build(filter_input)
