"""Tests for Schedule Storage V1 (scheduled_games + ingestion).

Covers: table creation, one game -> two team rows with correct home/away and
opponent assignment, conservative status normalization, doubleheader/series
parsing, safe handling of missing optional fields, and idempotent upsert (a
re-ingest updates changed status/time in place instead of duplicating rows).
The ingestion service stores schedule facts only — no context, no predictions.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from services import schedule_ingestion
from services.schedule_ingestion import ingest_games, ingest_schedule
from utils.db import db
from models.scheduled_game import ScheduledGame
import models.prospect  # noqa: F401  (full model registry for create_all)

# Script under test (argument/window resolution).
import scripts.ingest_schedule as ingest_script


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _game(game_pk=700123, *, home_id=116, away_id=118, official_date='2026-06-25',
          game_date='2026-06-25T23:10:00Z', game_type='R', status_code='S',
          detailed_state='Scheduled', abstract_state='Preview',
          double_header='N', game_number=1, series_game_number=2, games_in_series=3):
    return {
        'gamePk': game_pk,
        'officialDate': official_date,
        'gameDate': game_date,
        'gameType': game_type,
        'doubleHeader': double_header,
        'gameNumber': game_number,
        'seriesGameNumber': series_game_number,
        'gamesInSeries': games_in_series,
        'status': {
            'statusCode': status_code,
            'detailedState': detailed_state,
            'abstractGameState': abstract_state,
        },
        'teams': {
            'home': {'team': {'id': home_id, 'name': 'Home Club'}},
            'away': {'team': {'id': away_id, 'name': 'Away Club'}},
        },
    }


def _by_team(game_pk):
    return {r.team_id: r for r in ScheduledGame.query.filter_by(game_pk=game_pk).all()}


# ── Table creation ────────────────────────────────────────────────────────────

def test_table_is_created_and_starts_empty(app):
    with app.app_context():
        assert ScheduledGame.query.count() == 0


# ── One game -> two team rows, home/away + opponent ───────────────────────────

def test_one_game_creates_two_team_rows_with_opponent_assignment(app):
    with app.app_context():
        summary = ingest_games([_game()], source='test')
        assert summary['games_ingested'] == 1
        assert summary['rows_created'] == 2
        rows = _by_team(700123)
        assert set(rows) == {116, 118}

        home = rows[116]
        assert home.home_away == 'home'
        assert home.opponent_team_id == 118
        assert home.game_date == date(2026, 6, 25)
        assert home.game_datetime == datetime(2026, 6, 25, 23, 10, 0)  # naive UTC
        assert home.game_type == 'R'

        away = rows[118]
        assert away.home_away == 'away'
        assert away.opponent_team_id == 116
        assert away.game_date == date(2026, 6, 25)


# ── Status normalization ──────────────────────────────────────────────────────

@pytest.mark.parametrize('code,detailed,abstract,expected', [
    ('S', 'Scheduled', 'Preview', 'scheduled'),
    ('P', 'Pre-Game', 'Preview', 'scheduled'),
    ('F', 'Final', 'Final', 'final'),
    ('O', 'Game Over', 'Final', 'final'),
    ('DR', 'Postponed', 'Preview', 'postponed'),
    ('U', 'Suspended', 'Live', 'suspended'),
    ('I', 'In Progress', 'Live', 'other'),
    ('C', 'Cancelled', 'Final', 'other'),
    ('XX', 'Some New State', 'Other', 'other'),
])
def test_status_state_normalization(app, code, detailed, abstract, expected):
    with app.app_context():
        ingest_games([_game(game_pk=900, status_code=code,
                            detailed_state=detailed, abstract_state=abstract)],
                     source='test')
        row = _by_team(900)[116]
        assert row.status_state == expected
        assert row.status_code == code   # raw code preserved verbatim


def test_postponed_takes_precedence_over_final_code(app):
    # A postponed game can still carry an ambiguous code; detailed state wins.
    with app.app_context():
        ingest_games([_game(game_pk=901, status_code='F',
                            detailed_state='Postponed', abstract_state='Final')],
                     source='test')
        assert _by_team(901)[116].status_state == 'postponed'


# ── Doubleheader / series parsing ─────────────────────────────────────────────

def test_doubleheader_and_series_fields_are_parsed(app):
    with app.app_context():
        ingest_games([_game(game_pk=902, double_header='S', game_number=2,
                            series_game_number=3, games_in_series=4)], source='test')
        row = _by_team(902)[116]
        assert row.doubleheader == 'S'
        assert row.game_number == 2
        assert row.series_game_number == 3
        assert row.games_in_series == 4


def test_doubleheader_games_stay_separate_by_game_pk(app):
    with app.app_context():
        ingest_games([
            _game(game_pk=1001, game_number=1),
            _game(game_pk=1002, game_number=2),
        ], source='test')
        assert ScheduledGame.query.filter_by(team_id=116).count() == 2
        assert {r.game_pk for r in ScheduledGame.query.filter_by(team_id=116)} == {1001, 1002}


def test_resumed_linkage_fields_are_parsed(app):
    with app.app_context():
        ingest_games([
            _game(
                game_pk=1101,
                official_date='2026-07-04',
                status_code='F',
                detailed_state='Final',
                abstract_state='Final',
            ) | {
                'resumedFrom': 1001,
                'resumedFromDate': '2026-06-20',
            },
            _game(
                game_pk=1102,
                status_code='U',
                detailed_state='Suspended',
                abstract_state='Live',
            ) | {
                'rescheduleDate': '2026-07-05',
                'rescheduledGamePk': 1103,
            },
        ], source='test')

        resumed = _by_team(1101)[116]
        suspended = _by_team(1102)[116]

        assert resumed.status_state == 'final'
        assert resumed.resumed_from_game_pk == 1001
        assert resumed.original_game_date == date(2026, 6, 20)
        assert resumed.original_product_date == date(2026, 6, 20)
        assert resumed.resumed_product_date == date(2026, 7, 4)
        assert suspended.status_state == 'suspended'
        assert suspended.resumed_to_game_pk == 1103
        assert suspended.resumed_game_date == date(2026, 7, 5)
        assert suspended.resumed_product_date == date(2026, 7, 5)


# ── Missing optional fields do not crash ──────────────────────────────────────

def test_missing_optional_fields_are_handled_safely(app):
    minimal = {
        'gamePk': 950,
        'officialDate': '2026-06-26',
        'teams': {'home': {'team': {'id': 120}}, 'away': {'team': {'id': 121}}},
        # no gameDate, gameType, status, doubleHeader, series fields
    }
    with app.app_context():
        summary = ingest_games([minimal], source='test')
        assert summary['rows_created'] == 2
        row = _by_team(950)[120]
        assert row.game_datetime is None
        assert row.game_type is None
        assert row.status_code is None
        assert row.status_state == 'other'   # nothing decisive -> conservative default
        assert row.doubleheader is None
        assert row.game_number is None
        assert row.series_game_number is None


def test_unusable_games_are_skipped_not_fatal(app):
    games = [
        {'officialDate': '2026-06-26', 'teams': {}},      # no gamePk
        _game(game_pk=0) | {'gamePk': None},               # null gamePk
        {'gamePk': 9999, 'teams': {}},                     # no teams, no date
        _game(game_pk=970),                                # one good game
    ]
    with app.app_context():
        summary = ingest_games(games, source='test')
        assert summary['games_ingested'] == 1
        assert summary['games_skipped'] == 3
        assert ScheduledGame.query.filter_by(game_pk=970).count() == 2


# ── Idempotent upsert ─────────────────────────────────────────────────────────

def test_reingest_updates_in_place_without_duplicating(app):
    with app.app_context():
        ingest_games([_game(game_pk=800, status_code='S',
                            detailed_state='Scheduled', abstract_state='Preview',
                            game_date='2026-06-25T23:10:00Z')], source='first')
        assert ScheduledGame.query.filter_by(game_pk=800).count() == 2

        # Same game later goes Final, start time corrected, opponent unchanged.
        summary = ingest_games([_game(game_pk=800, status_code='F',
                                      detailed_state='Final', abstract_state='Final',
                                      game_date='2026-06-25T23:40:00Z')], source='second')
        assert summary['rows_updated'] == 2
        assert summary['rows_created'] == 0
        assert ScheduledGame.query.filter_by(game_pk=800).count() == 2   # no dupes

        home = _by_team(800)[116]
        assert home.status_state == 'final'
        assert home.status_code == 'F'
        assert home.game_datetime == datetime(2026, 6, 25, 23, 40, 0)
        assert home.source == 'second'


def test_unique_constraint_on_team_game(app):
    with app.app_context():
        db.session.add(ScheduledGame(team_id=116, game_pk=555, game_date=date(2026, 6, 25),
                                     status_state='scheduled'))
        db.session.commit()
        db.session.add(ScheduledGame(team_id=116, game_pk=555, game_date=date(2026, 6, 25),
                                     status_state='scheduled'))
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()


# ── Service fetch path (mlb_client injected) ──────────────────────────────────

def test_ingest_schedule_calls_mlb_client_with_window(app, monkeypatch):
    seen = {}

    def fake_schedule(start_date=None, end_date=None, team_id=None):
        seen['start'] = start_date
        seen['end'] = end_date
        return [_game(game_pk=600)]

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', fake_schedule)
    with app.app_context():
        summary = ingest_schedule(date(2026, 6, 20), date(2026, 6, 30), source='svc')
        assert seen == {'start': '2026-06-20', 'end': '2026-06-30'}
        assert summary['rows_created'] == 2
        assert ScheduledGame.query.filter_by(game_pk=600).count() == 2


def test_ingest_schedule_empty_result_is_safe(app, monkeypatch):
    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule',
                        lambda **kwargs: [])
    with app.app_context():
        summary = ingest_schedule('2026-06-20', '2026-06-30')
        assert summary['games_seen'] == 0
        assert summary['rows_created'] == 0


def test_refresh_non_final_games_for_slate_updates_stale_prior_game_to_final(app, monkeypatch):
    slate_date = date(2026, 7, 5)
    seen = {}

    def fake_schedule(start_date=None, end_date=None, team_id=None):
        seen['start'] = start_date
        seen['end'] = end_date
        return [
            _game(
                game_pk=824010,
                home_id=108,
                away_id=111,
                official_date=slate_date.isoformat(),
                game_date='2026-07-05T20:10:00Z',
                status_code='F',
                detailed_state='Final',
                abstract_state='Final',
            )
        ]

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', fake_schedule)
    with app.app_context():
        ingest_games([
            _game(
                game_pk=824010,
                home_id=108,
                away_id=111,
                official_date=slate_date.isoformat(),
                game_date='2026-07-05T20:10:00Z',
                status_code='I',
                detailed_state='In Progress',
                abstract_state='Live',
            )
        ], source='initial')

        result = schedule_ingestion.refresh_non_final_games_for_slate(
            slate_date,
            source='test_finality_refresh',
        )

        rows = _by_team(824010)
        assert seen == {'start': '2026-07-05', 'end': '2026-07-05'}
        assert result['status'] == 'refreshed'
        assert result['candidate_game_pks'] == [824010]
        assert result['summary']['rows_updated'] == 2
        assert rows[108].status_state == ScheduledGame.STATE_FINAL
        assert rows[111].status_state == ScheduledGame.STATE_FINAL
        assert rows[108].status_code == 'F'


def test_refresh_non_final_games_for_slate_keeps_source_non_final(app, monkeypatch):
    slate_date = date(2026, 7, 5)

    monkeypatch.setattr(
        schedule_ingestion.mlb_client,
        'get_schedule',
        lambda **_kwargs: [
            _game(
                game_pk=824010,
                home_id=108,
                away_id=111,
                official_date=slate_date.isoformat(),
                game_date='2026-07-05T20:10:00Z',
                status_code='I',
                detailed_state='In Progress',
                abstract_state='Live',
            )
        ],
    )
    with app.app_context():
        ingest_games([
            _game(
                game_pk=824010,
                home_id=108,
                away_id=111,
                official_date=slate_date.isoformat(),
                game_date='2026-07-05T20:10:00Z',
                status_code='I',
                detailed_state='In Progress',
                abstract_state='Live',
            )
        ], source='initial')

        result = schedule_ingestion.refresh_non_final_games_for_slate(slate_date)

        rows = _by_team(824010)
        assert result['status'] == 'refreshed'
        assert result['status_states_by_game_pk'] == {'824010': [ScheduledGame.STATE_OTHER]}
        assert rows[108].status_state == ScheduledGame.STATE_OTHER
        assert rows[111].status_state == ScheduledGame.STATE_OTHER


def test_refresh_non_final_games_for_slate_skips_final_and_postponed_games(app, monkeypatch):
    def fail_schedule(**_kwargs):
        raise AssertionError('final or postponed slate should not be re-fetched')

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', fail_schedule)
    with app.app_context():
        ingest_games([
            _game(game_pk=824011, status_code='F', detailed_state='Final',
                  abstract_state='Final'),
            _game(game_pk=824012, status_code='DR', detailed_state='Postponed',
                  abstract_state='Preview'),
        ], source='initial')

        result = schedule_ingestion.refresh_non_final_games_for_slate(date(2026, 6, 25))

        assert result == {
            'status': 'skipped',
            'reason': 'no_non_final_games',
            'slate_date': '2026-06-25',
            'candidate_game_pks': [],
        }


def test_refresh_non_final_games_for_slate_preserves_suspended_source(app, monkeypatch):
    slate_date = date(2026, 7, 5)

    monkeypatch.setattr(
        schedule_ingestion.mlb_client,
        'get_schedule',
        lambda **_kwargs: [
            _game(
                game_pk=824010,
                home_id=108,
                away_id=111,
                official_date=slate_date.isoformat(),
                game_date='2026-07-05T20:10:00Z',
                status_code='U',
                detailed_state='Suspended',
                abstract_state='Live',
            ) | {'rescheduledGamePk': 824099, 'rescheduleDate': '2026-07-06'}
        ],
    )
    with app.app_context():
        ingest_games([
            _game(
                game_pk=824010,
                home_id=108,
                away_id=111,
                official_date=slate_date.isoformat(),
                game_date='2026-07-05T20:10:00Z',
                status_code='I',
                detailed_state='In Progress',
                abstract_state='Live',
            )
        ], source='initial')

        result = schedule_ingestion.refresh_non_final_games_for_slate(slate_date)

        rows = _by_team(824010)
        assert result['status'] == 'refreshed'
        assert rows[108].status_state == ScheduledGame.STATE_SUSPENDED
        assert rows[108].resumed_to_game_pk == 824099
        assert rows[108].resumed_product_date == slate_date.replace(day=6)


# ── Script argument / window resolution ───────────────────────────────────────

def test_script_resolves_explicit_window():
    start, end = ingest_script._resolve_window('2026-06-01', '2026-06-05', date(2026, 6, 27))
    assert start == '2026-06-01'
    assert end == '2026-06-05'


def test_script_defaults_to_rolling_window_around_today():
    start, end = ingest_script._resolve_window(None, None, date(2026, 6, 27))
    assert start == '2026-06-17'   # today - 10
    assert end == '2026-07-07'     # today + 10


def test_script_rejects_inverted_window():
    with pytest.raises(ValueError):
        ingest_script._resolve_window('2026-06-10', '2026-06-01', date(2026, 6, 27))


def test_script_arg_parser_accepts_expected_flags():
    args = ingest_script._parse_args(
        ['--start-date', '2026-06-01', '--end-date', '2026-06-05', '--source', 'manual'])
    assert args.start_date == '2026-06-01'
    assert args.end_date == '2026-06-05'
    assert args.source == 'manual'


# ── Production schedule-ownership fence (SyncRun 92585 / Sep. 24 slate) ───────
#
# Production PostgreSQL carries ``baseballos_schedule_projection_fence``
# (migration e3f6a9b2c5d8). Once the sync-pipeline runtime adopts a game
# (``operational_state`` set), the trigger returns the OLD row for every
# schedule write from a session that has not declared schedule ownership. Main
# never declared it, so after that runtime stopped (its verify-only head check
# refuses any head but its own), every authoritative Scheduled -> Final
# transition for adopted games was silently discarded while ingestion still
# counted rows as updated. These tests run against the real migrated schema.

import importlib
import json
import os
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.db_config import assert_disposable_test_target
from tests.db_config import test_database_url as _test_database_url

_BACKEND = Path(__file__).resolve().parents[1]
_SEP_24 = date(2026, 9, 24)
_SEP_25 = date(2026, 9, 25)
_ADOPTED_FINAL_PKS = (822842, 823087, 823326)


def _migration_env(url):
    env = {**os.environ, 'APP_ENV': 'production', 'AUTO_SYNC': 'false',
           'DATABASE_URL': url, 'TEST_DATABASE_URL': url,
           'DATABASE_MIGRATION_MODE': 'owner', 'RENDER_GIT_BRANCH': 'main',
           'SECRET_KEY': 'isolated-schedule-fence-test-secret-key-32chars',
           'ADMIN_API_TOKEN': 'isolated-schedule-fence-test-admin-token-32ch',
           'SYNC_PIPELINE_SHADOW_MODE': 'false'}
    env.pop('GITHUB_REF', None)
    env.pop('SKIP_STARTUP_MIGRATIONS', None)
    return env


@pytest.fixture
def fenced_database_url():
    """A disposable database built by the real migration chain (fence included)."""
    url = _test_database_url()
    assert_disposable_test_target(url, operation='schedule ownership fence proof')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql':
        pytest.skip('The schedule fence is a PostgreSQL trigger; CI backend shards provide it')
    admin = create_engine(parsed.set(database='postgres'), isolation_level='AUTOCOMMIT')
    name = f'schedule_fence_test_{uuid.uuid4().hex[:12]}'
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    target = parsed.set(database=name).render_as_string(hide_password=False)
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'flask', '--app', 'app', 'db', 'upgrade'],
            cwd=_BACKEND, env=_migration_env(target), capture_output=True, text=True,
            timeout=300,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        yield target
    finally:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()


@pytest.fixture
def fenced_app(fenced_database_url, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', fenced_database_url)
    monkeypatch.setenv('TEST_DATABASE_URL', fenced_database_url)
    flask_app = importlib.import_module('app').create_app('test')
    flask_app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    flask_app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    with flask_app.app_context():
        assert db.session.execute(text(
            "SELECT count(*) FROM pg_trigger WHERE tgname='baseballos_schedule_projection_fence'"
        )).scalar() == 2
        try:
            yield flask_app
        finally:
            db.session.remove()


def _adopt_like_sync_pipeline(game_pks, *, state='scheduled'):
    """Adopt games exactly as the sync-pipeline runtime does: declared owner."""
    keys = json.dumps(sorted(str(pk) for pk in game_pks))
    db.session.execute(text(
        "SELECT set_config('baseballos.schedule_owners', :keys, true)"
    ), {'keys': keys})
    db.session.execute(text(
        'UPDATE scheduled_games SET operational_state=:state, '
        "status_detailed_state='Scheduled', status_abstract_state='Preview' "
        'WHERE game_pk = ANY(:pks)'
    ), {'state': state, 'pks': list(game_pks)})
    db.session.commit()


def _sep_24_game(game_pk, index, **status):
    return _game(
        game_pk=game_pk, home_id=108 + 2 * index, away_id=109 + 2 * index,
        official_date=_SEP_24.isoformat(), game_date='2026-09-24T23:05:00Z',
        **status,
    )


_FINAL = {'status_code': 'F', 'detailed_state': 'Final', 'abstract_state': 'Final'}


def _fresh_rows(url, table, columns, game_pks):
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(text(
                f'SELECT game_pk, {columns} FROM {table} '
                'WHERE game_pk = ANY(:pks) ORDER BY game_pk'
            ), {'pks': list(game_pks)}).all()
    finally:
        engine.dispose()


def test_ingest_declares_schedule_ownership_for_adopted_games(fenced_app, monkeypatch):
    with fenced_app.app_context():
        ingest_games([_sep_24_game(pk, i) for i, pk in enumerate(_ADOPTED_FINAL_PKS)])
        _adopt_like_sync_pipeline(_ADOPTED_FINAL_PKS)

        summary = ingest_games([
            _sep_24_game(pk, i, **_FINAL) for i, pk in enumerate(_ADOPTED_FINAL_PKS)
        ], source='daily_finality_preflight')

        assert summary['rows_updated'] == 6
        assert db.session.execute(text(
            "SELECT count(*) FROM compatibility_write_events WHERE outcome='stale_suppressed'"
        )).scalar() == 0
        # The declaration is transaction-local: nothing leaks past the commit.
        assert db.session.execute(text(
            "SELECT coalesce(current_setting('baseballos.schedule_owners', true), '')"
        )).scalar() == ''
        db.session.commit()

    url = os.environ['DATABASE_URL']
    scheduled = _fresh_rows(url, 'scheduled_games', 'status_state, status_code, operational_state',
                            _ADOPTED_FINAL_PKS)
    assert {(pk, state, code) for pk, state, code, _op in scheduled} == {
        (pk, ScheduledGame.STATE_FINAL, 'F') for pk in _ADOPTED_FINAL_PKS
    }
    assert len(scheduled) == 6
    slate = _fresh_rows(url, 'slate_games', 'normalized_state, status_code', _ADOPTED_FINAL_PKS)
    assert {row[1] for row in slate} == {'completed'}
    assert {row[2] for row in slate} == {'F'}


def test_ingest_follows_mlb_state_without_over_correcting(fenced_app):
    future = _game(game_pk=900001, home_id=110, away_id=111, official_date='2026-09-26',
                   game_date='2026-09-26T23:05:00Z')
    postponed = _sep_24_game(900002, 3, status_code='D', detailed_state='Postponed',
                             abstract_state='Final')
    suspended = _sep_24_game(900003, 4, status_code='U', detailed_state='Suspended',
                             abstract_state='Live') | {
        'rescheduledGamePk': 900099, 'rescheduleDate': '2026-09-25'}
    final = _sep_24_game(900004, 5, **_FINAL)
    resumed = _game(game_pk=900099, home_id=116, away_id=117, official_date='2026-09-25',
                    game_date='2026-09-25T17:05:00Z') | {
        'resumedFrom': 900003, 'resumedFromDate': '2026-09-24'}
    pks = (900001, 900002, 900003, 900004, 900099)
    with fenced_app.app_context():
        ingest_games([_game(game_pk=pk, home_id=120 + i, away_id=130 + i,
                            official_date=_SEP_24.isoformat())
                      for i, pk in enumerate(pks)])
        _adopt_like_sync_pipeline(pks)

        ingest_games([future, postponed, suspended, final, resumed])

        states = {
            row.game_pk: row for row in ScheduledGame.query.filter(
                ScheduledGame.game_pk.in_(pks)).all()
        }
        assert states[900001].status_state == ScheduledGame.STATE_SCHEDULED
        assert states[900001].game_date == date(2026, 9, 26)
        assert states[900002].status_state == ScheduledGame.STATE_POSTPONED
        assert states[900003].status_state == ScheduledGame.STATE_SUSPENDED
        assert states[900003].resumed_to_game_pk == 900099
        assert states[900004].status_state == ScheduledGame.STATE_FINAL
        assert states[900099].status_state == ScheduledGame.STATE_SCHEDULED
        assert states[900099].resumed_from_game_pk == 900003
        assert states[900099].original_game_date == _SEP_24


def test_daily_finality_survives_withheld_publication_and_clears_coverage(
    fenced_app, monkeypatch,
):
    """SyncRun 92585 shape: finality preflight, then a withheld candidate."""
    from datetime import datetime as _dt

    from api import bullpen as bullpen_api
    from models.dashboard_snapshot import DashboardSnapshot
    from models.postgame_processed_game import PostgameProcessedGame
    from models.sync_run import SyncRun
    from services import dashboard_snapshot, slate_coverage
    from services import sync as sync_service

    sep_24_games = [_sep_24_game(pk, i) for i, pk in enumerate(_ADOPTED_FINAL_PKS)]
    final_games = [_sep_24_game(pk, i, **_FINAL) for i, pk in enumerate(_ADOPTED_FINAL_PKS)]
    source = {'games': sep_24_games}

    def mlb_schedule(start_date=None, end_date=None, team_id=None):
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        return [g for g in source['games'] if start <= date.fromisoformat(g['officialDate']) <= end]

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', mlb_schedule)
    with fenced_app.app_context():
        ingest_games(sep_24_games, source='daily_slate_schedule')
        _adopt_like_sync_pipeline(_ADOPTED_FINAL_PKS)
        before = slate_coverage.compute_slate_coverage(_SEP_24)
        assert 'scheduled_games_not_final' in before['reason_codes']

        prior_run = SyncRun(job_name='daily_sync', status='success', stage='published',
                            source='test')
        db.session.add(prior_run)
        db.session.flush()
        trusted = DashboardSnapshot(
            snapshot_type='bullpen_dashboard', sync_run_id=prior_run.id,
            status=dashboard_snapshot.SNAPSHOT_STATUS_READY, is_published=True,
            published_at=_dt(2026, 9, 24, 6, 3), payload={'trusted': True},
            payload_version=1, data_through=_SEP_24 - timedelta(days=1),
            snapshot_generated_at=_dt(2026, 9, 24, 6, 2), source='scheduled_sync',
        )
        db.session.add(trusted)
        run = SyncRun(job_name='daily_sync', status='running', stage='started',
                      source='scheduled')
        db.session.add(run)
        db.session.commit()
        trusted_id, run_id = trusted.id, run.id

        # MLB now reports every game Final; the real Daily preflight and slate
        # refresh run exactly as in the Sep. 25 Daily Primary.
        source['games'] = final_games
        preflight = sync_service._refresh_daily_schedule_finality_window(_SEP_25, 7)
        slate = sync_service._refresh_daily_slate_schedule_window(_SEP_25)
        assert preflight['status'] == 'ok' and slate['status'] == 'ok'

        # Postgame markers are not written yet, so the real slate gate still
        # withholds this candidate for a genuine reason.
        monkeypatch.setattr(bullpen_api, 'build_bullpen_dashboard_payload',
                            lambda *_a, **_k: {'freshness': {
                                'data_through': _SEP_24.isoformat(),
                                'availability_reference_date': _SEP_25.isoformat()}})
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld) as withheld:
            sync_service.complete_sync_run_with_snapshot(
                run_id, final_status='success', source='scheduled',
                snapshot_source='scheduled_sync',
            )
        assert str(withheld.value) == dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
        candidate_id = withheld.value.snapshot_id
        db.session.remove()

    url = os.environ['DATABASE_URL']
    scheduled = _fresh_rows(url, 'scheduled_games', 'status_state', _ADOPTED_FINAL_PKS)
    assert len(scheduled) == 6
    assert {row[1] for row in scheduled} == {ScheduledGame.STATE_FINAL}
    slate_rows = _fresh_rows(url, 'slate_games', 'normalized_state', _ADOPTED_FINAL_PKS)
    assert {row[1] for row in slate_rows} == {'completed'}

    with fenced_app.app_context():
        assert db.session.get(DashboardSnapshot, trusted_id).is_published is True
        candidate = db.session.get(DashboardSnapshot, candidate_id)
        assert candidate.is_published is False
        coverage = candidate.payload['freshness']['slate_coverage']
        assert 'scheduled_games_not_final' not in coverage['reason_codes']
        assert 'postgame_markers_incomplete' in coverage['reason_codes']
        failed = db.session.get(SyncRun, run_id)
        assert failed.status == 'failed'
        assert failed.published_dashboard_snapshot_id is None
        assert db.session.execute(text(
            'SELECT count(*) FROM tonight_publications WHERE dashboard_snapshot_id=:id'
        ), {'id': candidate_id}).scalar() == 0

        # Once every final game is fully ingested, the real evaluator clears.
        for index, pk in enumerate(_ADOPTED_FINAL_PKS):
            db.session.add(PostgameProcessedGame(
                mlb_game_pk=pk, game_date=_SEP_24, game_type='R',
                home_team_id=108 + 2 * index, away_team_id=109 + 2 * index,
                processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
                processed_at=_dt(2026, 9, 25, 4, 0),
            ))
        db.session.commit()
        after = slate_coverage.compute_slate_coverage(_SEP_24)
        assert after['validations_passed'] is True
        assert after['complete_enough_to_publish'] is True
        assert after['reason_codes'] == ['slate_complete']
