"""add offers table

Revision ID: f5a83c8d92b2
Revises: 8f8d5e4c05ad
Create Date: 2026-07-12 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f5a83c8d92b2'
down_revision = '8f8d5e4c05ad'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'offers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('created_by_id', sa.UUID(), nullable=True),
        sa.Column('approved_by_id', sa.UUID(), nullable=True),
        sa.Column('offer_title', sa.String(length=255), nullable=True),
        sa.Column('compensation_min', sa.Integer(), nullable=True),
        sa.Column('compensation_max', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(length=10), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_offers_candidate_id'), 'offers', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_offers_job_id'), 'offers', ['job_id'], unique=False)
    op.create_index(op.f('ix_offers_created_by_id'), 'offers', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_offers_approved_by_id'), 'offers', ['approved_by_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_offers_approved_by_id'), table_name='offers')
    op.drop_index(op.f('ix_offers_created_by_id'), table_name='offers')
    op.drop_index(op.f('ix_offers_job_id'), table_name='offers')
    op.drop_index(op.f('ix_offers_candidate_id'), table_name='offers')
    op.drop_table('offers')
