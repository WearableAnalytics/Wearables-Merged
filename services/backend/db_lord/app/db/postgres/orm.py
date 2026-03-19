from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import TIMESTAMP, CheckConstraint, Date, ForeignKey, Index, MetaData, Numeric, String, Uuid, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.model_constants import (
    CONTEXT_COORDINATOR_MAX_LEN,
    CONTEXT_GROUP_NAME_MAX_LEN,
    FHIR_CATEGORY_MAX_LEN,
    FHIR_VERSION_MAX_LEN,
    HARDWARE_MANUFACTURER_MAX_LEN,
    HARDWARE_MODEL_MAX_LEN,
    HARDWARE_OS_VERSION_MAX_LEN,
    HARDWARE_SERIAL_MAX_LEN,
    PATIENT_HEIGHT_PRECISION,
    PATIENT_HEIGHT_SCALE,
    PATIENT_NAME_MAX_LEN,
    PATIENT_SEX_MAX_LEN,
    PATIENT_WEIGHT_PRECISION,
    PATIENT_WEIGHT_SCALE,
)
from app.schemas.case import CaseStatus
from app.schemas.common import HardwareStatus

# Naming convention for constraints - required for Alembic autogenerate to work properly with constraints
_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# monotonic can be used for uuids in sqlalchemy 2.1 to improve performance slightly (but 2.1 is currently only in beta)
# Use actual postgres enums: these can cause issues with Alembic autogenerate if not handled carefully!!
case_status_db = SAEnum(CaseStatus, name="case_status_enum", native_enum=True, validate_strings=True)
hardware_status_db = SAEnum(HardwareStatus, name="hardware_status_enum", native_enum=True, validate_strings=True)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    metadata = MetaData(naming_convention=_naming_convention)
    type_annotation_map = {
        UUID: Uuid(as_uuid=True, native_uuid=True),
        datetime: TIMESTAMP(timezone=True),
    }


# Association tables (m2m)
class CaseContext(Base):
    """Association table for Case <-> Context"""

    __tablename__ = "case_contexts"

    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    context_id: Mapped[UUID] = mapped_column(
        ForeignKey("contexts.id", ondelete="CASCADE"), primary_key=True, index=True
    )

    __table_args__ = (
        # context -> cases GraphQL connection
        Index("ix_case_contexts_context_case_desc", "context_id", text("case_id DESC")),
    )


class CaseDevice(Base):
    """Association table for Case <-> Device with temporal assignment data."""

    __tablename__ = "case_devices"

    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    device_id: Mapped[UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True, index=True)
    assigned_from: Mapped[datetime] = mapped_column(primary_key=True)

    assigned_to: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships for accessing the linked entities, lazy="raise" should make accidental N+1 impossible
    case: Mapped[Case] = relationship(back_populates="device_assignments", lazy="raise")
    device: Mapped[Device] = relationship(back_populates="case_assignments", lazy="raise")

    __table_args__ = (
        # case -> device assignment connection sorted by most recent assignment
        Index(
            "ix_case_devices_case_assigned_from_desc",
            "case_id",
            text("assigned_from DESC"),
            text("device_id DESC"),
            postgresql_include=["assigned_to"],
        ),
        # device detail/history lookups sorted by most recent assignment
        Index(
            "ix_case_devices_device_assigned_from_desc",
            "device_id",
            text("assigned_from DESC"),
            text("case_id DESC"),
            postgresql_include=["assigned_to"],
        ),
        # enforces valid assignment windows: an end timestamp, if present, must be after start
        CheckConstraint(
            "assigned_to IS NULL OR assigned_to > assigned_from",
            name="ck_case_devices_assigned_order",
        ),
        # prevents overlapping assignment intervals for the same device across cases
        ExcludeConstraint(
            ("device_id", "="),
            (
                text("tstzrange(assigned_from, COALESCE(assigned_to, 'infinity'::timestamptz), '[)')"),
                "&&",
            ),
            name="ex_case_device_no_overlap",
            using="gist",
        ),
        # currently assigned device checks without scanning historical rows
        Index(
            "ix_case_devices_active_by_device",
            "device_id",
            postgresql_where=text("assigned_to IS NULL"),
        ),
    )


