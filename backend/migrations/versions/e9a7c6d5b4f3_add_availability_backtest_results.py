"""add availability backtest results

Revision ID: e9a7c6d5b4f3
Revises: b42f7c9a1d6e
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e9a7c6d5b4f3'
down_revision = 'b42f7c9a1d6e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'availability_backtest_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('method_version', sa.String(length=80), nullable=False),
        sa.Column('cadence', sa.String(length=80), nullable=False),
        sa.Column('computed_at', sa.DateTime(), nullable=False),
        sa.Column('data_through', sa.Date(), nullable=True),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('window_label', sa.String(length=50), nullable=False),
        sa.Column('window_start', sa.Date(), nullable=True),
        sa.Column('window_end', sa.Date(), nullable=True),
        sa.Column('tier', sa.String(length=20), nullable=False),
        sa.Column('tier_order', sa.Integer(), nullable=False),
        sa.Column('sample_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_day_appearances', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_day_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('no_appearance_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no_appearance_tier_flips', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no_appearance_tier_flip_rate', sa.Float(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('availability_backtest_results', schema=None) as batch_op:
        batch_op.create_index(
            'ix_availability_backtest_method_computed',
            ['method_version', 'computed_at'],
            unique=False,
        )
        batch_op.create_index(
            'ix_availability_backtest_season_tier',
            ['season', 'tier'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('availability_backtest_results', schema=None) as batch_op:
        batch_op.drop_index('ix_availability_backtest_season_tier')
        batch_op.drop_index('ix_availability_backtest_method_computed')
    op.drop_table('availability_backtest_results')
