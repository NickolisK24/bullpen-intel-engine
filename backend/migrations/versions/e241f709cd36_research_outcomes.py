"""Add bounded traffic outcomes and the verified first-pitch clock."""
from importlib import import_module

from alembic import op
import sqlalchemy as sa

revision = 'e241f709cd36'
down_revision = 'de608f29a341'
branch_labels = None
depends_on = None


def _certify(head):
    if op.get_bind().dialect.name == 'postgresql':
        prior = import_module('migrations.versions.de608f29a341_murphy_transaction_recovery')
        prior._certify_existing_roster_functions(head)
        op.execute(prior.ADMISSION.replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION', 1)
                   .replace(down_revision, head))


def upgrade():
    op.add_column('traffic_page_views', sa.Column('research_outcome', sa.String(24)))
    op.add_column('traffic_page_views', sa.Column('answer_ms', sa.Integer()))
    op.add_column('traffic_page_views', sa.Column('matchup_game_pk', sa.Integer()))
    op.add_column('play_by_play_processed_games', sa.Column('first_pitch_at', sa.DateTime()))
    _certify(revision)


def downgrade():
    _certify(down_revision)
    op.drop_column('play_by_play_processed_games', 'first_pitch_at')
    for name in ('matchup_game_pk', 'answer_ms', 'research_outcome'):
        op.drop_column('traffic_page_views', name)
