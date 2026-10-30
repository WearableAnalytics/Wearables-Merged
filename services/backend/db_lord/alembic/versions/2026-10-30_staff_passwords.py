"""Admin-managed password credentials; revoke sessions from the earlier email/demo login.

No credential or password is inferred for an existing account. Initialize the first admin
through the protected server command. Named staff are then created by an administrator.
"""

import sqlalchemy as sa

from alembic import op

revision = "d4c82a9016b7"
down_revision = "a8e3b9d47f20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "control_passwords",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("control_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("must_change", sa.Boolean(), nullable=False),
        sa.Column("temporary_expires_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.TIMESTAMP(timezone=True)),
        sa.Column("changed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint("failed_attempts >= 0", name=op.f("ck_control_passwords_password_failed_attempts")),
        sa.CheckConstraint(
            "(must_change AND temporary_expires_at IS NOT NULL) OR (NOT must_change AND temporary_expires_at IS NULL)",
            name=op.f("ck_control_passwords_password_temporary_expiry"),
        ),
    )
    # Old sessions and email links must not bypass the newly required password.
    op.execute("UPDATE control_users SET auth_version=auth_version+1, revision=revision+1")
    op.drop_table("login_challenges")


def downgrade() -> None:
    op.drop_table("control_passwords")
    op.create_table(
        "login_challenges",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("control_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True)),
    )
    op.create_index("ix_login_challenges_expires_at", "login_challenges", ["expires_at"])
    # Security invalidation and old email tokens are deliberately not restored.
