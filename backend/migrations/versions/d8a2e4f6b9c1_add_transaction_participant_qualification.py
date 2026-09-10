"""add transaction participant qualification

Revision ID: d8a2e4f6b9c1
Revises: c7f1b408d93a
Create Date: 2026-08-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd8a2e4f6b9c1'
down_revision = 'c7f1b408d93a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('player_transactions', sa.Column(
        'participant_role', sa.String(length=20), nullable=False,
        server_default='unresolved',
    ))
    op.add_column('player_transactions', sa.Column(
        'participant_role_authority', sa.String(length=60), nullable=False,
        server_default='unresolved',
    ))
    op.add_column('player_transactions', sa.Column('participant_position_code', sa.String(length=10)))
    op.add_column('player_transactions', sa.Column('participant_position_abbreviation', sa.String(length=10)))
    op.add_column('player_transactions', sa.Column('participant_position_type', sa.String(length=40)))
    op.create_check_constraint(
        'ck_player_transactions_participant_role',
        'player_transactions',
        "participant_role IN ('pitcher', 'non_pitcher', 'unresolved')",
    )


def downgrade():
    op.drop_constraint(
        'ck_player_transactions_participant_role',
        'player_transactions',
        type_='check',
    )
    op.drop_column('player_transactions', 'participant_position_type')
    op.drop_column('player_transactions', 'participant_position_abbreviation')
    op.drop_column('player_transactions', 'participant_position_code')
    op.drop_column('player_transactions', 'participant_role_authority')
    op.drop_column('player_transactions', 'participant_role')
