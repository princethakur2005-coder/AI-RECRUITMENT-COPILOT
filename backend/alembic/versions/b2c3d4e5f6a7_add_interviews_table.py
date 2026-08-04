"""add interviews table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("interviewer_member_id", sa.UUID(), nullable=False),
        sa.Column("interview_type", sa.String(length=50), nullable=False, server_default="phone"),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("meeting_link", sa.String(length=500), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="scheduled"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interviewer_member_id"], ["company_members.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_interviews_application_id"), "interviews", ["application_id"], unique=False)
    op.create_index(op.f("ix_interviews_company_id"), "interviews", ["company_id"], unique=False)
    op.create_index(op.f("ix_interviews_interviewer_member_id"), "interviews", ["interviewer_member_id"], unique=False)
    op.create_index(op.f("ix_interviews_interview_type"), "interviews", ["interview_type"], unique=False)
    op.create_index(op.f("ix_interviews_scheduled_start"), "interviews", ["scheduled_start"], unique=False)
    op.create_index(op.f("ix_interviews_status"), "interviews", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_interviews_status"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_scheduled_start"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_interview_type"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_interviewer_member_id"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_company_id"), table_name="interviews")
    op.drop_index(op.f("ix_interviews_application_id"), table_name="interviews")
    op.drop_table("interviews")
