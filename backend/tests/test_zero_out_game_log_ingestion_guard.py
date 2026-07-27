"""Source guard for zero-out gameLog listings not proven by a final box score."""

from datetime import date, timedelta

import pytest
from flask import Flask

import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 6, 23)
GAME_PK = 824262
HOME_TEAM = 116
AWAY_TEAM = 147
TARGET_MLB_ID = 445276


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _pitcher():
    pitcher = Pitcher(
        mlb_id=TARGET_MLB_ID,
        full_name='Kenley Jansen',
        team_id=999,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _schedule():
    db.session.add_all([
        ScheduledGame(
            team_id=HOME_TEAM,
            game_pk=GAME_PK,
            game_date=GAME_DATE,
            status_state='final',
            home_away='home',
            opponent_team_id=AWAY_TEAM,
        ),
        ScheduledGame(
            team_id=AWAY_TEAM,
            game_pk=GAME_PK,
            game_date=GAME_DATE,
            status_state='final',
            home_away='away',
            opponent_team_id=HOME_TEAM,
        ),
    ])
    db.session.commit()


def _complete_zero_split():
    return {
        'game': {'gamePk': GAME_PK, 'gameType': 'R'},
        'date': GAME_DATE.isoformat(),
        'opponent': {'id': AWAY_TEAM, 'name': 'New York Yankees'},
        'stat': {
            'inningsPitched': '0.0',
            'numberOfPitches': '0',
            'strikes': '0',
            'hits': '0',
            'runs': '0',
            'earnedRuns': '0',
            'baseOnBalls': '0',
            'strikeOuts': '0',
            'homeRuns': '0',
            'gamesStarted': '0',
            'battersFaced': '0',
            'balls': '0',
            'gamesFinished': '0',
            'inheritedRunners': '0',
            'inheritedRunnersScored': '0',
            'saveOpportunities': '0',
            'holds': '0',
            'blownSaves': '0',
            'wins': '0',
            'losses': '0',
            'saves': '0',
        },
    }


def _boxscore_with_zero_out_line():
    stats = dict(_complete_zero_split()['stat'])
    return {
        'teams': {
            'home': {
                'team': {'id': HOME_TEAM, 'name': 'Detroit Tigers'},
                'pitchers': [TARGET_MLB_ID],
                'players': {
                    f'ID{TARGET_MLB_ID}': {
                        'person': {'id': TARGET_MLB_ID, 'fullName': 'Kenley Jansen'},
                        'stats': {'pitching': stats},
                    },
                },
            },
            'away': {
                'team': {'id': AWAY_TEAM, 'name': 'New York Yankees'},
                'pitchers': [607074],
                'players': {
                    'ID607074': {
                        'person': {'id': 607074, 'fullName': 'Carlos Rodón'},
                        'stats': {'pitching': {
                            'inningsPitched': '6.0',
                            'numberOfPitches': '90',
                            'strikes': '60',
                            'hits': '4',
                            'runs': '1',
                            'earnedRuns': '1',
                            'baseOnBalls': '1',
                            'strikeOuts': '7',
                            'homeRuns': '0',
                            'gamesStarted': '1',
                        }},
                    },
                },
            },
        },
    }


def test_new_schedule_only_zero_out_listing_fails_before_insert(app):
    _schedule()
    pitcher = _pitcher()

    with pytest.raises(ata.UnverifiedZeroOutAppearance) as exc:
        sync_service._ingest_game_log_split(
            pitcher,
            _complete_zero_split(),
            GAME_DATE - timedelta(days=5),
            {},
        )

    assert exc.value.reason_code == ata.REASON_ZERO_OUT_UNVERIFIED
    assert GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=GAME_PK,
    ).count() == 0


def test_official_boxscore_zero_out_line_remains_a_valid_appearance(app):
    _schedule()
    pitcher = _pitcher()
    boxscore = _boxscore_with_zero_out_line()
    line = next(
        item for item in sync_service._extract_pitching_lines_from_boxscore(boxscore)
        if item['player_id'] == TARGET_MLB_ID
    )

    result = sync_service._ingest_boxscore_pitching_line(
        pitcher,
        line,
        {
            'gamePk': GAME_PK,
            'gameType': 'R',
            'officialDate': GAME_DATE.isoformat(),
            'teams': {
                'home': {'team': {'id': HOME_TEAM, 'name': 'Detroit Tigers'}},
                'away': {'team': {'id': AWAY_TEAM, 'name': 'New York Yankees'}},
            },
        },
        game_date=GAME_DATE,
        team_abbr_map={},
        pitcher_order=sync_service._pitcher_order_by_side(boxscore),
    )
    db.session.commit()

    assert result['status'] == 'inserted'
    stored = GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=GAME_PK,
    ).one()
    assert stored.innings_pitched_outs == 0
    assert stored.appearance_team_status == ata.STATUS_RESOLVED
    assert stored.appearance_team_source == ata.SOURCE_BOXSCORE
    assert stored.appearance_team_id == HOME_TEAM


def test_daily_zero_out_reread_is_allowed_after_official_row_exists(app):
    _schedule()
    pitcher = _pitcher()
    official_resolution = ata.resolve_for_write(
        boxscore_team_id=HOME_TEAM,
        game_pk=GAME_PK,
        opponent_team_id=AWAY_TEAM,
    )
    values = sync_service._game_log_values_from_stats(
        stats=_complete_zero_split()['stat'],
        pitcher=pitcher,
        game_pk=GAME_PK,
        game_date=GAME_DATE,
        game_type='R',
        opponent='New York Yankees',
        opponent_abbreviation='NYY',
        games_started=0,
        appearance_team=official_resolution,
    )
    db.session.add(GameLog(**values))
    db.session.commit()

    result = sync_service._ingest_game_log_split(
        pitcher,
        _complete_zero_split(),
        GAME_DATE - timedelta(days=5),
        {},
    )
    db.session.commit()

    assert result['status'] == 'unchanged'
    assert GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=GAME_PK,
    ).count() == 1


def test_nonzero_daily_appearance_is_unchanged_by_guard(app):
    _schedule()
    pitcher = _pitcher()
    split = _complete_zero_split()
    split['stat']['inningsPitched'] = '1.0'
    split['stat']['numberOfPitches'] = '12'
    split['stat']['strikes'] = '8'
    split['stat']['strikeOuts'] = '1'

    result = sync_service._ingest_game_log_split(
        pitcher,
        split,
        GAME_DATE - timedelta(days=5),
        {},
    )
    db.session.commit()

    assert result['status'] == 'inserted'
    assert GameLog.query.filter_by(
        pitcher_id=pitcher.id,
        mlb_game_pk=GAME_PK,
    ).one().innings_pitched_outs == 3


def test_zero_out_guard_never_reads_current_team_as_authority():
    source = Path(__file__).resolve().parents[2] / 'backend' / 'services' / 'appearance_team_authority.py'
    text = source.read_text(encoding='utf-8').lower()
    assert 'pitcher.team_id' not in text
