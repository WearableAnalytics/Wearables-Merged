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
from sqlalchemy import and_, insert, select

TABLE_MAP = {
    "patients": patients,
    "devices": devices,
    "wearables": wearables,
    "cases": cases,
    "contexts": contexts,
}


def build_insert(table_name: str, data: dict):
    return insert(TABLE_MAP[table_name]).values(**data)


def build_get_one(table_name: str, record_id: str):
    t = TABLE_MAP[table_name]
    return select(t).where(t.c.id == record_id)


def build_list_patients(filters: dict):
    query = select(patients)
    conditions = []
    if filters.get("lastname"):
        conditions.append(patients.c.name.ilike(f"%{filters['lastname']}%"))
    if filters.get("sex"):
        conditions.append(patients.c.sex == filters["sex"])
    # Add other filters (weight, dob ranges) as needed
    if conditions:
        query = query.where(and_(*conditions))
    return query


def build_link_insert(link_type: str, data: dict):
    if link_type == "device":
        return insert(case_devices).values(**data)
    if link_type == "wearable":
        return insert(case_wearables).values(**data)
    if link_type == "context":
        return insert(case_contexts).values(**data)
