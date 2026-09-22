"""add composite score and hiring decision

Revision ID: q7r8s9t0u1v2
Revises: p6q7r8s9t0u1
Create Date: 2026-08-23 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "q7r8s9t0u1v2"
down_revision = "p6q7r8s9t0u1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("composite_score", sa.Float(), nullable=True))
    op.add_column("applications", sa.Column("hiring_decision_json", sa.JSON(), nullable=True))
    with op.batch_alter_table("applications") as batch_op:
        batch_op.create_index("ix_applications_composite_score", ["composite_score"])


def downgrade() -> None:
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_index("ix_applications_composite_score")
    op.drop_column("applications", "hiring_decision_json")
    op.drop_column("applications", "composite_score")
