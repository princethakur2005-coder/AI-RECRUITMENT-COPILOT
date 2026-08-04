"""add company_members table

Revision ID: e8c3a5f92d41
Revises: d7b2f1a84c30
Create Date: 2026-08-03 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e8c3a5f92d41"
down_revision = "d7b2f1a84c30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "user_id", name="uq_company_members_company_user"),
        sa.UniqueConstraint("user_id", name="uq_company_members_user"),
    )
    op.create_index(op.f("ix_company_members_branch_id"), "company_members", ["branch_id"], unique=False)
    op.create_index(op.f("ix_company_members_company_id"), "company_members", ["company_id"], unique=False)
    op.create_index(op.f("ix_company_members_role"), "company_members", ["role"], unique=False)
    op.create_index(op.f("ix_company_members_user_id"), "company_members", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_company_members_user_id"), table_name="company_members")
    op.drop_index(op.f("ix_company_members_role"), table_name="company_members")
    op.drop_index(op.f("ix_company_members_company_id"), table_name="company_members")
    op.drop_index(op.f("ix_company_members_branch_id"), table_name="company_members")
    op.drop_table("company_members")
