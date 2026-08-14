"""add webhooks table

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-08-13 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "h8i9j0k1l2m3"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("signing_secret_sealed", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhooks_company_id", "webhooks", ["company_id"], unique=False)
    op.create_index("ix_webhooks_company_active", "webhooks", ["company_id", "is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_webhooks_company_active", table_name="webhooks")
    op.drop_index("ix_webhooks_company_id", table_name="webhooks")
    op.drop_table("webhooks")
