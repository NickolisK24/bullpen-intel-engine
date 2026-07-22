from datetime import date, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401  (register on db.metadata)
from api.bullpen import ACTIVE_WINDOW_DAYS, bullpen_bp
from utils.time import utc_now_naive


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _add_scored_pitcher(days_since_last_game, team_id=1, risk_level='HIGH', raw_score=72.0):
    pitcher = Pitcher(
        mlb_id=1000 + days_since_last_game + team_id,
        full_name=f'Pitcher {days_since_last_game}',
        team_id=team_id,
        team_name='Test Club',
        team_abbreviation='TST',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()

    game_date = date.today() - timedelta(days=days_since_last_game)
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=2000 + days_since_last_game + team_id,
        game_date=game_date,
        pitches_thrown=18,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        # Relief appearance (no start): keeps this scored pitcher inside the
        # reliever population the public fatigue list now filters to.
        games_started=0,
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        pitch_count_score=50.0,
        rest_days_score=30.0,
        appearances_score=20.0,
        innings_score=10.0,
        leverage_score=0.0,
        days_since_last_appearance=days_since_last_game,
        appearances_last_7=1,
        appearances_last_14=1,
        pitches_last_7_days=18,
        innings_last_7_days=1.0,
        risk_level=risk_level,
    ))
    db.session.commit()
    return pitcher


class TestBullpenFreshness:
    def test_legacy_fatigue_response_stays_array(self, client):
        with client.application.app_context():
            pitcher = _add_scored_pitcher(days_since_last_game=1)
            pitcher_id = pitcher.id

        res = client.get('/api/bullpen/fatigue?include_stale=false')

        assert res.status_code == 200
        body = res.get_json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]['pitcher_id'] == pitcher_id
        assert 'raw_score' in body[0]
        assert body[0]['availability']['availability_status'] in {
            'Available',
            'Monitor',
            'Limited',
            'Avoid',
            'Unavailable',
        }
        assert body[0]['availability']['confidence'] in {'high', 'medium', 'low'}
        assert isinstance(body[0]['availability']['reasons'], list)

    def test_metadata_explains_stale_filtered_empty_list(self, client):
        stale_days = ACTIVE_WINDOW_DAYS + 10
        with client.application.app_context():
            _add_scored_pitcher(days_since_last_game=stale_days)

        current = client.get('/api/bullpen/fatigue?limit=750&include_stale=false&with_meta=true')
        inclusive = client.get('/api/bullpen/fatigue?limit=750&include_stale=true&with_meta=true')

        assert current.status_code == 200
        body = current.get_json()
        assert body['data'] == []
        assert body['meta']['total_game_logs'] == 1
        assert body['meta']['total_scored_pitchers'] == 1
        assert body['meta']['filtered_scored_pitchers'] == 1
        assert body['meta']['fresh_filtered_pitchers'] == 0
        assert body['meta']['stale_filtered_pitchers'] == 1

        inclusive_body = inclusive.get_json()
        assert len(inclusive_body['data']) == 1
        assert inclusive_body['meta']['filtered_scored_pitchers'] == 1
        assert inclusive_body['meta']['fresh_filtered_pitchers'] == 0

    def test_dashboard_overview_counts_stale_scores(self, client):
        with client.application.app_context():
            _add_scored_pitcher(days_since_last_game=ACTIVE_WINDOW_DAYS + 10)

        res = client.get('/api/bullpen/stats/overview')

        assert res.status_code == 200
        body = res.get_json()
        assert body['total_pitchers'] == 1
        assert body['total_game_logs'] == 1
        assert body['scored_pitchers'] == 1
        assert body['risk_breakdown']['HIGH'] == 1
        assert 'availability_summary' not in body
        inventory = body['scored_pitcher_inventory']
        assert inventory['mode'] == 'scored_pitcher_inventory'
        assert inventory['is_current_availability'] is False
        assert inventory['total_pitchers'] == 1
        assert inventory['statuses']['Monitor'] == 1
        assert inventory['confidence']['low'] == 1
        assert inventory['data_state']['stale'] == 1
        assert any('inventory workload reads' in note.lower() for note in inventory['notes'])

    def test_detail_and_team_responses_include_availability(self, client):
        with client.application.app_context():
            pitcher = _add_scored_pitcher(days_since_last_game=1, team_id=7)
            pitcher_id = pitcher.id

        detail = client.get(f'/api/bullpen/fatigue/{pitcher_id}')
        team = client.get('/api/bullpen/teams/7/bullpen?include_stale=false')

        assert detail.status_code == 200
        detail_body = detail.get_json()
        assert detail_body['current_fatigue']['pitcher_id'] == pitcher_id
        assert detail_body['availability']['availability_status']
        assert isinstance(detail_body['availability']['reasons'], list)

        assert team.status_code == 200
        team_body = team.get_json()
        assert len(team_body) == 1
        assert team_body[0]['pitcher']['id'] == pitcher_id
        assert team_body[0]['fatigue']['pitcher_id'] == pitcher_id
        assert team_body[0]['availability']['availability_status']


