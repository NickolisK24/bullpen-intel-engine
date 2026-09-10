"""extend editorial post history

Revision ID: a1d8e4c6b2f0
Revises: f7c5d3b9a2e1
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = 'a1d8e4c6b2f0'
down_revision = 'f7c5d3b9a2e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('editorial_post_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('team_ids_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('game_pks_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('candidate_id', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('evidence_reference', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('evidence_snapshot_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('generated_draft_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('final_post_text', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('external_post_url', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('score_version', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('source_briefing_date', sa.Date(), nullable=True))
        batch_op.create_index('ix_editorial_post_history_candidate_id', ['candidate_id'], unique=False)


def downgrade():
    with op.batch_alter_table('editorial_post_history', schema=None) as batch_op:
        batch_op.drop_index('ix_editorial_post_history_candidate_id')
        for column in (
            'source_briefing_date', 'score_version', 'external_post_url',
            'final_post_text', 'generated_draft_text', 'evidence_snapshot_json',
            'evidence_reference', 'candidate_id', 'game_pks_json', 'team_ids_json',
            'platform',
        ):
            batch_op.drop_column(column)
