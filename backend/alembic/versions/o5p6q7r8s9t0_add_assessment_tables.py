"""add assessment tables

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-08-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "o5p6q7r8s9t0"
down_revision = "n4o5p6q7r8s9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("assessment_score", sa.Float(), nullable=True))
    op.create_table(
        "assessment_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("questions_json", sa.JSON(), nullable=False),
        sa.Column("answers_json", sa.JSON(), nullable=True),
        sa.Column("breakdown_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_assessment_sessions_application_id", "assessment_sessions", ["application_id"])
    op.create_index("ix_assessment_sessions_candidate_id", "assessment_sessions", ["candidate_id"])
    op.create_index("ix_assessment_sessions_company_id", "assessment_sessions", ["company_id"])
    op.create_index("ix_assessment_sessions_job_id", "assessment_sessions", ["job_id"])
    op.create_index("ix_assessment_sessions_status", "assessment_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_assessment_sessions_status", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_job_id", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_company_id", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_candidate_id", table_name="assessment_sessions")
    op.drop_index("ix_assessment_sessions_application_id", table_name="assessment_sessions")
    op.drop_table("assessment_sessions")
    op.drop_column("applications", "assessment_score")
