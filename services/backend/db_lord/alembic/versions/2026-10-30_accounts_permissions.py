"""Staff accounts, case assignments and one-use email login proof.

No access is inferred. Existing cases and measurements are unchanged.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "a8e3b9d47f20"
down_revision = "7c2e9d4b1a6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("control_authority_lock", sa.Column("id", sa.Integer(), primary_key=True))
    op.execute("INSERT INTO control_authority_lock (id) VALUES (1)")
    op.create_table(
        "control_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("roles", JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("request_state", JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("denied_at", sa.TIMESTAMP(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending','approved','denied')", name=op.f("ck_control_users_control_user_status")
        ),
        sa.CheckConstraint("auth_version > 0 AND revision > 0", name=op.f("ck_control_users_control_user_versions")),
    )
    op.create_index("ix_control_users_status", "control_users", ["status"])
    op.create_index("ix_control_users_email", "control_users", ["email"], unique=True)
    op.create_table(
        "control_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid()),
        sa.Column("operation", sa.String(48), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer()),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("reason", sa.String(256)),
        sa.CheckConstraint(
            "reason IS NULL OR length(reason) BETWEEN 1 AND 256",
            name=op.f("ck_control_audit_control_audit_reason_length"),
        ),
    )

    op.create_table(
        "case_access",
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("control_users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("patient_id", sa.Uuid(), sa.ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("scopes", JSONB(), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("revision > 0", name=op.f("ck_case_access_case_access_revision")),
        sa.CheckConstraint(
            "purpose IN ('clinical-reference','synthetic-research')", name=op.f("ck_case_access_case_access_purpose")
        ),
    )
    op.create_index("ix_case_access_user_page", "case_access", ["user_id", "case_id"])
    op.create_table(
        "login_challenges",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("control_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("ix_login_challenges_expires_at", "login_challenges", ["expires_at"])


def downgrade() -> None:
    for table in ("login_challenges", "case_access", "control_audit", "control_users", "control_authority_lock"):
        op.drop_table(table)