class CaseWearable(Base):
    """Association table for Case <-> Wearable with temporal assignment data."""

    __tablename__ = "case_wearables"

    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True)
    wearable_id: Mapped[UUID] = mapped_column(
        ForeignKey("wearables.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    assigned_from: Mapped[datetime] = mapped_column(primary_key=True)

    assigned_to: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships for accessing the linked entities
    case: Mapped[Case] = relationship(back_populates="wearable_assignments", lazy="raise")
    wearable: Mapped[Wearable] = relationship(back_populates="case_assignments", lazy="raise")

    __table_args__ = (
        # case -> wearable assignment connection sorted by most recent assignment
        Index(
            "ix_case_wearables_case_assigned_from_desc",
            "case_id",
            text("assigned_from DESC"),
            text("wearable_id DESC"),
            postgresql_include=["assigned_to"],
        ),
        # wearable detail/history lookups sorted by most recent assignment
        Index(
            "ix_case_wearables_wearable_assigned_from_desc",
            "wearable_id",
            text("assigned_from DESC"),
            text("case_id DESC"),
            postgresql_include=["assigned_to"],
        ),
        # enforces valid assignment windows: an end timestamp, if present, must be after start
        CheckConstraint(
            "assigned_to IS NULL OR assigned_to > assigned_from",
            name="ck_case_wearables_assigned_order",
        ),
        # prevents overlapping assignment intervals for the same wearable across cases
        ExcludeConstraint(
            ("wearable_id", "="),
            (
                text("tstzrange(assigned_from, COALESCE(assigned_to, 'infinity'::timestamptz), '[)')"),
                "&&",
            ),
            name="ex_case_wearable_no_overlap",
            using="gist",
        ),
        # currently assigned wearable checks without scanning historical rows
        Index(
            "ix_case_wearables_active_by_wearable",
            "wearable_id",
            postgresql_where=text("assigned_to IS NULL"),
        ),
    )


# Main entity models
class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    charite_id: Mapped[UUID] = mapped_column(unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(PATIENT_NAME_MAX_LEN), nullable=False)
    sex: Mapped[str | None] = mapped_column(String(PATIENT_SEX_MAX_LEN), nullable=True, index=True)
    dob: Mapped[date | None] = mapped_column(Date, index=True)
    weight: Mapped[Decimal | None] = mapped_column(
        Numeric(PATIENT_WEIGHT_PRECISION, PATIENT_WEIGHT_SCALE), nullable=True
    )
    height: Mapped[Decimal | None] = mapped_column(
        Numeric(PATIENT_HEIGHT_PRECISION, PATIENT_HEIGHT_SCALE), nullable=True
    )

    # Relationships
    cases: Mapped[list[Case]] = relationship(
        back_populates="patient", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        # weight must be positive when provided
        CheckConstraint("weight is null OR weight > 0", name="ck_patients_weight_positive"),
        # height must be positive when provided
        CheckConstraint("height is null OR height > 0", name="ck_patients_height_positive"),
        # patient name search/autocomplete
        Index("ix_patients_name_trgm", "name", postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"}),
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    status: Mapped[CaseStatus] = mapped_column(case_status_db, default=CaseStatus.PLANNED, index=True)
    patient_id: Mapped[UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    patient: Mapped[Patient] = relationship(back_populates="cases", lazy="raise")

    # m2m
    device_assignments: Mapped[list[CaseDevice]] = relationship(
        back_populates="case", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )
    wearable_assignments: Mapped[list[CaseWearable]] = relationship(
        back_populates="case", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )

    # Simple m2m for contexts
    contexts: Mapped[list[Context]] = relationship(
        secondary="case_contexts", back_populates="cases", lazy="raise", passive_deletes=True
    )
    __table_args__ = (
        # patient -> cases filtering by status
        Index("ix_cases_patient_status", "patient_id", "status"),
        # patient -> cases connection ordered by newest case id (proxy for creation time since UUIDv7 is time ordered)
        Index("ix_cases_patient_id_id_desc", "patient_id", text("id DESC")),
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    serial_nr: Mapped[str] = mapped_column(String(HARDWARE_SERIAL_MAX_LEN), unique=True, nullable=False)
    model: Mapped[str] = mapped_column(String(HARDWARE_MODEL_MAX_LEN), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(HARDWARE_MANUFACTURER_MAX_LEN), nullable=True)
    os_version: Mapped[str] = mapped_column(String(HARDWARE_OS_VERSION_MAX_LEN), nullable=False)
    # indexed for inventory filtering by current availability/status
    status: Mapped[HardwareStatus] = mapped_column(
        hardware_status_db, default=HardwareStatus.AVAILABLE, index=True, nullable=False
    )

    # Relationships
    case_assignments: Mapped[list[CaseDevice]] = relationship(
        back_populates="device", lazy="raise", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_devices_model_trgm", "model", postgresql_using="gin", postgresql_ops={"model": "gin_trgm_ops"}),
    )


class Wearable(Base):
    __tablename__ = "wearables"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    serial_nr: Mapped[str] = mapped_column(String(HARDWARE_SERIAL_MAX_LEN), unique=True, nullable=False)
    model: Mapped[str] = mapped_column(String(HARDWARE_MODEL_MAX_LEN), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(HARDWARE_MANUFACTURER_MAX_LEN), nullable=True)
    os_version: Mapped[str] = mapped_column(String(HARDWARE_OS_VERSION_MAX_LEN), nullable=False)
    # Indexed for inventory filtering by current availability/status.
    status: Mapped[HardwareStatus] = mapped_column(
        hardware_status_db, default=HardwareStatus.AVAILABLE, index=True, nullable=False
    )

    # Relationships
    case_assignments: Mapped[list[CaseWearable]] = relationship(
        back_populates="wearable", lazy="raise", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_wearables_model_trgm", "model", postgresql_using="gin", postgresql_ops={"model": "gin_trgm_ops"}),
    )


class Context(Base):
    __tablename__ = "contexts"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    group_name: Mapped[str] = mapped_column(String(CONTEXT_GROUP_NAME_MAX_LEN), nullable=False)
    coordinator: Mapped[str | None] = mapped_column(String(CONTEXT_COORDINATOR_MAX_LEN), nullable=True)

    # Relationships
    cases: Mapped[list[Case]] = relationship(
        secondary="case_contexts", back_populates="contexts", lazy="raise", passive_deletes=True
    )


class FHIRMapping(Base):
    __tablename__ = "fhir_mappings"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    # indexed+unique for direct lookup of mapping payload by version
    version: Mapped[str] = mapped_column(String(FHIR_VERSION_MAX_LEN), unique=True, index=True, nullable=False)
    full_mapping: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    # Relationships
    dot_dependency_files: Mapped[list[DotDependencyFile]] = relationship(
        back_populates="mapping", lazy="raise", cascade="all, delete-orphan", passive_deletes=True
    )


class DotDependencyFile(Base):
    __tablename__ = "dot_dependency_files"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))

    version: Mapped[str] = mapped_column(String(FHIR_VERSION_MAX_LEN), index=True, nullable=False)
    # Indexed for category-scoped dependency file queries.
    category: Mapped[str] = mapped_column(String(FHIR_CATEGORY_MAX_LEN), index=True, nullable=False)
    digraph: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    mapping_id: Mapped[UUID] = mapped_column(ForeignKey("fhir_mappings.id", ondelete="CASCADE"), nullable=False)

    # Relationships
    mapping: Mapped[FHIRMapping] = relationship(back_populates="dot_dependency_files", lazy="raise")

    __table_args__ = (
        # fetching dependency graphs by mapping version and category at the same time
        Index("ix_dot_dependency_files_version_category", "version", "category"),
    )
