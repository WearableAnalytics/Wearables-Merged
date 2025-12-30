from typing import Any, Dict, List, Optional, Union

from sqlalchemy import Table, delete, insert, select, update
from sqlalchemy.sql.dml import Delete, Insert, Update
from sqlalchemy.sql.selectable import Select

from models.sql import (
    case_contexts,
    case_devices,
    case_wearables,
    cases,
    contexts,
    devices,
    patients,
    wearables,
)

# Maybe dont do returning(*) just return what we need
# TODO: Add Pagination support all applicable functions
# In general add more verification and error handling
TABLE_MAP = {
    "patients": patients,
    "devices": devices,
    "wearables": wearables,
    "cases": cases,
    "contexts": contexts,
}

LINK_TABLE_MAP = {
    "device": case_devices,
    "wearable": case_wearables,
    "context": case_contexts,
}


# Helpers
def _get_table(name: str) -> Table:
    if name not in TABLE_MAP:
        raise ValueError(f"Unknown table: {name}")
    return TABLE_MAP[name]


def _get_link_table(name: str) -> Table:
    if name not in LINK_TABLE_MAP:
        raise ValueError(f"Unknown link type: {name}")
    return LINK_TABLE_MAP[name]


# Builders
def build_insert(table_name: str, data: Dict[str, Any]) -> Insert:
    t = _get_table(table_name)
    return insert(t).values(data).returning(t)


def build_get_one(table_name: str, record_id: str) -> Select:
    t = _get_table(table_name)
    return select(t).where(t.c.id == record_id)


def build_update(table_name: str, record_id: str, data: Dict[str, Any]) -> Update:
    t = _get_table(table_name)
    return update(t).where(t.c.id == record_id).values(data).returning(t)


def build_delete(table_name: str, record_id: str) -> Delete:
    t = _get_table(table_name)
    return delete(t).where(t.c.id == record_id)


def build_list_patients(filters: Dict[str, Any]) -> Select:
    query = select(patients)
    conditions = []

    # TODO: add way more filters and convenient mapping between API and DB fields
    # also probably find a way to make this not just a big mess of if statements
    if filters.get("lastname"):
        conditions.append(patients.c.name.ilike(f"%{filters['lastname']}%"))
    if filters.get("firstname"):
        conditions.append(patients.c.name.ilike(f"%{filters['firstname']}%"))
    if filters.get("sex"):
        conditions.append(patients.c.sex == filters["sex"])
    if filters.get("birthRangeStart"):
        conditions.append(patients.c.dob >= filters["birthRangeStart"])
    if filters.get("birthRangeEnd"):
        conditions.append(patients.c.dob <= filters["birthRangeEnd"])
    if filters.get("weightRangeStart"):
        conditions.append(patients.c.weight >= filters["weightRangeStart"])
    if filters.get("weightRangeEnd"):
        conditions.append(patients.c.weight <= filters["weightRangeEnd"])

    if conditions:
        query = query.where(*conditions)
    return query


def build_link_insert(link_type: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Insert:
    t = _get_link_table(link_type)
    return insert(t).values(data).returning(t)


def build_link_update(link_type: str, link_keys: Dict[str, Any], data: Dict[str, Any]) -> Update:
    # Safety check to stop full table updates
    if not link_keys:
        raise ValueError("Cannot update links without filter keys")

    t = _get_link_table(link_type)
    conditions = [t.c[key] == value for key, value in link_keys.items()]
    return update(t).where(*conditions).values(data).returning(t)


def build_link_delete(link_type: str, link_keys: Dict[str, Any]) -> Delete:
    if not link_keys:
        raise ValueError("Cannot delete links without filter keys")

    t = _get_link_table(link_type)
    # TODO: Handle errors in conditions
    conditions = [t.c[key] == value for key, value in link_keys.items()]
    return delete(t).where(*conditions)


def build_link_select(link_type: str, filters: Optional[Dict[str, Any]] = None) -> Select:
    t = _get_link_table(link_type)
    query = select(t)

    if filters:
        conditions = [t.c[key] == value for key, value in filters.items()]
        query = query.where(*conditions)

    return query


def build_case_rich_select(main_table_key: str, link_table_key: str, case_id: str) -> Select:
    """
    Joins main table (e.g. devices) with the Link Table (e.g. case_devices) to return the full object + assignment times
    """
    t_main = _get_table(main_table_key)
    t_link = _get_link_table(link_table_key)

    fk_column = f"{link_table_key}_id"  # Pretty janky should probably map this somewhere

    # Contexts dont have assigned_from / to
    if link_table_key == "context":
        return select(t_main).join(t_link, t_main.c.id == t_link.c.context_id).where(t_link.c.case_id == case_id)

    return (
        select(t_main, t_link.c.assigned_from, t_link.c.assigned_to)
        .join(t_link, t_main.c.id == t_link.c[fk_column])
        .where(t_link.c.case_id == case_id)
    )
