from fastapi_filters.ext.sqlalchemy import create_filters_from_orm, create_sorting_from_orm
from fastapi_filters.filters import alias_generator_config
from fastapi_filters.types import AbstractFilterOperator, SortingValues

from app.db.postgres.orm import Case, Context, Device, DotDependencyFile, FHIRMapping, Patient, Wearable

GLOBAL_SORT_STR = "-id"
GLOBAL_SORT_VALUES: SortingValues = [("id", "desc", None)]


def underscore_alias_generator(name: str, op: AbstractFilterOperator, alias: str | None = None) -> str:
    """Generate query parameter names using double underscore convention."""
    name = alias or name
    op_name = op.name.rstrip("_")
    if op_name == "eq":
        return name
    return f"{name}__{op_name}"


alias_generator_config.set(underscore_alias_generator)

PatientFilters = create_filters_from_orm(Patient, include=["id", "charite_id", "name", "sex", "dob"])
PatientSorting = create_sorting_from_orm(
    Patient, default=GLOBAL_SORT_STR, include=["id", "charite_id", "name", "sex", "dob"]
)


CaseFilters = create_filters_from_orm(Case, include_fk=True, include=["id", "status", "patient_id"])
CaseSorting = create_sorting_from_orm(
    Case, include_fk=True, default=GLOBAL_SORT_STR, include=["id", "status", "patient_id"]
)

DeviceFilters = create_filters_from_orm(
    Device, include=["id", "serial_nr", "model", "manufacturer", "os_version", "status"]
)
DeviceSorting = create_sorting_from_orm(
    Device, default=GLOBAL_SORT_STR, include=["id", "serial_nr", "model", "manufacturer", "os_version", "status"]
)


WearableFilters = create_filters_from_orm(
    Wearable, include=["id", "serial_nr", "model", "manufacturer", "os_version", "status"]
)
WearableSorting = create_sorting_from_orm(
    Wearable, default=GLOBAL_SORT_STR, include=["id", "serial_nr", "model", "manufacturer", "os_version", "status"]
)


ContextFilters = create_filters_from_orm(Context, include=["id", "group_name", "coordinator"])
ContextSorting = create_sorting_from_orm(Context, default=GLOBAL_SORT_STR, include=["id", "group_name", "coordinator"])

FHIRMappingFilters = create_filters_from_orm(FHIRMapping, include=["id", "version"])
FHIRMappingSorting = create_sorting_from_orm(FHIRMapping, default=GLOBAL_SORT_STR, include=["id", "version"])

DotDependencyFileFilters = create_filters_from_orm(
    DotDependencyFile, include=["id", "version", "category", "mapping_id"], include_fk=True
)
DotDependencyFileSorting = create_sorting_from_orm(
    DotDependencyFile, default=GLOBAL_SORT_STR, include=["id", "version", "category", "mapping_id"], include_fk=True
)
