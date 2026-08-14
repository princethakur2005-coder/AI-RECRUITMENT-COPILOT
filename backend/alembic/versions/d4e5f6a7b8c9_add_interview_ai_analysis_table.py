"""add interview_ai_analysis table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_ai_analysis",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("interview_id", sa.UUID(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("technical_score", sa.Integer(), nullable=False),
        sa.Column("communication_score", sa.Integer(), nullable=False),
        sa.Column("problem_solving_score", sa.Integer(), nullable=False),
        sa.Column("behavioral_score", sa.Integer(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("gaps_identified", sa.JSON(), nullable=False),
        sa.Column("demonstrated_competencies", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("ai_provider", sa.String(length=50), nullable=False),
        sa.Column("ai_model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["interview_id"], ["interviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_id", name="uq_interview_ai_analysis_interview"),
    )
    op.create_index(
        op.f("ix_interview_ai_analysis_interview_id"),
        "interview_ai_analysis",
        ["interview_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_interview_ai_analysis_interview_id"), table_name="interview_ai_analysis")
    op.drop_table("interview_ai_analysis")
