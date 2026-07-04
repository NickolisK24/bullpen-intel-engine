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
