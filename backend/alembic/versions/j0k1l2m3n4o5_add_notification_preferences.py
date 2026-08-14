"""add notification_preferences table

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-08-13 15:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "j0k1l2m3n4o5"
down_revision = "i9j0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recipient_type", sa.String(length=32), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("in_app_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_disabled_categories", sa.JSON(), nullable=False),
        sa.Column("in_app_disabled_categories", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recipient_type",
            "recipient_id",
            "company_id",
            name="uq_notification_preferences_recipient_company",
        ),
    )
    op.create_index(
        "ix_notification_preferences_recipient_id",
        "notification_preferences",
        ["recipient_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_preferences_company_id",
        "notification_preferences",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_notification_preferences_recipient",
        "notification_preferences",
        ["recipient_type", "recipient_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_notification_preferences_recipient", table_name="notification_preferences")
    op.drop_index("ix_notification_preferences_company_id", table_name="notification_preferences")
    op.drop_index("ix_notification_preferences_recipient_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")
