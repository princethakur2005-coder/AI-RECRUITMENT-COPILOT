"""add audit_events table

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-08-13 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "l2m3n4o5p6q7"
down_revision = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_company_id", "audit_events", ["company_id"], unique=False)
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"], unique=False)
    op.create_index(
        "ix_audit_events_company_id_created_at",
        "audit_events",
        ["company_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_company_id_resource",
        "audit_events",
        ["company_id", "resource_type", "resource_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_company_id_action",
        "audit_events",
        ["company_id", "action"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_company_id_action", table_name="audit_events")
    op.drop_index("ix_audit_events_company_id_resource", table_name="audit_events")
    op.drop_index("ix_audit_events_company_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_actor_id", table_name="audit_events")
    op.drop_index("ix_audit_events_company_id", table_name="audit_events")
    op.drop_table("audit_events")
