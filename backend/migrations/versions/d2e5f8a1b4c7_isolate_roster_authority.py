"""Scope current membership uniqueness and retain explicit void correction versions.

Revision ID: d2e5f8a1b4c7
Revises: c9d4e6f8a1b2
"""

from alembic import op
import sqlalchemy as sa

revision = 'd2e5f8a1b4c7'
down_revision = 'c9d4e6f8a1b2'
branch_labels = None
depends_on = None

OLD = 'uq_roster_membership_intervals_current_open_player_type'
NEW = 'uq_roster_membership_intervals_current_open_player_team_type'
TABLE = 'roster_membership_intervals'


def upgrade():
    op.add_column(TABLE, sa.Column('is_void', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(
        NEW, TABLE, ['pitcher_id', 'team_id', 'membership_type'], unique=True,
        postgresql_where=sa.text('effective_end_date IS NULL AND is_current_version = true AND is_void = false'),
        sqlite_where=sa.text('effective_end_date IS NULL AND is_current_version = 1 AND is_void = 0'),
    )
    op.drop_index(OLD, table_name=TABLE)


def downgrade():
    # An old reader cannot represent void versions or legitimate scoped coexistence.
    # Refuse to erase correction meaning; this is a forward-only data boundary.
    connection = op.get_bind()
    if connection.execute(sa.text(f'SELECT 1 FROM {TABLE} WHERE is_void = true LIMIT 1')).first():
        raise RuntimeError('Roster correction history requires the AUDIT-R1 schema; downgrade refused')
    op.create_index(
        OLD, TABLE, ['pitcher_id', 'membership_type'], unique=True,
        postgresql_where=sa.text('effective_end_date IS NULL AND is_current_version = true'),
        sqlite_where=sa.text('effective_end_date IS NULL AND is_current_version = 1'),
    )
    op.drop_index(NEW, table_name=TABLE)
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column('is_void')
