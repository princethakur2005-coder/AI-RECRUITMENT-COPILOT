"""add calendar integration and interview calendar sync tables

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-08-13 14:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "i9j0k1l2m3n4"
down_revision = "h8i9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_integrations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("provider_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("external_calendar_id", sa.String(length=255), nullable=True),
        sa.Column("credentials_sealed", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "provider_type", name="uq_calendar_integrations_company_provider"),
    )
    op.create_index("ix_calendar_integrations_company_id", "calendar_integrations", ["company_id"], unique=False)
    op.create_index(
        "ix_calendar_integrations_company_status",
        "calendar_integrations",
        ["company_id", "status"],
        unique=False,
    )

    op.create_table(
        "interview_calendar_syncs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("calendar_integration_id", sa.Uuid(), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("last_operation", sa.String(length=32), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["calendar_integration_id"], ["calendar_integrations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_id", name="uq_interview_calendar_syncs_interview_id"),
    )
    op.create_index(
        "ix_interview_calendar_syncs_interview_id",
        "interview_calendar_syncs",
        ["interview_id"],
        unique=False,
    )
    op.create_index(
        "ix_interview_calendar_syncs_company_id",
        "interview_calendar_syncs",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_interview_calendar_syncs_calendar_integration_id",
        "interview_calendar_syncs",
        ["calendar_integration_id"],
        unique=False,
    )
    op.create_index(
        "ix_interview_calendar_syncs_sync_status",
        "interview_calendar_syncs",
        ["sync_status"],
        unique=False,
    )
    op.create_index(
        "ix_interview_calendar_syncs_company_status",
        "interview_calendar_syncs",
        ["company_id", "sync_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interview_calendar_syncs_company_status", table_name="interview_calendar_syncs")
    op.drop_index("ix_interview_calendar_syncs_sync_status", table_name="interview_calendar_syncs")
    op.drop_index("ix_interview_calendar_syncs_calendar_integration_id", table_name="interview_calendar_syncs")
    op.drop_index("ix_interview_calendar_syncs_company_id", table_name="interview_calendar_syncs")
    op.drop_index("ix_interview_calendar_syncs_interview_id", table_name="interview_calendar_syncs")
    op.drop_table("interview_calendar_syncs")
    op.drop_index("ix_calendar_integrations_company_status", table_name="calendar_integrations")
    op.drop_index("ix_calendar_integrations_company_id", table_name="calendar_integrations")
    op.drop_table("calendar_integrations")
