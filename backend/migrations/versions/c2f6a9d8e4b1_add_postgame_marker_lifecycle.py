"""add postgame marker lifecycle

Revision ID: c2f6a9d8e4b1
Revises: f6a2c9d8e1b3
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c2f6a9d8e4b1'
down_revision = 'f6a2c9d8e1b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('postgame_processed_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'processing_status',
            sa.String(length=32),
            nullable=False,
            server_default='fully_processed',
        ))
        batch_op.add_column(sa.Column(
            'attempt_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'last_attempted_at',
            sa.DateTime(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'incomplete_reason',
            sa.String(length=120),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'pitching_lines_seen',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'pitcher_resolution_failures',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'correction_attempts_failed',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'failed_at',
            sa.DateTime(),
            nullable=True,
        ))
        batch_op.alter_column(
            'processed_at',
            existing_type=sa.DateTime(),
            nullable=True,
        )
        batch_op.create_index(
            'ix_postgame_processed_games_processing_status',
            ['processing_status'],
            unique=False,
        )

    op.execute(
        "UPDATE postgame_processed_games "
        "SET attempt_count = 1 "
        "WHERE processing_status = 'fully_processed' AND attempt_count = 0"
    )
    op.execute(
        "UPDATE postgame_processed_games "
        "SET last_attempted_at = processed_at "
        "WHERE last_attempted_at IS NULL"
    )


def downgrade():
    op.execute(
        "UPDATE postgame_processed_games "
        "SET processed_at = COALESCE(processed_at, last_attempted_at, created_at) "
        "WHERE processed_at IS NULL"
    )
    with op.batch_alter_table('postgame_processed_games', schema=None) as batch_op:
        batch_op.drop_index('ix_postgame_processed_games_processing_status')
        batch_op.alter_column(
            'processed_at',
            existing_type=sa.DateTime(),
            nullable=False,
        )
        batch_op.drop_column('failed_at')
        batch_op.drop_column('correction_attempts_failed')
        batch_op.drop_column('pitcher_resolution_failures')
        batch_op.drop_column('pitching_lines_seen')
        batch_op.drop_column('incomplete_reason')
        batch_op.drop_column('last_attempted_at')
        batch_op.drop_column('attempt_count')
        batch_op.drop_column('processing_status')
