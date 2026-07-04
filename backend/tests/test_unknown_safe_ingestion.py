from datetime import date

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.mlb_api import mlb_client
from utils.db import db


def _status(status_code, detailed_state, abstract_state):
    return {
        'statusCode': status_code,
        'detailedState': detailed_state,
        'abstractGameState': abstract_state,
    }


def _split(pk, *, game_status=None, pitches=12, game_date=date(2026, 6, 10),
           stat_overrides=None, missing=()):
    stat = {
        'inningsPitched': '1.0',
        'strikes': 8,
    }
    if pitches != 'missing':
        stat['numberOfPitches'] = pitches
    stat.update(stat_overrides or {})
    for key in missing:
        stat.pop(key, None)
    return {
        'game': {
            'gamePk': pk,
            'gameType': 'R',
            'status': game_status or _status('F', 'Final', 'Final'),
        },
        'date': game_date.isoformat(),
        'opponent': {'id': 2, 'name': 'Opp'},
        'stat': stat,
    }


def _game(game_pk=4001):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-10',
        'status': _status('F', 'Final', 'Final'),
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Unknown Club'}},
            'away': {'team': {'id': 2, 'name': 'Opp'}},
        },
    }


def _boxscore(stat):
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Unknown Club'},
                'pitchers': [100],
                'players': {
                    'ID100': {
                        'person': {'id': 100, 'fullName': 'Unknown Safe Reliever'},
                        'stats': {'pitching': stat},
                    },
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Opp'},
                'pitchers': [],
                'players': {},
            },
        },
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(mlb_client, 'get_game_pitching_lines', lambda game_pk: [])
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        pitcher = Pitcher(
            mlb_id=100,
            full_name='Unknown Safe Reliever',
            team_id=1,
            team_abbreviation='UNK',
            active=True,
        )
        db.session.add(pitcher)
        db.session.commit()
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_missing_zero_and_positive_pitch_counts_remain_distinct(app, monkeypatch):
    splits = [
        _split(1001, pitches='missing'),
        _split(1002, pitches=0),
        _split(1003, pitches=27),
    ]
    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: splits)

    with app.app_context():
        result = sync_service.sync_recent_logs(days_back=7, reference_date=date(2026, 6, 10))
        logs = {
            log.mlb_game_pk: log
            for log in GameLog.query.order_by(GameLog.mlb_game_pk).all()
        }

    assert result['new_logs_added'] == 3
    assert logs[1001].pitches_thrown is None
    assert logs[1001].to_dict()['pitches_thrown'] is None
    assert logs[1002].pitches_thrown == 0
    assert logs[1002].to_dict()['pitches_thrown'] == 0
    assert logs[1003].pitches_thrown == 27
    assert logs[1003].to_dict()['pitches_thrown'] == 27


def test_daily_boxscore_expansion_fields_are_unknown_safe(app, monkeypatch):
    splits = [
        _split(1101),
        _split(1102, stat_overrides={
            'battersFaced': 0,
            'balls': 0,
            'gamesFinished': 0,
            'inheritedRunners': 0,
            'inheritedRunnersScored': 0,
        }),
        _split(1103, stat_overrides={
            'battersFaced': 4,
            'balls': 7,
            'gamesFinished': 1,
            'inheritedRunners': 2,
            'inheritedRunnersScored': 1,
        }),
        _split(1104, stat_overrides={
            'battersFaced': 'not-a-number',
            'balls': '',
            'gamesFinished': None,
            'inheritedRunners': 'x',
            'inheritedRunnersScored': '',
        }),
    ]
    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: splits)

    with app.app_context():
        result = sync_service.sync_recent_logs(days_back=7, reference_date=date(2026, 6, 10))
        logs = {
            log.mlb_game_pk: log
            for log in GameLog.query.order_by(GameLog.mlb_game_pk).all()
        }

    assert result['new_logs_added'] == 4
    for field in (
        'batters_faced',
        'balls',
        'games_finished',
        'inherited_runners',
        'inherited_runners_scored',
    ):
        assert getattr(logs[1101], field) is None
        assert getattr(logs[1102], field) == 0
        assert getattr(logs[1104], field) is None
    assert logs[1103].batters_faced == 4
    assert logs[1103].balls == 7
    assert logs[1103].games_finished == 1
    assert logs[1103].inherited_runners == 2
    assert logs[1103].inherited_runners_scored == 1


def test_postgame_boxscore_expansion_fields_are_unknown_safe(app, monkeypatch):
    stats = {
        'inningsPitched': '1.0',
        'numberOfPitches': 12,
        'strikes': 8,
        'battersFaced': 0,
        'balls': 0,
        'gamesFinished': 0,
        'inheritedRunners': 0,
        'inheritedRunnersScored': 0,
    }
    monkeypatch.setattr(mlb_client, 'get_game_boxscore', lambda game_pk: _boxscore(stats))
    monkeypatch.setattr(mlb_client, 'get_game_play_by_play', lambda game_pk: {})

    with app.app_context():
        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(4001),
            schedule_date=date(2026, 6, 10),
        )
        db.session.commit()
        log = GameLog.query.filter_by(mlb_game_pk=4001).one()

    assert result['logs_added'] == 1
    assert log.batters_faced == 0
    assert log.balls == 0
    assert log.games_finished == 0
    assert log.inherited_runners == 0
    assert log.inherited_runners_scored == 0


def test_new_boxscore_fields_do_not_enter_public_game_log_serialization(app, monkeypatch):
    splits = [_split(1201, stat_overrides={'battersFaced': 4, 'balls': 6})]
    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: splits)

    with app.app_context():
        sync_service.sync_recent_logs(days_back=7, reference_date=date(2026, 6, 10))
        payload = GameLog.query.filter_by(mlb_game_pk=1201).one().to_dict()

    for field in (
        'batters_faced',
        'balls',
        'games_finished',
        'inherited_runners',
        'inherited_runners_scored',
    ):
        assert field not in payload


@pytest.mark.parametrize(
    ('game_status', 'game_pk'),
    [
        (_status('I', 'In Progress', 'Live'), 2001),
        (_status('P', 'Scheduled', 'Preview'), 2002),
        (_status('S', 'Suspended', 'Live'), 2003),
        (_status('DR', 'Postponed', 'Preview'), 2004),
    ],
)
def test_daily_ingestion_excludes_non_final_game_splits(app, monkeypatch, game_status, game_pk):
    splits = [
        _split(1999, game_status=_status('F', 'Final', 'Final')),
        _split(game_pk, game_status=game_status),
    ]
    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: splits)

    with app.app_context():
        result = sync_service.sync_recent_logs(days_back=7, reference_date=date(2026, 6, 10))
        game_pks = [row.mlb_game_pk for row in GameLog.query.order_by(GameLog.mlb_game_pk).all()]

    assert result['new_logs_added'] == 1
    assert game_pks == [1999]


def test_daily_ingestion_excludes_ambiguous_statusless_split(app, monkeypatch):
    splits = [_split(3001) | {'game': {'gamePk': 3001, 'gameType': 'R'}}]
    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: splits)

    with app.app_context():
        result = sync_service.sync_recent_logs(days_back=7, reference_date=date(2026, 6, 10))

    assert result['new_logs_added'] == 0
    assert GameLog.query.count() == 0
