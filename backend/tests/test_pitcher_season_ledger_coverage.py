from datetime import date
import importlib.util
from pathlib import Path

import pytest
from flask import Flask
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.pitcher_season_ledger_coverage import PitcherSeasonLedgerCoverage
from models.scheduled_game import ScheduledGame
from services import pitcher_season_ledger_coverage as coverage
from services import sync as sync_service
from services.pitcher_game_log_backfill import backfill_pitcher_game_logs
from utils.db import db


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations'
    / 'versions'
    / '7c4d2e9f1a6b_add_pitcher_season_ledger_coverage.py'
)


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _pitcher():
    pitcher = Pitcher(
        mlb_id=621112,
        full_name='Paul Blackburn',
        team_id=147,
        team_abbreviation='NYY',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _final(game_pk, game_date):
    db.session.add(ScheduledGame(
        team_id=147,
        game_pk=game_pk,
        game_date=game_date,
        status_state=ScheduledGame.STATE_FINAL,
        status_code='F',
        game_type='R',
    ))


def _not_final(game_pk, game_date):
    db.session.add(ScheduledGame(
        team_id=147,
        game_pk=game_pk,
        game_date=game_date,
        status_state=ScheduledGame.STATE_SCHEDULED,
        status_code='S',
        game_type='R',
    ))


def _row(pitcher, game_pk, game_date, games_started=0):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        games_started=games_started,
        innings_pitched=1.0,
        innings_pitched_outs=3,
    ))


def _split(game_pk, game_date, games_started=0):
    return {
        'game': {'gamePk': game_pk, 'gameType': 'R'},
        'date': game_date.isoformat(),
        'stat': {
            'gamesStarted': games_started,
            'inningsPitched': '1.0',
            'strikes': 9,
            'hits': 0,
            'runs': 0,
            'earnedRuns': 0,
            'baseOnBalls': 0,
            'strikeOuts': 1,
            'homeRuns': 0,
        },
    }


def _reconcile(pitcher, splits, through=date(2026, 7, 9)):
    return coverage.reconcile_pitcher_season_coverage(
        pitcher,
        splits,
        season=2026,
        through_date=through,
    )


def _coverage(game_pk):
    return PitcherSeasonLedgerCoverage.query.filter_by(
        target_game_pk=game_pk
    ).one()


