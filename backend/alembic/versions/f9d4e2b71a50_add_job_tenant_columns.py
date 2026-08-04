"""add tenant ownership columns to jobs

Revision ID: f9d4e2b71a50
Revises: e8c3a5f92d41
Create Date: 2026-08-03 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "f9d4e2b71a50"
down_revision = "e8c3a5f92d41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Pre-tenant jobs cannot satisfy required ownership constraints.
    op.execute(sa.text("UPDATE candidates SET job_id = NULL WHERE job_id IS NOT NULL"))
    op.execute(sa.text("UPDATE offers SET job_id = NULL WHERE job_id IS NOT NULL"))
    op.execute(sa.text("DELETE FROM jobs"))

    op.add_column("jobs", sa.Column("company_id", sa.UUID(), nullable=False))
    op.add_column("jobs", sa.Column("branch_id", sa.UUID(), nullable=True))
    op.add_column("jobs", sa.Column("company_member_id", sa.UUID(), nullable=False))
    op.create_index(op.f("ix_jobs_company_id"), "jobs", ["company_id"], unique=False)
    op.create_index(op.f("ix_jobs_branch_id"), "jobs", ["branch_id"], unique=False)
    op.create_index(op.f("ix_jobs_company_member_id"), "jobs", ["company_member_id"], unique=False)
    op.create_foreign_key(
        "fk_jobs_company_id_companies",
        "jobs",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_jobs_branch_id_branches",
        "jobs",
        "branches",
        ["branch_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_jobs_company_member_id_company_members",
        "jobs",
        "company_members",
        ["company_member_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_jobs_company_member_id_company_members", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_branch_id_branches", "jobs", type_="foreignkey")
    op.drop_constraint("fk_jobs_company_id_companies", "jobs", type_="foreignkey")
    op.drop_index(op.f("ix_jobs_company_member_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_branch_id"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_company_id"), table_name="jobs")
    op.drop_column("jobs", "company_member_id")
    op.drop_column("jobs", "branch_id")
    op.drop_column("jobs", "company_id")
