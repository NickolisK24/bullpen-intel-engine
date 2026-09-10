"""add persisted game observation states

Revision ID: c6d8e1f3a5b7
Revises: b4e7c9d2a1f6
Create Date: 2026-08-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c6d8e1f3a5b7'
down_revision = 'b4e7c9d2a1f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'game_observation_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('observation_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('observation', sa.JSON(), nullable=False),
        sa.Column('source_authority', sa.String(length=100), nullable=False),
        sa.Column('source_endpoint', sa.String(length=120), nullable=False),
        sa.Column('source_observed_at', sa.DateTime(), nullable=True),
        sa.Column('finality_state', sa.String(length=40), nullable=False),
        sa.Column('previous_observation_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('last_classification', sa.String(length=40), nullable=False),
        sa.Column('last_change_summary', sa.JSON(), nullable=True),
        sa.Column('accepted_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mlb_game_pk', name='uq_game_observation_states_game_pk'),
    )
    op.create_index(
        'ix_game_observation_states_finality',
        'game_observation_states', ['finality_state'], unique=False,
    )
    op.create_index(
        'ix_game_observation_states_source_observed',
        'game_observation_states', ['source_observed_at'], unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_game_observation_states_source_observed',
        table_name='game_observation_states',
    )
    op.drop_index(
        'ix_game_observation_states_finality',
        table_name='game_observation_states',
    )
    op.drop_table('game_observation_states')
