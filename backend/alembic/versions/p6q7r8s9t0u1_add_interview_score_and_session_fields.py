"""add interview score and session fields

Revision ID: p6q7r8s9t0u1
Revises: o5p6q7r8s9t0
Create Date: 2026-08-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "p6q7r8s9t0u1"
down_revision = "o5p6q7r8s9t0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add interview_score to applications
    op.add_column("applications", sa.Column("interview_score", sa.Float(), nullable=True))

    # 2. Add columns to interviews
    op.add_column("interviews", sa.Column("candidate_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("interviews", sa.Column("job_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("interviews", sa.Column("interview_score", sa.Float(), nullable=True))
    op.add_column("interviews", sa.Column("questions_json", sa.JSON(), nullable=True))
    op.add_column("interviews", sa.Column("answers_json", sa.JSON(), nullable=True))
    op.add_column("interviews", sa.Column("evaluation_json", sa.JSON(), nullable=True))

    with op.batch_alter_table("interviews") as batch_op:
        batch_op.alter_column("interviewer_member_id", existing_type=sa.Uuid(as_uuid=True), nullable=True)
        batch_op.create_index("ix_interviews_candidate_id", ["candidate_id"])
        batch_op.create_index("ix_interviews_job_id", ["job_id"])

    # 3. Create interview_sessions table
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("application_id", sa.Uuid(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(as_uuid=True), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", sa.Uuid(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.Uuid(as_uuid=True), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interview_id", sa.Uuid(as_uuid=True), sa.ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("questions_json", sa.JSON(), nullable=False),
        sa.Column("answers_json", sa.JSON(), nullable=True),
        sa.Column("evaluation_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_interview_sessions_application_id", "interview_sessions", ["application_id"])
    op.create_index("ix_interview_sessions_candidate_id", "interview_sessions", ["candidate_id"])
    op.create_index("ix_interview_sessions_company_id", "interview_sessions", ["company_id"])
    op.create_index("ix_interview_sessions_job_id", "interview_sessions", ["job_id"])
    op.create_index("ix_interview_sessions_status", "interview_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_interview_sessions_status", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_job_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_company_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_candidate_id", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_application_id", table_name="interview_sessions")
    op.drop_table("interview_sessions")

    with op.batch_alter_table("interviews") as batch_op:
        batch_op.drop_index("ix_interviews_job_id")
        batch_op.drop_index("ix_interviews_candidate_id")
        batch_op.alter_column("interviewer_member_id", existing_type=sa.Uuid(as_uuid=True), nullable=False)
        batch_op.drop_column("evaluation_json")
        batch_op.drop_column("answers_json")
        batch_op.drop_column("questions_json")
        batch_op.drop_column("interview_score")
        batch_op.drop_column("job_id")
        batch_op.drop_column("candidate_id")

    op.drop_column("applications", "interview_score")
