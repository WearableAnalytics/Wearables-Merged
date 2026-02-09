"""remove_export_jobs

Revision ID: 3b9e6f7c9a11
Revises: afb10388d1d0
Create Date: 2026-02-09 14:05:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9e6f7c9a11"
down_revision: str | Sequence[str] | None = "afb10388d1d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TABLE IF EXISTS export_jobs CASCADE")
    op.execute("DROP TYPE IF EXISTS export_job_status_enum")


def downgrade() -> None:
    """Downgrade schema."""
    export_job_status_enum = sa.Enum("PENDING", "RUNNING", "COMPLETE", "FAILED", name="export_job_status_enum")
    export_job_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "export_jobs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("status", export_job_status_enum, nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=2048), nullable=True),
        sa.Column("result_path", sa.String(length=2048), nullable=True),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_export_jobs")),
    )
    op.create_index(op.f("ix_export_jobs_status"), "export_jobs", ["status"], unique=False)