def _seed_role_pitcher(mlb_id, name, log_specs, team_id=1, raw_score=40.0, base_offset=1):
    """Seed a scored pitcher with explicit per-appearance start/relief evidence.

    ``log_specs`` is a list of dicts: {'gs': games_started (or None), 'ip': innings,
    'save': bool, 'hold': bool}. The most recent appearance is base_offset days ago.
    """
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name='Test Club',
        team_abbreviation='TST',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()

    for index, spec in enumerate(log_specs):
        innings = spec.get('ip', 1.0)
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=mlb_id * 100 + index,
            game_date=date.today() - timedelta(days=base_offset + index),
            pitches_thrown=spec.get('pitches', 15),
            innings_pitched=innings,
            innings_pitched_outs=int(round(innings * 3)),
            games_started=spec.get('gs'),
            game_type='R',
            save=spec.get('save', False),
            hold=spec.get('hold', False),
        ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        pitches_last_7_days=spec_total_pitches(log_specs),
        appearances_last_7=len(log_specs),
        days_since_last_appearance=base_offset,
        risk_level='MODERATE',
    ))
    db.session.commit()
    return pitcher


def spec_total_pitches(log_specs):
    return sum(spec.get('pitches', 15) for spec in log_specs)


def _fatigue_pitcher_ids(client, query=''):
    res = client.get(f'/api/bullpen/fatigue?limit=750&include_stale=true&with_meta=true{query}')
    assert res.status_code == 200
    body = res.get_json()
    return body, {row['pitcher_id'] for row in body['data']}


class TestRelieverPopulationFilter:
    """The public All Pitchers list is a reliever finder: the shared Role
    Authority must exclude confirmed starters and fail closed on unknown role."""

    def test_confirmed_starter_excluded_reliever_and_swingman_included(self, client):
        with client.application.app_context():
            reliever = _seed_role_pitcher(
                501, 'Relief Only', [{'gs': 0}, {'gs': 0}, {'gs': 0}, {'gs': 0}])
            starter = _seed_role_pitcher(
                502, 'Rotation Arm',
                [{'gs': 1, 'ip': 6.0, 'pitches': 95}] * 4)
            swingman = _seed_role_pitcher(
                503, 'Swing Man',
                [{'gs': 1, 'ip': 5.0}, {'gs': 1, 'ip': 5.0}, {'gs': 0}, {'gs': 0}, {'gs': 0}])
            reliever_id, starter_id, swingman_id = reliever.id, starter.id, swingman.id

        body, ids = _fatigue_pitcher_ids(client)
        assert reliever_id in ids          # confirmed reliever
        assert swingman_id in ids          # ambiguous swingman included with caveat
        assert starter_id not in ids       # confirmed starter excluded
        # Displayed total reflects the filtered reliever population, not all scored.
        assert body['meta']['filtered_scored_pitchers'] == len(ids)
        assert body['meta']['returned_pitchers'] == len(ids)

    def test_unknown_role_fails_closed(self, client):
        with client.application.app_context():
            reliever = _seed_role_pitcher(511, 'Clear Reliever', [{'gs': 0}, {'gs': 0}])
            # Appearances on record but no start data and no save/hold relief
            # context → Unknown role, which must never be guessed into relief.
            unknown = _seed_role_pitcher(512, 'No Role Read', [{'gs': None}, {'gs': None}])
            reliever_id, unknown_id = reliever.id, unknown.id

        _body, ids = _fatigue_pitcher_ids(client)
        assert reliever_id in ids
        assert unknown_id not in ids

    def test_start_leaning_ambiguous_is_excluded(self, client):
        with client.application.app_context():
            # 3 of 5 known appearances are starts (start share 0.60) → start-leaning
            # ambiguous, which the role contract holds out of the bullpen population.
            start_leaning = _seed_role_pitcher(
                521, 'Mostly Starts',
                [{'gs': 1, 'ip': 5.0}, {'gs': 1, 'ip': 5.0}, {'gs': 1, 'ip': 5.0}, {'gs': 0}, {'gs': 0}])
            reliever = _seed_role_pitcher(522, 'Bullpen Arm', [{'gs': 0}, {'gs': 0}, {'gs': 0}])
            start_leaning_id, reliever_id = start_leaning.id, reliever.id

        _body, ids = _fatigue_pitcher_ids(client)
        assert reliever_id in ids
        assert start_leaning_id not in ids

    def test_opener_follows_existing_ambiguous_contract(self, client):
        with client.application.app_context():
            # Very short "starts" read as an opener → ambiguous (eligible) under the
            # existing role contract, so the opener is not treated as a rotation
            # starter and remains in the reliever finder.
            opener = _seed_role_pitcher(
                531, 'The Opener',
                [{'gs': 1, 'ip': 1.0}, {'gs': 1, 'ip': 1.0}, {'gs': 1, 'ip': 1.0}, {'gs': 1, 'ip': 1.0}])
            opener_id = opener.id

        _body, ids = _fatigue_pitcher_ids(client)
        assert opener_id in ids

    def test_role_change_in_stored_data_is_reflected(self, client):
        with client.application.app_context():
            # Starts only → classified as a starter and excluded.
            flipper = _seed_role_pitcher(
                541, 'Converted Arm',
                [{'gs': 1, 'ip': 6.0}, {'gs': 1, 'ip': 6.0}, {'gs': 1, 'ip': 6.0}, {'gs': 1, 'ip': 6.0}])
            flipper_id = flipper.id

        _body, ids_before = _fatigue_pitcher_ids(client)
        assert flipper_id not in ids_before

        with client.application.app_context():
            # Recent stored data now shows a run of relief outings, dropping the
            # start share below the reliever threshold.
            for index in range(6):
                db.session.add(GameLog(
                    pitcher_id=flipper_id,
                    mlb_game_pk=541 * 100 + 50 + index,
                    game_date=date.today() - timedelta(days=index),
                    pitches_thrown=15,
                    innings_pitched=1.0,
                    innings_pitched_outs=3,
                    games_started=0,
                    game_type='R',
                ))
            db.session.commit()

        _body, ids_after = _fatigue_pitcher_ids(client)
        assert flipper_id in ids_after
