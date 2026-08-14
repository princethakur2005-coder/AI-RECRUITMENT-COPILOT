"""add application_hiring_decisions table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-06 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_hiring_decisions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("decision_confidence", sa.JSON(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("weaknesses", sa.JSON(), nullable=False),
        sa.Column("missing_mandatory_qualifications", sa.JSON(), nullable=False),
        sa.Column("risk_factors", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("recruiter_metadata", sa.JSON(), nullable=False),
        sa.Column("ai_hiring_summary", sa.JSON(), nullable=True),
        sa.Column("decision_detail", sa.JSON(), nullable=False),
        sa.Column("recruiter_override", sa.JSON(), nullable=True),
        sa.Column("policy_version", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", name="uq_application_hiring_decisions_application"),
    )
    op.create_index(
        op.f("ix_application_hiring_decisions_application_id"),
        "application_hiring_decisions",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_application_hiring_decisions_application_id"),
        table_name="application_hiring_decisions",
    )
    op.drop_table("application_hiring_decisions")
