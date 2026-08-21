"""add candidate notification preference uniqueness

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-08-14 18:00:00.000000

PostgreSQL treats NULL as distinct in multi-column UNIQUE constraints, so
candidate rows (company_id IS NULL) need a partial unique index.
"""

from alembic import op
import sqlalchemy as sa


revision = "m3n4o5p6q7r8"
down_revision = "l2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the newest row when historical duplicates exist.
    op.execute(
        """
        DELETE FROM notification_preferences AS newer
        USING notification_preferences AS older
        WHERE newer.company_id IS NULL
          AND older.company_id IS NULL
          AND newer.recipient_type = older.recipient_type
          AND newer.recipient_id = older.recipient_id
          AND newer.created_at > older.created_at
        """
    )
    op.create_index(
        "uq_notification_preferences_candidate_recipient",
        "notification_preferences",
        ["recipient_type", "recipient_id"],
        unique=True,
        postgresql_where=sa.text("company_id IS NULL"),
        sqlite_where=sa.text("company_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_notification_preferences_candidate_recipient",
        table_name="notification_preferences",
    )
