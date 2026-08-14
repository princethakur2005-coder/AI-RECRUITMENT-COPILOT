"""realign offers to application ownership and revisions

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-10 19:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("offers", sa.Column("application_id", sa.UUID(), nullable=True))
    op.add_column(
        "offers",
        sa.Column("supersedes_offer_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "offers",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "offers",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_index(op.f("ix_offers_application_id"), "offers", ["application_id"], unique=False)
    op.create_index(op.f("ix_offers_supersedes_offer_id"), "offers", ["supersedes_offer_id"], unique=False)
    op.create_index(op.f("ix_offers_is_active"), "offers", ["is_active"], unique=False)
    op.create_index(op.f("ix_offers_status"), "offers", ["status"], unique=False)
    op.create_index(
        "ix_offers_application_id_created_at",
        "offers",
        ["application_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_offers_is_active_status",
        "offers",
        ["is_active", "status"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_offers_application_id_applications",
        "offers",
        "applications",
        ["application_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_offers_supersedes_offer_id_offers",
        "offers",
        "offers",
        ["supersedes_offer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Normalize legacy status vocabulary into the single production contract.
    op.execute(
        """
        UPDATE offers
        SET status = CASE lower(status)
            WHEN 'pending' THEN 'pending_approval'
            ELSE lower(status)
        END
        """
    )

    # Safe ownership backfill: only when candidate_id + job_id uniquely match an application.
    op.execute(
        """
        UPDATE offers AS o
        SET application_id = a.id
        FROM applications AS a
        WHERE o.application_id IS NULL
          AND o.job_id IS NOT NULL
          AND a.candidate_id = o.candidate_id
          AND a.job_id = o.job_id
        """
    )

    # Assign monotonic revisions per application by created_at, oldest first.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY application_id
                    ORDER BY created_at ASC, id ASC
                ) AS revision_number
            FROM offers
            WHERE application_id IS NOT NULL
        )
        UPDATE offers AS o
        SET revision = ranked.revision_number
        FROM ranked
        WHERE o.id = ranked.id
        """
    )

    # Exactly one active revision per application: newest revision remains active.
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY application_id
                    ORDER BY revision DESC, created_at DESC, id DESC
                ) AS activity_rank
            FROM offers
            WHERE application_id IS NOT NULL
        )
        UPDATE offers AS o
        SET is_active = (ranked.activity_rank = 1)
        FROM ranked
        WHERE o.id = ranked.id
        """
    )

    # Chain supersedes_offer_id to the immediately previous revision.
    op.execute(
        """
        UPDATE offers AS newer
        SET supersedes_offer_id = older.id
        FROM offers AS older
        WHERE newer.application_id IS NOT NULL
          AND older.application_id = newer.application_id
          AND older.revision = newer.revision - 1
        """
    )

    op.create_unique_constraint(
        "uq_offers_application_revision",
        "offers",
        ["application_id", "revision"],
    )
    op.create_index(
        "uq_offers_one_active_per_application",
        "offers",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("is_active IS TRUE AND application_id IS NOT NULL"),
    )

    # Keep durable defaults aligned with the ORM model for non-ORM inserts.
    op.alter_column("offers", "revision", server_default=None)
    op.alter_column(
        "offers",
        "is_active",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )
    op.alter_column(
        "offers",
        "status",
        existing_type=sa.String(length=50),
        server_default="draft",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "offers",
        "status",
        existing_type=sa.String(length=50),
        server_default="pending",
        existing_nullable=False,
    )

    op.drop_index(
        "uq_offers_one_active_per_application",
        table_name="offers",
    )
    op.drop_constraint("uq_offers_application_revision", "offers", type_="unique")

    op.execute(
        """
        UPDATE offers
        SET status = CASE lower(status)
            WHEN 'pending_approval' THEN 'pending'
            ELSE status
        END
        """
    )

    op.drop_constraint("fk_offers_supersedes_offer_id_offers", "offers", type_="foreignkey")
    op.drop_constraint("fk_offers_application_id_applications", "offers", type_="foreignkey")

    op.drop_index("ix_offers_is_active_status", table_name="offers")
    op.drop_index("ix_offers_application_id_created_at", table_name="offers")
    op.drop_index(op.f("ix_offers_status"), table_name="offers")
    op.drop_index(op.f("ix_offers_is_active"), table_name="offers")
    op.drop_index(op.f("ix_offers_supersedes_offer_id"), table_name="offers")
    op.drop_index(op.f("ix_offers_application_id"), table_name="offers")

    op.drop_column("offers", "is_active")
    op.drop_column("offers", "revision")
    op.drop_column("offers", "supersedes_offer_id")
    op.drop_column("offers", "application_id")
