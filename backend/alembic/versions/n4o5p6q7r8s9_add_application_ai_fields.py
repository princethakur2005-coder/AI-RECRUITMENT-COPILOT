"""add application ai fields

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-08-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "n4o5p6q7r8s9"
down_revision = "m3n4o5p6q7r8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("fit_score", sa.Float(), nullable=True))
    op.add_column("applications", sa.Column("evaluation_summary", sa.Text(), nullable=True))
    op.add_column(
        "applications",
        sa.Column("ai_status", sa.String(length=50), nullable=False, server_default="pending"),
    )


def downgrade() -> None:
    op.drop_column("applications", "ai_status")
    op.drop_column("applications", "evaluation_summary")
    op.drop_column("applications", "fit_score")
