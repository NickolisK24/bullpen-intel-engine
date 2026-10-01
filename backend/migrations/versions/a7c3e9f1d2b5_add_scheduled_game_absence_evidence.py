"""Schedule absence evidence on scheduled_games (postseason conditional games).

Two nullable columns, both written only by schedule ingestion:

* ``if_necessary``: MLB's own ``ifNecessary`` flag ('Y'/'N') for the game,
  stored verbatim. It identifies a postseason "if necessary" game from the
  source itself instead of from series position alone.
* ``schedule_absent_since``: when a structurally sound, league-wide MLB
  schedule response first stopped listing a stored postseason conditional
  game. A later, separate response must confirm the absence before the game
  is retired (``services.schedule_absence``). Cleared whenever MLB lists the
  game again.

Additive only: no existing row, column, index, constraint, function, trigger or
access-control setting changes. ``scheduled_games`` already carries SEC-01 row
level security and the schedule ownership fence, both of which apply to the new
columns unchanged. Existing rows read NULL.

Revision ID: a7c3e9f1d2b5
Revises: d4a8f2c6e9b3
"""
from alembic import op
import sqlalchemy as sa


revision = 'a7c3e9f1d2b5'
down_revision = 'd4a8f2c6e9b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('scheduled_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('if_necessary', sa.String(length=2), nullable=True))
        batch_op.add_column(sa.Column('schedule_absent_since', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('scheduled_games', schema=None) as batch_op:
        batch_op.drop_column('schedule_absent_since')
        batch_op.drop_column('if_necessary')
