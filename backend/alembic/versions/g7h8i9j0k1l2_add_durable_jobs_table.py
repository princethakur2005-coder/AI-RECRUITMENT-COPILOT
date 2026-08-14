"""add durable_jobs table

Revision ID: g7h8i9j0k1l2
Revises: b8c9d0e1f2a3
Create Date: 2026-08-13 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "g7h8i9j0k1l2"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "durable_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_durable_jobs_idempotency_key"),
    )
    op.create_index("ix_durable_jobs_job_type", "durable_jobs", ["job_type"], unique=False)
    op.create_index("ix_durable_jobs_status", "durable_jobs", ["status"], unique=False)
    op.create_index("ix_durable_jobs_company_id", "durable_jobs", ["company_id"], unique=False)
    op.create_index(
        "ix_durable_jobs_status_next_run",
        "durable_jobs",
        ["status", "next_run_at"],
        unique=False,
    )
    op.create_index(
        "ix_durable_jobs_type_status",
        "durable_jobs",
        ["job_type", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_durable_jobs_type_status", table_name="durable_jobs")
    op.drop_index("ix_durable_jobs_status_next_run", table_name="durable_jobs")
    op.drop_index("ix_durable_jobs_company_id", table_name="durable_jobs")
    op.drop_index("ix_durable_jobs_status", table_name="durable_jobs")
    op.drop_index("ix_durable_jobs_job_type", table_name="durable_jobs")
    op.drop_table("durable_jobs")