def test_exact_manifest_match_produces_complete_coverage(app_ctx):
    pitcher = _pitcher()
    for game_pk, day, started in (
        (9700, date(2026, 5, 7), 1),
        (9701, date(2026, 5, 10), 0),
        (9900, date(2026, 7, 9), 1),
    ):
        _final(game_pk, day)
        _row(pitcher, game_pk, day, started)

    result = _reconcile(pitcher, [
        _split(9700, date(2026, 5, 7), 1),
        _split(9701, date(2026, 5, 10), 0),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()
    record = _coverage(9900)

    assert result['coverage_records_complete'] == 3
    assert record.coverage_status == coverage.STATUS_COMPLETE
    assert record.source_appearance_count == 3
    assert record.stored_appearance_count == 3
    assert record.source_games_started_count == 2
    assert record.stored_games_started_count == 2
    assert record.source_manifest_fingerprint == record.stored_manifest_fingerprint


def test_missing_one_relief_appearance_is_incomplete(app_ctx):
    pitcher = _pitcher()
    for game_pk, day in (
        (9700, date(2026, 5, 7)),
        (9701, date(2026, 5, 10)),
        (9900, date(2026, 7, 9)),
    ):
        _final(game_pk, day)
    _row(pitcher, 9700, date(2026, 5, 7), 1)
    _row(pitcher, 9900, date(2026, 7, 9), 1)

    _reconcile(pitcher, [
        _split(9700, date(2026, 5, 7), 1),
        _split(9701, date(2026, 5, 10), 0),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()

    record = _coverage(9900)
    assert record.coverage_status == coverage.STATUS_INCOMPLETE
    assert coverage.REASON_MANIFEST_MISMATCH in record.reason_codes


def test_matching_counts_with_different_game_ids_still_fails(app_ctx):
    pitcher = _pitcher()
    for game_pk, day in (
        (9700, date(2026, 5, 7)),
        (9701, date(2026, 5, 10)),
        (9702, date(2026, 5, 11)),
        (9900, date(2026, 7, 9)),
    ):
        _final(game_pk, day)
    _row(pitcher, 9700, date(2026, 5, 7), 1)
    _row(pitcher, 9702, date(2026, 5, 11), 0)
    _row(pitcher, 9900, date(2026, 7, 9), 1)

    _reconcile(pitcher, [
        _split(9700, date(2026, 5, 7), 1),
        _split(9701, date(2026, 5, 10), 0),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()

    record = _coverage(9900)
    assert record.source_appearance_count == record.stored_appearance_count
    assert record.coverage_status == coverage.STATUS_INCOMPLETE
    assert record.source_manifest_fingerprint != record.stored_manifest_fingerprint


def test_same_game_with_conflicting_games_started_fails(app_ctx):
    pitcher = _pitcher()
    for game_pk, day in (
        (9700, date(2026, 5, 7)),
        (9900, date(2026, 7, 9)),
    ):
        _final(game_pk, day)
    _row(pitcher, 9700, date(2026, 5, 7), 0)
    _row(pitcher, 9900, date(2026, 7, 9), 1)

    _reconcile(pitcher, [
        _split(9700, date(2026, 5, 7), 1),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()

    record = _coverage(9900)
    assert record.coverage_status == coverage.STATUS_INCOMPLETE
    assert record.source_games_started_count != record.stored_games_started_count


def test_identical_source_duplicates_normalize_safely(app_ctx):
    pitcher = _pitcher()
    for game_pk, day, started in (
        (9700, date(2026, 5, 7), 1),
        (9900, date(2026, 7, 9), 1),
    ):
        _final(game_pk, day)
        _row(pitcher, game_pk, day, started)

    _reconcile(pitcher, [
        _split(9700, date(2026, 5, 7), 1),
        _split(9700, date(2026, 5, 7), 1),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()

    assert _coverage(9900).coverage_status == coverage.STATUS_COMPLETE


def test_conflicting_source_duplicates_fail(app_ctx):
    pitcher = _pitcher()
    for game_pk, day, started in (
        (9700, date(2026, 5, 7), 1),
        (9900, date(2026, 7, 9), 1),
    ):
        _final(game_pk, day)
        _row(pitcher, game_pk, day, started)

    _reconcile(pitcher, [
        _split(9700, date(2026, 5, 7), 1),
        _split(9700, date(2026, 5, 7), 0),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()

    record = _coverage(9900)
    assert record.coverage_status == coverage.STATUS_INCOMPLETE
    assert coverage.REASON_SOURCE_DUPLICATE_CONFLICT in record.reason_codes


def test_same_date_doubleheader_targets_are_exact_subsets(app_ctx):
    pitcher = _pitcher()
    for game_pk in (9801, 9802):
        _final(game_pk, date(2026, 7, 5))
        _row(pitcher, game_pk, date(2026, 7, 5), 0)

    _reconcile(pitcher, [
        _split(9802, date(2026, 7, 5), 0),
        _split(9801, date(2026, 7, 5), 0),
    ])
    db.session.commit()

    assert _coverage(9801).source_appearance_count == 1
    assert _coverage(9802).source_appearance_count == 2


def test_unknown_source_games_started_blocks_coverage(app_ctx):
    result = coverage.build_source_manifest(
        [_split(9700, date(2026, 5, 7), None)],
        through_date=date(2026, 7, 9),
    )

    assert result['entries'] == []
    assert coverage.REASON_SOURCE_UNKNOWN_GAMES_STARTED in result['reason_codes']


def test_non_final_source_game_blocks_later_target(app_ctx):
    pitcher = _pitcher()
    _not_final(9701, date(2026, 5, 10))
    _final(9900, date(2026, 7, 9))
    _row(pitcher, 9900, date(2026, 7, 9), 1)

    _reconcile(pitcher, [
        _split(9701, date(2026, 5, 10), 0),
        _split(9900, date(2026, 7, 9), 1),
    ])
    db.session.commit()

    record = _coverage(9900)
    assert record.coverage_status == coverage.STATUS_INCOMPLETE
    assert coverage.REASON_SOURCE_NOT_FINAL in record.reason_codes


def test_backfill_inserts_missing_finalized_rows_and_is_idempotent(
    app_ctx,
    monkeypatch,
):
    pitcher = _pitcher()
    for game_pk, day in (
        (9700, date(2026, 5, 7)),
        (9900, date(2026, 7, 9)),
    ):
        _final(game_pk, day)
    splits = [
        _split(9700, date(2026, 5, 7), 1),
        _split(9900, date(2026, 7, 9), 1),
    ]

    class Client:
        def get_pitcher_game_logs(self, player_id, season=None):
            assert player_id == pitcher.mlb_id
            return splits

    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines', lambda pk: [])

    first = backfill_pitcher_game_logs(
        season=2026,
        through_date=date(2026, 7, 9),
        apply=True,
        pitcher_mlb_id=pitcher.mlb_id,
        client=Client(),
    )
    second = backfill_pitcher_game_logs(
        season=2026,
        through_date=date(2026, 7, 9),
        apply=True,
        pitcher_mlb_id=pitcher.mlb_id,
        client=Client(),
    )

    rows = GameLog.query.filter_by(pitcher_id=pitcher.id).all()
    assert first['records_inserted'] == 2
    assert second['records_inserted'] == 0
    assert second['records_unchanged'] == 2
    assert len(rows) == 2
    assert _coverage(9900).coverage_status == coverage.STATUS_COMPLETE


def test_pitcher_ledger_coverage_migration_round_trips_and_enforces_unique_target():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('pitchers', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        module = _load_migration()
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()

        columns = {
            row._mapping['name']
            for row in connection.execute(
                sa.text('PRAGMA table_info(pitcher_season_ledger_coverage)')
            )
        }
        assert {
            'pitcher_id',
            'season',
            'game_type',
            'target_game_pk',
            'source_manifest_fingerprint',
            'stored_manifest_fingerprint',
            'coverage_status',
            'reason_codes',
        }.issubset(columns)

        payload = {
            'pitcher_id': 1,
            'pitcher_mlb_id': 621112,
            'season': 2026,
            'game_type': 'R',
            'target_game_pk': 9900,
            'covered_through_date': '2026-07-09',
            'source_appearance_count': 22,
            'source_games_started_count': 2,
            'stored_appearance_count': 22,
            'stored_games_started_count': 2,
            'source_manifest_fingerprint': 'a' * 64,
            'stored_manifest_fingerprint': 'a' * 64,
            'coverage_status': 'complete',
            'reason_codes': '[]',
            'verified_at': '2026-07-10 00:00:00',
            'created_at': '2026-07-10 00:00:00',
            'updated_at': '2026-07-10 00:00:00',
        }
        connection.execute(
            sa.text(
                'INSERT INTO pitcher_season_ledger_coverage ('
                'pitcher_id, pitcher_mlb_id, season, game_type, target_game_pk, '
                'covered_through_date, source_appearance_count, '
                'source_games_started_count, stored_appearance_count, '
                'stored_games_started_count, source_manifest_fingerprint, '
                'stored_manifest_fingerprint, coverage_status, reason_codes, '
                'verified_at, created_at, updated_at'
                ') VALUES ('
                ':pitcher_id, :pitcher_mlb_id, :season, :game_type, '
                ':target_game_pk, :covered_through_date, '
                ':source_appearance_count, :source_games_started_count, '
                ':stored_appearance_count, :stored_games_started_count, '
                ':source_manifest_fingerprint, :stored_manifest_fingerprint, '
                ':coverage_status, :reason_codes, :verified_at, :created_at, '
                ':updated_at)'
            ),
            payload,
        )
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(
                sa.text(
                    'INSERT INTO pitcher_season_ledger_coverage ('
                    'pitcher_id, pitcher_mlb_id, season, game_type, target_game_pk, '
                    'covered_through_date, source_manifest_fingerprint, '
                    'stored_manifest_fingerprint, verified_at, created_at, updated_at'
                    ') VALUES ('
                    ':pitcher_id, :pitcher_mlb_id, :season, :game_type, '
                    ':target_game_pk, :covered_through_date, '
                    ':source_manifest_fingerprint, :stored_manifest_fingerprint, '
                    ':verified_at, :created_at, :updated_at)'
                ),
                payload,
            )
        connection.rollback()

    with engine.begin() as connection:
        module = _load_migration()
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.downgrade()
        tables = {
            row._mapping['name']
            for row in connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert 'pitcher_season_ledger_coverage' not in tables


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'pitcher_season_ledger_coverage_migration',
        MIGRATION_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
