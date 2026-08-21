from datetime import date, timedelta

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services.public_team_performance import (
    ADDITIONAL_METRICS_LIMITATION,
    CONTRACT_VERSION,
    POPULATION_BASIS,
    build_public_team_performance_payload,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


TEAM_ID = 113
OTHER_TEAM_ID = 158
THROUGH = date(2026, 8, 20)


@pytest.fixture()
def app():
    application = Flask('test_public_team_performance')
    configure_test_database(application)
    db.init_app(application)
    with application.app_context():
        create_test_schema(application)
        try:
            yield application
        finally:
            db.session.remove()
            drop_test_schema(application)


def _pitcher(name, mlb_id):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=TEAM_ID,
        team_name='Cincinnati Reds',
        team_abbreviation='CIN',
        active=True,
        roster_status='Active',
        position='P',
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _log(pitcher, index, *, outs=3, earned_runs=0, games_started=0,
         appearance_team_id=TEAM_ID, hits=0, walks=0, strikeouts=0,
         home_runs=0, batters_faced=None):
    game_pk = 990000 + index
    game_date = THROUGH - timedelta(days=index % 120)
    opponent_id = OTHER_TEAM_ID if appearance_team_id == TEAM_ID else TEAM_ID
    for team_id in (appearance_team_id, opponent_id):
        db.session.add(ScheduledGame(
            team_id=team_id,
            game_pk=game_pk,
            game_date=game_date,
            game_type='R',
            status_code='F',
            status_state=ScheduledGame.STATE_FINAL,
        ))
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        games_started=games_started,
        innings_pitched=outs / 3,
        innings_pitched_outs=outs,
        earned_runs=earned_runs,
        runs_allowed=earned_runs,
        hits_allowed=hits,
        walks=walks,
        strikeouts=strikeouts,
        home_runs_allowed=home_runs,
        batters_faced=batters_faced,
        appearance_team_id=appearance_team_id,
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_source='boxscore_side',
        appearance_team_reason='appearance_team_resolved_boxscore',
    ))


def _card(pitcher, *, visible=True):
    return {
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'name': pitcher.full_name,
        'visibility': {'is_visible_by_default': visible},
    }


def _board(cards):
    return {
        'team': {'team_id': TEAM_ID, 'team_name': 'Cincinnati Reds'},
        'team_state': {'data_through': THROUGH.isoformat()},
        'freshness': {
            'data_through': THROUGH.isoformat(),
            'freshness_state': 'current',
            'fail_closed': False,
        },
        'groups': [{'pitchers': cards}],
    }


def test_public_read_uses_represented_active_group_and_team_owned_relief_only(app):
    active = _pitcher('Active Arm', 700001)
    former = _pitcher('Off Active Arm', 700002)
    for index in range(36):
        _log(active, index, earned_runs=1 if index < 12 else 0)
    _log(active, 100, outs=12, earned_runs=10, games_started=1)
    _log(active, 101, outs=12, earned_runs=10, appearance_team_id=OTHER_TEAM_ID)
    _log(former, 102, outs=27, earned_runs=20)
    db.session.commit()

    payload = build_public_team_performance_payload(
        TEAM_ID,
        board=_board([_card(active), _card(former, visible=False)]),
    )

    assert payload['contract_version'] == CONTRACT_VERSION
    assert payload['population_basis'] == POPULATION_BASIS
    assert payload['active_pitcher_count'] == 1
    assert payload['pitchers_with_sample'] == 1
    assert payload['relief_appearances'] == 36
    assert payload['innings_pitched'] == '36.0'
    assert payload['metrics'][0]['value'] == '3.00'
    assert payload['sample']['recorded_outs'] == 108
    assert payload['sample']['meets_minimum'] is True
    assert payload['status'] == 'partial'
    assert payload['limitations'] == [ADDITIONAL_METRICS_LIMITATION]
    assert payload['evidence']['official_record']['appearance_count'] == 36


def test_below_sample_is_partial_and_never_exposes_the_internal_value(app):
    active = _pitcher('Thin Sample Arm', 700003)
    _log(active, 201, outs=27, earned_runs=4)
    db.session.commit()

    payload = build_public_team_performance_payload(
        TEAM_ID, board=_board([_card(active)]),
    )

    assert payload['status'] == 'partial'
    assert payload['summary'] == 'Not Enough Innings Yet'
    assert payload['metrics'][0]['value'] is None
    assert payload['sample']['recorded_outs'] == 27
    assert payload['sample']['minimum_recorded_outs'] == 108
    assert payload['sample']['meets_minimum'] is False


def test_empty_and_zero_out_samples_fail_closed(app):
    empty = _pitcher('No Sample Arm', 700004)
    zero = _pitcher('Zero Out Arm', 700005)
    _log(zero, 301, outs=0, earned_runs=1)
    db.session.commit()

    empty_payload = build_public_team_performance_payload(
        TEAM_ID, board=_board([_card(empty)]),
    )
    zero_payload = build_public_team_performance_payload(
        TEAM_ID, board=_board([_card(zero)]),
    )

    assert empty_payload['status'] == 'unavailable'
    assert empty_payload['metrics'][0]['value'] is None
    assert zero_payload['status'] == 'unavailable'
    assert zero_payload['metrics'][0]['value'] is None
    assert zero_payload['reason_code'] == 'era_denominator_zero'


def test_missing_optional_domains_never_become_fabricated_zero_metrics(app):
    active = _pitcher('Optional Data Arm', 700006)
    for index in range(36):
        _log(active, 400 + index, batters_faced=None)
    db.session.commit()

    payload = build_public_team_performance_payload(
        TEAM_ID, board=_board([_card(active)]),
    )

    assert payload['metrics'] == [{
        'key': 'active_bullpen_era',
        'metric_id': 'M-001',
        'label': 'Active Bullpen ERA',
        'value': '0.00',
        'method_version': '1.1.0',
    }]
    assert payload['status'] == 'partial'
    assert 'WHIP' in payload['limitations'][0]
    assert 'inherited-runner' in payload['limitations'][0]
