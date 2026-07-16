"""add job intelligence to jobs

Revision ID: b9e7fca2a1d1
Revises: f5a83c8d92b2
Create Date: 2026-07-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b9e7fca2a1d1"
down_revision = "f5a83c8d92b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("job_intelligence", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "job_intelligence")
