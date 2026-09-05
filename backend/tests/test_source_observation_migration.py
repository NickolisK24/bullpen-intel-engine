import importlib.util
from datetime import date, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations'
    / 'versions'
    / 'd7a3e9c1f5b2_add_source_observation_evidence.py'
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'source_observation_evidence_migration', MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection, operation):
    module = _load_migration()
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, operation)()


def _current_schema(engine):
    metadata = sa.MetaData()
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('sync_jobs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    game_states = sa.Table(
        'game_observation_states', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_pk', sa.Integer(), nullable=False),
    )
    scheduled_games = sa.Table(
        'scheduled_games', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_pk', sa.Integer(), nullable=False),
    )
    transaction_windows = sa.Table(
        'player_transaction_sync_windows', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('window_start', sa.Date(), nullable=False),
        sa.Column('window_end', sa.Date(), nullable=False),
    )
    metadata.create_all(engine)
    return game_states, scheduled_games, transaction_windows


def test_migration_adds_evidence_schema_preserves_links_and_round_trips():
    engine = sa.create_engine('sqlite:///:memory:')
    game_states, scheduled_games, transaction_windows = _current_schema(engine)
    now = datetime(2026, 9, 5, 18, 0, 0)

    with engine.begin() as connection:
        connection.execute(game_states.insert().values(id=1, game_pk=777123))
        connection.execute(scheduled_games.insert().values(id=2, game_pk=777123))
        connection.execute(transaction_windows.insert().values(
            id=3, window_start=date(2026, 9, 5), window_end=date(2026, 9, 5)
        ))
        _run(connection, 'upgrade')

        inspector = sa.inspect(connection)
        assert {
            'source_subjects', 'source_payload_artifacts',
            'source_observations', 'source_fetch_attempts',
        } <= set(inspector.get_table_names())
        for table_name in (
            'game_observation_states', 'scheduled_games',
            'player_transaction_sync_windows',
        ):
            columns = {row['name'] for row in inspector.get_columns(table_name)}
            assert 'source_observation_id' in columns

        connection.execute(sa.text(
            "INSERT INTO source_subjects "
            "(id, identity_key, provider, source_domain, endpoint, subject_type, "
            "subject_key, request_identity, request_schema_version, "
            "request_parameters, created_at, updated_at) VALUES "
            "(10, :identity, 'mlb_stats_api', 'boxscore', '/boxscore', 'game', "
            "'777123', :request_identity, 1, '{}', :now, :now)"
        ), {'identity': 'a' * 64, 'request_identity': 'b' * 64, 'now': now})
        connection.execute(sa.text(
            "INSERT INTO source_observations "
            "(id, source_subject_id, version_number, dedupe_key, fingerprint, "
            "fingerprint_algorithm, fingerprint_version, payload_schema_version, "
            "completeness, outcome, is_change, is_authoritative, observed_at, created_at) "
            "VALUES (20, 10, 1, :dedupe, :fingerprint, 'sha256', "
            "'source-json-sha256-v1', 1, 'complete', 'new', 1, 1, :now, :now)"
        ), {'dedupe': 'c' * 64, 'fingerprint': 'd' * 64, 'now': now})
        connection.execute(sa.text(
            'UPDATE game_observation_states SET source_observation_id = 20 WHERE id = 1'
        ))
        assert connection.execute(sa.text(
            'SELECT source_observation_id FROM game_observation_states WHERE id = 1'
        )).scalar_one() == 20

        _run(connection, 'downgrade')
        inspector = sa.inspect(connection)
        assert 'source_observations' not in inspector.get_table_names()
        assert 'source_observation_id' not in {
            row['name'] for row in inspector.get_columns('game_observation_states')
        }
        assert connection.execute(sa.text(
            'SELECT game_pk FROM game_observation_states WHERE id = 1'
        )).scalar_one() == 777123
        assert connection.execute(sa.text(
            'SELECT game_pk FROM scheduled_games WHERE id = 2'
        )).scalar_one() == 777123
        assert connection.execute(sa.text(
            'SELECT window_start FROM player_transaction_sync_windows WHERE id = 3'
        )).scalar_one() == '2026-09-05'
