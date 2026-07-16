"""add notes table

Revision ID: 8f8d5e4c05ad
Revises: 80366bee5bea
Create Date: 2026-07-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8f8d5e4c05ad'
down_revision = '80366bee5bea'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'notes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('candidate_id', sa.UUID(), nullable=False),
        sa.Column('author_id', sa.UUID(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False, server_default='human'),
        sa.Column('pinned', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('mentions', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['candidate_id'], ['candidates.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notes_candidate_id'), 'notes', ['candidate_id'], unique=False)
    op.create_index(op.f('ix_notes_author_id'), 'notes', ['author_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_notes_author_id'), table_name='notes')
    op.drop_index(op.f('ix_notes_candidate_id'), table_name='notes')
    op.drop_table('notes')
