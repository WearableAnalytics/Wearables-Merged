from typing import Any, Dict, Optional

from sqlalchemy import and_, delete, insert, select, update

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


def build_insert(table_name: str, data: Dict[str, Any]):
    if table_name not in TABLE_MAP:
        raise ValueError(f"Unknown table: {table_name}")
    t = TABLE_MAP[table_name]
    return insert(t).values(**data).returning(t)


def build_get_one(table_name: str, record_id: str):
    if table_name not in TABLE_MAP:
        raise ValueError(f"Unknown table: {table_name}")
    t = TABLE_MAP[table_name]
    return select(t).where(t.c.id == record_id)


def build_update(table_name: str, record_id: str, data: Dict[str, Any]):
    if table_name not in TABLE_MAP:
        raise ValueError(f"Unknown table: {table_name}")
    t = TABLE_MAP[table_name]
    return update(t).where(t.c.id == record_id).values(**data).returning(t)


def build_delete(table_name: str, record_id: str):
    if table_name not in TABLE_MAP:
        raise ValueError(f"Unknown table: {table_name}")
    t = TABLE_MAP[table_name]
    return delete(t).where(t.c.id == record_id)


def build_list_patients(filters: Dict[str, Any]):
    query = select(patients)
    conditions = []

    # API 'lastname' -> DB 'name' (Fuzzy match)
    if filters.get("lastname"):
        conditions.append(patients.c.name.ilike(f"%{filters['lastname']}%"))

    # API 'firstname' -> DB 'name' (Fuzzy match, usually checks for same field if DB has no split)
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
        query = query.where(and_(*conditions))
    return query


def build_link_insert(link_type: str, data: Dict[str, Any]):
    if link_type not in LINK_TABLE_MAP:
        raise ValueError(f"Unknown link type: {link_type}")
    t = LINK_TABLE_MAP[link_type]
    return insert(t).values(**data).returning(t)


def build_link_update(link_type: str, link_keys: Dict[str, Any], data: Dict[str, Any]):
    if link_type not in LINK_TABLE_MAP:
        raise ValueError(f"Unknown link type: {link_type}")

    t = LINK_TABLE_MAP[link_type]
    # Ensure keys match composite PKs (case_id, device_id, assigned_from)
    conditions = [t.c[key] == value for key, value in link_keys.items()]
    return update(t).where(and_(*conditions)).values(**data).returning(t)


def build_link_delete(link_type: str, link_keys: Dict[str, Any]):
    if link_type not in LINK_TABLE_MAP:
        raise ValueError(f"Unknown link type: {link_type}")

    t = LINK_TABLE_MAP[link_type]
    conditions = [t.c[key] == value for key, value in link_keys.items()]
    return delete(t).where(and_(*conditions))


def build_link_select(link_type: str, filters: Optional[Dict[str, Any]] = None):
    if link_type not in LINK_TABLE_MAP:
        raise ValueError(f"Unknown link type: {link_type}")

    t = LINK_TABLE_MAP[link_type]
    query = select(t)

    if filters:
        conditions = [t.c[key] == value for key, value in filters.items()]
        query = query.where(and_(*conditions))

    return query
