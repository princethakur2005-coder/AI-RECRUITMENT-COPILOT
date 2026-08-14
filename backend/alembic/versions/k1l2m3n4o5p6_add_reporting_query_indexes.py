"""add reporting query indexes

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-08-13 15:30:00.000000
"""

from alembic import op


revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_applications_company_id_applied_at",
        "applications",
        ["company_id", "applied_at"],
        unique=False,
    )
    op.create_index(
        "ix_interviews_company_id_scheduled_start",
        "interviews",
        ["company_id", "scheduled_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_interviews_company_id_scheduled_start", table_name="interviews")
    op.drop_index("ix_applications_company_id_applied_at", table_name="applications")
