"""add audience subscribers table

Revision ID: 2f7b9c1a5d43
Revises: fa9c1d2e3b47
Create Date: 2026-07-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '2f7b9c1a5d43'
down_revision = 'fa9c1d2e3b47'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audience_subscribers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email_normalized', sa.String(length=320), nullable=False),
        sa.Column('email_original', sa.String(length=320), nullable=True),
        sa.Column('source', sa.String(length=64), nullable=False, server_default='unknown'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='subscribed'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('welcome_sent_at', sa.DateTime(), nullable=True),
        sa.Column('last_welcome_error', sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audience_subscribers', schema=None) as batch_op:
        batch_op.create_index(
            'ix_audience_subscribers_email_normalized',
            ['email_normalized'],
            unique=True,
        )
        batch_op.create_index('ix_audience_subscribers_status', ['status'], unique=False)


def downgrade():
    with op.batch_alter_table('audience_subscribers', schema=None) as batch_op:
        batch_op.drop_index('ix_audience_subscribers_status')
        batch_op.drop_index('ix_audience_subscribers_email_normalized')
    op.drop_table('audience_subscribers')
