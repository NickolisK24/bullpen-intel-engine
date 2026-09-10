"""add adaptive game-state polling and provenance fields

Revision ID: e8b4f1a2c6d9
Revises: d7a3e9c1f5b2
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = 'e8b4f1a2c6d9'
down_revision = 'd7a3e9c1f5b2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('scheduled_games') as batch_op:
        batch_op.add_column(sa.Column('operational_state', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('status_detailed_state', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('status_abstract_state', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('game_state_fingerprint', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('next_poll_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('polling_policy_version', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('last_transition', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('last_transition_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('last_transition_observation_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_scheduled_games_last_transition_observation',
            'source_observations',
            ['last_transition_observation_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_scheduled_games_operational_state', ['operational_state'])
        batch_op.create_index('ix_scheduled_games_next_poll_at', ['next_poll_at'])


def downgrade():
    with op.batch_alter_table('scheduled_games') as batch_op:
        batch_op.drop_index('ix_scheduled_games_next_poll_at')
        batch_op.drop_index('ix_scheduled_games_operational_state')
        batch_op.drop_constraint(
            'fk_scheduled_games_last_transition_observation', type_='foreignkey'
        )
        batch_op.drop_column('last_transition_observation_id')
        batch_op.drop_column('last_transition_at')
        batch_op.drop_column('last_transition')
        batch_op.drop_column('polling_policy_version')
        batch_op.drop_column('next_poll_at')
        batch_op.drop_column('game_state_fingerprint')
        batch_op.drop_column('status_abstract_state')
        batch_op.drop_column('status_detailed_state')
        batch_op.drop_column('operational_state')
