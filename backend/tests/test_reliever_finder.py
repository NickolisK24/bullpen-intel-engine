from datetime import date, timedelta

import pytest
from flask import Flask

import api.bullpen as bullpen_api
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.reliever_finder import FINDER_MAX_LIMIT
from services.roster_status import STATUS_ACTIVE
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def client():
    app = Flask('test_reliever_finder')
    configure_test_database(app)
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_reliever(*, mlb_id, name, team_id, team_name, team_abbreviation, pitches=18):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        position='P',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.flush()
    for index in range(3):
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=mlb_id * 10 + index,
            game_date=date.today() - timedelta(days=index + 1),
            games_started=0,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            pitches_thrown=pitches,
            game_type='R',
        ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=30.0,
        pitches_last_7_days=pitches * 3,
        appearances_last_7=3,
        appearances_last_14=3,
        days_since_last_appearance=1,
        innings_last_7_days=3.0,
        risk_level='MODERATE',
    ))
    db.session.commit()
    return pitcher


def _seed_population():
    specs = (
        (9101, 'Alex Rivera', 111, 'Boston Red Sox', 'BOS', 12),
        (9102, 'Ben Rivera', 147, 'New York Yankees', 'NYY', 20),
        (9103, 'Carlos Estevez', 111, 'Boston Red Sox', 'BOS', 16),
        (9104, 'Drew Smith', 121, 'New York Mets', 'NYM', 24),
        (9105, 'Emilio Pagan', 142, 'Minnesota Twins', 'MIN', 10),
    )
    return [
        _seed_reliever(
            mlb_id=mlb_id,
            name=name,
            team_id=team_id,
            team_name=team_name,
            team_abbreviation=abbr,
            pitches=pitches,
        )
        for mlb_id, name, team_id, team_name, abbr, pitches in specs
    ]


def test_no_intent_returns_lightweight_contract_without_running_finder_query(client, monkeypatch):
    monkeypatch.setattr(
        bullpen_api,
        'build_reliever_finder_payload',
        lambda **_kwargs: pytest.fail('neutral Finder must not execute the result query'),
    )
    monkeypatch.setattr(
        bullpen_api,
        '_board_freshness_block',
        lambda: pytest.fail('neutral Finder must not inspect publication freshness'),
    )

    response = client.get('/api/bullpen/reliever-finder')

    assert response.status_code == 200
    body = response.get_json()
    assert body['status'] == 'awaiting_intent'
    assert body['data'] == []
    assert body['meta']['query_executed'] is False
    assert body['meta']['total_results'] is None


def test_partial_name_query_returns_compact_backend_owned_rows(client):
    with client.application.app_context():
        pitchers = _seed_population()
        pitcher_ids = {pitchers[0].id, pitchers[1].id}

    response = client.get('/api/bullpen/reliever-finder?q=river&limit=10')

    assert response.status_code == 200
    body = response.get_json()
    assert [row['pitcher']['full_name'] for row in body['data']] == [
        'Alex Rivera', 'Ben Rivera',
    ]
    assert {row['pitcher']['id'] for row in body['data']} == pitcher_ids
    for row in body['data']:
        assert row['destination'] == f"/pitcher/{row['pitcher']['id']}"
        assert row['availability']['availability_public_label'] in {
            'Available', 'On Watch', 'Limited', 'Unavailable',
        }
        for forbidden in ('raw_score', 'risk_level', 'fatigue_score'):
            assert forbidden not in row

    partial_first = client.get('/api/bullpen/reliever-finder?q=ale').get_json()
    assert [row['pitcher']['full_name'] for row in partial_first['data']] == ['Alex Rivera']


def test_team_intent_is_sufficient_and_team_authority_is_preserved(client):
    with client.application.app_context():
        _seed_population()

    body = client.get('/api/bullpen/reliever-finder?team_id=111').get_json()

    assert body['status'] == 'available'
    assert {row['pitcher']['full_name'] for row in body['data']} == {
        'Alex Rivera', 'Carlos Estevez',
    }
    assert {row['pitcher']['team_id'] for row in body['data']} == {111}


def test_public_availability_filter_is_applied_by_backend(client):
    with client.application.app_context():
        _seed_population()

    all_rows = client.get('/api/bullpen/reliever-finder?q=ri&limit=50').get_json()['data']
    label = all_rows[0]['availability']['availability_public_label']
    body = client.get('/api/bullpen/reliever-finder', query_string={
        'availability': label,
        'limit': 50,
    }).get_json()

    assert body['meta']['filters']['availability'] == label
    assert body['data']
    assert all(
        row['availability']['availability_public_label'] == label
        for row in body['data']
    )


def test_limit_is_clamped_to_strict_finder_ceiling(client, monkeypatch):
    captured = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return {'status': 'empty', 'data': [], 'meta': {}}

    monkeypatch.setattr(bullpen_api, 'build_reliever_finder_payload', fake_builder)
    response = client.get('/api/bullpen/reliever-finder?q=rivera&limit=750')

    assert response.status_code == 200
    assert captured['limit'] == FINDER_MAX_LIMIT == 50


def test_pagination_and_supported_sorts_are_deterministic(client):
    with client.application.app_context():
        _seed_population()

    first = client.get('/api/bullpen/reliever-finder?q=new&limit=1&page=1&sort=name').get_json()
    second = client.get('/api/bullpen/reliever-finder?q=new&limit=1&page=2&sort=name').get_json()

    assert first['meta']['total_results'] == 2
    assert first['meta']['total_pages'] == 2
    assert first['meta']['has_more'] is True
    assert first['meta']['next_page'] == 2
    assert second['meta']['has_more'] is False
    assert first['data'][0]['pitcher']['id'] != second['data'][0]['pitcher']['id']

    pitches = client.get('/api/bullpen/reliever-finder?q=river&sort=pitches').get_json()
    assert [row['pitcher']['full_name'] for row in pitches['data']] == [
        'Ben Rivera', 'Alex Rivera',
    ]


@pytest.mark.parametrize('query_string, parameter', [
    ({'q': 'rivera', 'sort': 'score'}, 'sort'),
    ({'availability': 'Avoid'}, 'availability'),
    ({'team_id': -1}, 'team_id'),
    ({'q': 'rivera', 'page': 0}, 'page'),
])
def test_invalid_finder_parameters_fail_closed(client, query_string, parameter):
    response = client.get('/api/bullpen/reliever-finder', query_string=query_string)

    assert response.status_code == 400
    body = response.get_json()
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == parameter


def test_no_match_is_an_honest_empty_result(client):
    with client.application.app_context():
        _seed_population()

    body = client.get('/api/bullpen/reliever-finder?q=zzzz-no-match').get_json()

    assert body['status'] == 'empty'
    assert body['data'] == []
    assert body['meta']['query_executed'] is True
    assert body['meta']['total_results'] == 0


def test_legacy_bulk_fatigue_endpoint_remains_compatible(client):
    with client.application.app_context():
        _seed_population()

    response = client.get('/api/bullpen/fatigue?limit=750&with_meta=true')

    assert response.status_code == 200
    body = response.get_json()
    assert isinstance(body['data'], list)
    assert body['meta']['returned_pitchers'] == len(body['data'])
