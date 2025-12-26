from sqlalchemy import (
    TIMESTAMP,
    Column,
    Date,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID

metadata = MetaData()

patients = Table(
    "patients",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("charite_id", UUID(as_uuid=True), nullable=False),
    Column("name", String, nullable=False),
    Column("sex", String),
    Column("dob", Date),
    Column("weight", Numeric(6, 2)),
    Column("height", Numeric(4, 2)),
)

devices = Table(
    "devices",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("serial_nr", String, unique=True, nullable=False),
    Column("model", String, nullable=False),
    Column("manufacturer", String),
    Column("os_version", String, nullable=False),
)

wearables = Table(
    "wearables",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("serial_nr", String, unique=True, nullable=False),
    Column("model", String, nullable=False),
    Column("manufacturer", String),
    Column("os_version", String, nullable=False),
)

cases = Table(
    "cases",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("status", String, nullable=False),
    Column("patient_id", UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False),
)

contexts = Table(
    "contexts",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("group_name", String, nullable=False),
    Column("coordinator", String),
)

# Link Tables
case_contexts = Table(
    "case_contexts",
    metadata,
    Column("case_id", UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True),
    Column("context_id", UUID(as_uuid=True), ForeignKey("contexts.id"), primary_key=True),
)

case_devices = Table(
    "case_devices",
    metadata,
    Column("case_id", UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True),
    Column("device_id", UUID(as_uuid=True), ForeignKey("devices.id"), primary_key=True),
    Column("assigned_from", TIMESTAMP, primary_key=True),
    Column("assigned_to", TIMESTAMP),
)

case_wearables = Table(
    "case_wearables",
    metadata,
    Column("case_id", UUID(as_uuid=True), ForeignKey("cases.id"), primary_key=True),
    Column("wearable_id", UUID(as_uuid=True), ForeignKey("wearables.id"), primary_key=True),
    Column("assigned_from", TIMESTAMP, primary_key=True),
    Column("assigned_to", TIMESTAMP),
)
