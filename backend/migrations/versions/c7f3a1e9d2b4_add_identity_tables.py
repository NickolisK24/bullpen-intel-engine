"""add identity tables (users, user_followed_teams)

Revision ID: c7f3a1e9d2b4
Revises: a6d4e9c2f1b8
Create Date: 2026-06-23 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c7f3a1e9d2b4'
down_revision = 'a6d4e9c2f1b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('email_verified_at', sa.DateTime(), nullable=True),
        sa.Column('onboarded_at', sa.DateTime(), nullable=True),
        sa.Column('notification_prefs', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('ix_users_email', ['email'], unique=True)

    op.create_table(
        'user_followed_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'team_id', name='uq_user_followed_teams_user_team'),
    )
    with op.batch_alter_table('user_followed_teams', schema=None) as batch_op:
        batch_op.create_index('ix_user_followed_teams_user', ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('user_followed_teams', schema=None) as batch_op:
        batch_op.drop_index('ix_user_followed_teams_user')
    op.drop_table('user_followed_teams')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_email')
    op.drop_table('users')
