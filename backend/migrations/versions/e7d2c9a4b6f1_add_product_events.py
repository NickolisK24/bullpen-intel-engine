"""add product events table (canonical event log, Phase D2A-1)

Revision ID: e7d2c9a4b6f1
Revises: d1f8a3c64b29
Create Date: 2026-06-25 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e7d2c9a4b6f1'
down_revision = 'd1f8a3c64b29'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'product_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_name', sa.String(length=64), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('anon_id', sa.String(length=64), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('delivery_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    # Deliberately no foreign keys: the event log is an append-only record of
    # facts and must survive deletion of the rows it references (never cascade a
    # delete into history).
    with op.batch_alter_table('product_events', schema=None) as batch_op:
        batch_op.create_index('ix_product_events_occurred_at', ['occurred_at'], unique=False)
        batch_op.create_index('ix_product_events_user', ['user_id'], unique=False)
        batch_op.create_index(
            'ix_product_events_name_occurred', ['event_name', 'occurred_at'], unique=False,
        )


def downgrade():
    with op.batch_alter_table('product_events', schema=None) as batch_op:
        batch_op.drop_index('ix_product_events_name_occurred')
        batch_op.drop_index('ix_product_events_user')
        batch_op.drop_index('ix_product_events_occurred_at')
    op.drop_table('product_events')
