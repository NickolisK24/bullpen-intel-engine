from datetime import date, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
from api.pitchers import pitchers_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.pitcher_search import (
    TEAM_ASSIGNMENT_ASSIGNED,
    TEAM_ASSIGNMENT_NO_ORGANIZATION,
    TEAM_ASSIGNMENT_UNKNOWN,
)
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(pitchers_bp, url_prefix='/api/pitchers')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def seed_pitcher(
    name,
    mlb_id,
    team_id=139,
    team_name='Tampa Bay Rays',
    team_abbreviation='TB',
    position='P',
    roster_status=STATUS_ACTIVE,
    team_assignment_status=TEAM_ASSIGNMENT_ASSIGNED,
    raw_score=12.0,
    risk_level='LOW',
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        team_assignment_status=team_assignment_status,
        team_assignment_source='test_fixture',
        team_assignment_updated_at=utc_now_naive(),
        position=position,
        active=True,
        roster_status=roster_status,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=date.today() - timedelta(days=3),
        pitches_thrown=8,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        pitch_count_score=10.0,
        rest_days_score=10.0,
        appearances_score=10.0,
        innings_score=10.0,
        days_since_last_appearance=3,
        appearances_last_7=1,
        appearances_last_14=1,
        pitches_last_7_days=8,
        innings_last_7_days=1.0,
        risk_level=risk_level,
    ))
    db.session.commit()
    return pitcher


def search(client, query):
    return client.get('/api/pitchers/search', query_string={'q': query}).get_json()


def test_pitcher_search_exact_full_name_orders_exact_match_first(client):
    with client.application.app_context():
        exact = seed_pitcher('Craig Kimbrel', 518886)
        exact_id = exact.id
        seed_pitcher('Craig Kimbrelson', 999001)

    payload = search(client, 'Craig Kimbrel')

    assert payload['query'] == 'Craig Kimbrel'
    assert payload['results'][0]['player_id'] == exact_id
    assert payload['results'][0]['player_name'] == 'Craig Kimbrel'


def test_pitcher_search_partial_last_name(client):
    with client.application.app_context():
        richards = seed_pitcher(
            'Trevor Richards',
            670950,
            team_id=142,
            team_name='Minnesota Twins',
            team_abbreviation='MIN',
        )
        richards_id = richards.id

    payload = search(client, 'rich')

    assert [result['player_id'] for result in payload['results']] == [richards_id]
    assert payload['results'][0]['team_name'] == 'Minnesota Twins'


def test_pitcher_search_prefix_match(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Trevor Richards', 670950)
        pitcher_id = pitcher.id

    payload = search(client, 'tre')

    assert payload['results'][0]['player_id'] == pitcher_id


def test_pitcher_search_case_and_accent_insensitive(client):
    with client.application.app_context():
        pagan = seed_pitcher('Emilio Pagan', 641941)
        pagan_id = pagan.id

    payload = search(client, 'PAGÁN')

    assert payload['results'][0]['player_id'] == pagan_id
    assert payload['results'][0]['player_name'] == 'Emilio Pagan'


def test_pitcher_search_empty_and_too_short_queries_return_no_results(client):
    with client.application.app_context():
        seed_pitcher('Craig Kimbrel', 518886)

    empty = search(client, '')
    too_short = search(client, 'k')

    assert empty['results'] == []
    assert too_short['results'] == []
    assert empty['min_query_length'] == 2
    assert too_short['min_query_length'] == 2


def test_pitcher_search_returns_current_team_roster_status_and_final_availability(client):
    with client.application.app_context():
        seed_pitcher('Craig Kimbrel', 518886)

    result = search(client, 'kimbrel')['results'][0]

    assert result['team_id'] == 139
    assert result['team_name'] == 'Tampa Bay Rays'
    assert result['roster_status'] == 'ACTIVE'
    assert result['availability'] == 'Available'
    assert result['position'] == 'P'


def test_pitcher_search_does_not_leak_workload_available_for_unavailable_status(client):
    with client.application.app_context():
        seed_pitcher(
            'Pierce Johnson',
            572955,
            roster_status=STATUS_IL_15,
            raw_score=12.0,
        )

    result = search(client, 'johnson')['results'][0]

    assert result['roster_status'] == 'IL_15'
    assert result['availability'] == 'Unavailable'


def test_pitcher_search_ordering_exact_prefix_contains_then_name(client):
    with client.application.app_context():
        seed_pitcher('Abe McKimbrel', 999101)
        seed_pitcher('Craig Kimbrel', 518886)
        seed_pitcher('Kimbrel Adams', 999102)

    payload = search(client, 'kimbrel')
    names = [result['player_name'] for result in payload['results']]

    assert names == ['Craig Kimbrel', 'Kimbrel Adams', 'Abe McKimbrel']


def test_pitcher_search_no_organization_clears_stale_team_fields(client):
    with client.application.app_context():
        seed_pitcher(
            'Released Pitcher',
            999201,
            team_id=113,
            team_name='Cincinnati Reds',
            team_abbreviation='CIN',
            roster_status=STATUS_ACTIVE,
            team_assignment_status=TEAM_ASSIGNMENT_NO_ORGANIZATION,
            raw_score=12.0,
        )

    result = search(client, 'released')['results'][0]

    assert result['team_id'] is None
    assert result['team_name'] is None
    assert result['availability'] == 'Unavailable'


@pytest.mark.parametrize('assignment_status', [None, TEAM_ASSIGNMENT_UNKNOWN])
def test_pitcher_search_unresolved_team_assignment_does_not_emit_stale_team(client, assignment_status):
    with client.application.app_context():
        seed_pitcher(
            'Unresolved Pitcher',
            999202,
            team_id=113,
            team_name='Cincinnati Reds',
            team_abbreviation='CIN',
            roster_status=STATUS_ACTIVE,
            team_assignment_status=assignment_status,
            raw_score=12.0,
        )

    result = search(client, 'unresolved')['results'][0]

    assert result['team_id'] is None
    assert result['team_name'] is None
    expected_roster_status = 'UNKNOWN' if assignment_status == TEAM_ASSIGNMENT_UNKNOWN else 'ACTIVE'
    assert result['roster_status'] == expected_roster_status
    assert result['availability'] == 'Unavailable'
