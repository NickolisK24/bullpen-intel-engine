"""add digest metrics tables (digest_runs, digest_deliveries)

Revision ID: d1f8a3c64b29
Revises: c7f3a1e9d2b4
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd1f8a3c64b29'
down_revision = 'c7f3a1e9d2b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'digest_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('dry_run', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('reference_date', sa.String(length=10), nullable=True),
        sa.Column('considered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('suppressed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('errors', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('breakdown', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'digest_deliveries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('digest_type', sa.String(length=64), nullable=False, server_default='team_digest_v1'),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('reason', sa.String(length=64), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('open_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('clicked_at', sa.DateTime(), nullable=True),
        sa.Column('click_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('returned_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['digest_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('digest_deliveries', schema=None) as batch_op:
        batch_op.create_index('ix_digest_deliveries_user', ['user_id'], unique=False)
        batch_op.create_index('ix_digest_deliveries_status', ['status'], unique=False)
        batch_op.create_index('ix_digest_deliveries_run', ['run_id'], unique=False)


def downgrade():
    with op.batch_alter_table('digest_deliveries', schema=None) as batch_op:
        batch_op.drop_index('ix_digest_deliveries_run')
        batch_op.drop_index('ix_digest_deliveries_status')
        batch_op.drop_index('ix_digest_deliveries_user')
    op.drop_table('digest_deliveries')
    op.drop_table('digest_runs')
