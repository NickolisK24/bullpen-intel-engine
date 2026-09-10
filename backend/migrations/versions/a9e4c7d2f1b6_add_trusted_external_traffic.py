"""add trusted external traffic measurement

Revision ID: a9e4c7d2f1b6
Revises: 7c4d2e9f1a6b
Create Date: 2026-07-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a9e4c7d2f1b6'
down_revision = '7c4d2e9f1a6b'
branch_labels = None
depends_on = None


def _table_names():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table_name):
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade():
    tables = _table_names()
    if 'product_events' in tables:
        op.drop_table('product_events')
    if 'digest_deliveries' in tables:
        op.drop_table('digest_deliveries')
    if 'digest_runs' in tables:
        op.drop_table('digest_runs')
    if 'users' in tables and 'notification_prefs' in _column_names('users'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.drop_column('notification_prefs')

    op.create_table(
        'traffic_internal_visitors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('visitor_id', sa.String(length=36), nullable=False),
        sa.Column('registered_at', sa.DateTime(), nullable=False),
        sa.Column('registered_by_user_id', sa.Integer(), nullable=True),
        sa.Column('registration_source', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_traffic_internal_visitors_visitor_id',
        'traffic_internal_visitors',
        ['visitor_id'],
        unique=True,
    )

    op.create_table(
        'traffic_page_views',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('view_id', sa.String(length=36), nullable=False),
        sa.Column('visitor_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('route', sa.String(length=256), nullable=False),
        sa.Column('surface', sa.String(length=32), nullable=False),
        sa.Column('view_mode', sa.String(length=16), nullable=True),
        sa.Column('team_ref', sa.String(length=16), nullable=True),
        sa.Column('pitcher_id', sa.Integer(), nullable=True),
        sa.Column('referrer_domain', sa.String(length=253), nullable=True),
        sa.Column('utm_source', sa.String(length=64), nullable=True),
        sa.Column('utm_medium', sa.String(length=64), nullable=True),
        sa.Column('utm_campaign', sa.String(length=128), nullable=True),
        sa.Column('utm_content', sa.String(length=128), nullable=True),
        sa.Column('site_host', sa.String(length=253), nullable=False),
        sa.Column('device_class', sa.String(length=16), nullable=False),
        sa.Column('is_bot', sa.Boolean(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_traffic_page_views_view_id', 'traffic_page_views', ['view_id'], unique=True)
    op.create_index('ix_traffic_page_views_occurred_at', 'traffic_page_views', ['occurred_at'])
    op.create_index(
        'ix_traffic_page_views_visitor_occurred', 'traffic_page_views', ['visitor_id', 'occurred_at'],
    )
    op.create_index(
        'ix_traffic_page_views_session_occurred', 'traffic_page_views', ['session_id', 'occurred_at'],
    )
    op.create_index(
        'ix_traffic_page_views_route_occurred', 'traffic_page_views', ['route', 'occurred_at'],
    )
    op.create_index(
        'ix_traffic_page_views_site_host_occurred', 'traffic_page_views', ['site_host', 'occurred_at'],
    )
    op.create_index(
        'ix_traffic_page_views_bot_occurred', 'traffic_page_views', ['is_bot', 'occurred_at'],
    )


def downgrade():
    tables = _table_names()
    if 'traffic_page_views' in tables:
        op.drop_table('traffic_page_views')
    if 'traffic_internal_visitors' in tables:
        op.drop_table('traffic_internal_visitors')

    tables = _table_names()
    if 'users' in tables and 'notification_prefs' not in _column_names('users'):
        with op.batch_alter_table('users', schema=None) as batch_op:
            batch_op.add_column(sa.Column('notification_prefs', sa.JSON(), nullable=True))

    if 'digest_runs' not in tables:
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
    if 'digest_deliveries' not in tables:
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
        op.create_index('ix_digest_deliveries_user', 'digest_deliveries', ['user_id'])
        op.create_index('ix_digest_deliveries_status', 'digest_deliveries', ['status'])
        op.create_index('ix_digest_deliveries_run', 'digest_deliveries', ['run_id'])

    if 'product_events' not in tables:
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
        op.create_index('ix_product_events_occurred_at', 'product_events', ['occurred_at'])
        op.create_index('ix_product_events_user', 'product_events', ['user_id'])
        op.create_index(
            'ix_product_events_name_occurred', 'product_events', ['event_name', 'occurred_at'],
        )
