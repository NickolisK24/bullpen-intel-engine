from datetime import date, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
import models.prospect  # noqa: F401
from services.bullpen_context import (
    BULLPEN_CONTEXT_SAMPLE_CAP,
    build_team_bullpen_context,
)
from services.roster_status import STATUS_ACTIVE
from utils.db import db
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs
from utils.time import utc_now_naive


REF = date(2026, 6, 8)

ROTATION_CONTEXT_KEYS = {
    'context_available',
    'evidence_type',
    'window_days',
    'starter_avg_ip_last_7',
    'starter_avg_ip_prev_7',
    'starter_starts_last_7',
    'starter_starts_prev_7',
    'delta_ip',
    'trend',
    'windows',
    'rotation_avg_ip_7d',
    'rotation_avg_ip_14d',
    'rotation_ip_trend',
    'early_bullpen_entry_rate',
    'bullpen_coverage_ip_7d',
    'rotation_games_analyzed_7d',
    'rotation_games_analyzed_14d',
    'rotation_games_excluded_14d',
    'rotation_early_bullpen_entry_games_14d',
    'rotation_context_layer',
    'start_classification_state',
    'unknown_start_rows',
    'unknown_start_row_share',
}

USAGE_DEMAND_CONTEXT_KEYS = {
    'context_available',
    'evidence_type',
    'window_days',
    'bullpen_appearances_last_7',
    'bullpen_appearances_prev_7',
    'bullpen_pitches_last_7',
    'bullpen_pitches_prev_7',
    'appearance_delta',
    'pitch_delta',
    'appearance_pct_delta',
    'pitch_pct_delta',
    'unknown_start_rows_excluded',
    'start_classification_state',
    'unknown_start_rows',
    'unknown_start_row_share',
    'trend',
    'windows',
}

BULLPEN_CONCENTRATION_CONTEXT_KEYS = {
    'capability',
    'version',
    'source',
    'reference_date',
    'window_days',
    'window_start_10d',
    'window_end_10d',
    'top_three_workload_share_10d',
    'league_top_three_workload_share_10d',
    'top_three_share_delta_vs_league',
    'bullpen_workload_total_10d',
    'concentration_band',
    'top_three_relievers_10d',
    'qualifying_reliever_count_10d',
    'bullpen_workload_appearances_10d',
    'league_team_count_10d',
    'excluded_starting_workload_rows_10d',
    'unknown_role_rows_excluded_10d',
    'zero_pitch_artifact_rows_excluded_10d',
    'non_pitch_workload_rows_excluded_10d',
    'rows_without_pitcher_id_10d',
    'excluded_row_reasons',
    'limitations',
}

BULLPEN_OPTIONALITY_CONTEXT_KEYS = {
    'capability',
    'version',
    'source',
    'context_available',
    'reference_date',
    'available_arms_count',
    'monitor_arms_count',
    'restricted_arms_count',
    'limited_arms_count',
    'avoid_arms_count',
    'unavailable_arms_count',
    'unknown_status_count',
    'clean_workload_options',
    'secondary_options',
    'practical_close_game_paths_count',
    'optionality_band',
    'optionality_summary_inputs',
    'limitations',
}


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


def _seed_pitcher(team_id, name, mlb_id, position='P', roster_status=None):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position=position,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
        roster_status_updated_at=utc_now_naive() if roster_status else None,
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _seed_log(pitcher, days_ago, game_pk, innings, pitches=15, games_started=0):
    innings_outs = parse_mlb_innings_to_outs(innings)
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=REF - timedelta(days=days_ago),
        innings_pitched=outs_to_decimal_innings(innings_outs),
        innings_pitched_outs=innings_outs,
        pitches_thrown=pitches,
        games_started=games_started,
        game_type='R',
    ))
    db.session.commit()


def _seed_score(pitcher, raw_score=10.0, risk_level='LOW'):
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        risk_level=risk_level,
    ))
    db.session.commit()


def _seed_team_identity(team_id, mlb_id):
    return _seed_pitcher(team_id, f'Team {team_id} Pitcher', mlb_id)


def _assert_normalized_context_shapes(result):
    assert set(result['rotation_context']) == ROTATION_CONTEXT_KEYS
    assert set(result['usage_demand_context']) == USAGE_DEMAND_CONTEXT_KEYS
    assert set(result['bullpen_concentration_context']) == BULLPEN_CONCENTRATION_CONTEXT_KEYS
    assert set(result['bullpen_optionality_context']) == BULLPEN_OPTIONALITY_CONTEXT_KEYS


def test_no_data_team_returns_normalized_rotation_context_shape(client):
    with client.application.app_context():
        _seed_team_identity(116, 11601)

        context = build_team_bullpen_context(116)

    rotation = context['rotation_context']
    assert set(rotation) == ROTATION_CONTEXT_KEYS
    assert rotation['context_available'] is False
    assert rotation['window_days'] == 7
    assert rotation['starter_avg_ip_last_7'] is None
    assert rotation['starter_avg_ip_prev_7'] is None
    assert rotation['starter_starts_last_7'] == 0
    assert rotation['starter_starts_prev_7'] == 0
    assert rotation['delta_ip'] is None
    assert rotation['trend'] == 'insufficient_data'
    assert rotation['windows'] is None
    assert rotation['rotation_avg_ip_7d'] is None
    assert rotation['rotation_avg_ip_14d'] is None
    assert rotation['rotation_ip_trend'] is None
    assert rotation['early_bullpen_entry_rate'] is None
    assert rotation['bullpen_coverage_ip_7d'] is None
    assert rotation['rotation_games_analyzed_7d'] == 0
    assert rotation['rotation_games_analyzed_14d'] == 0
    assert rotation['rotation_games_excluded_14d'] == 0
    assert rotation['rotation_early_bullpen_entry_games_14d'] == 0
    assert rotation['rotation_context_layer'] is None
    assert rotation['start_classification_state'] == 'complete'
    assert rotation['unknown_start_rows'] == 0
    assert rotation['unknown_start_row_share'] == 0.0
    assert 'No stored game-log context was found for this team.' in context['limitations']


def test_no_data_team_returns_normalized_usage_demand_context_shape(client):
    with client.application.app_context():
        _seed_team_identity(117, 11701)

        context = build_team_bullpen_context(117)

    demand = context['usage_demand_context']
    assert set(demand) == USAGE_DEMAND_CONTEXT_KEYS
    assert demand['context_available'] is False
    assert demand['window_days'] == 7
    assert demand['bullpen_appearances_last_7'] == 0
    assert demand['bullpen_appearances_prev_7'] == 0
    assert demand['bullpen_pitches_last_7'] == 0
    assert demand['bullpen_pitches_prev_7'] == 0
    assert demand['appearance_delta'] == 0
    assert demand['pitch_delta'] == 0
    assert demand['appearance_pct_delta'] is None
    assert demand['pitch_pct_delta'] is None
    assert demand['unknown_start_rows_excluded'] == 0
    assert demand['start_classification_state'] == 'complete'
    assert demand['unknown_start_rows'] == 0
    assert demand['unknown_start_row_share'] == 0.0
    assert demand['trend'] == 'insufficient_data'
    assert demand['windows'] is None
    assert 'No stored game-log context was found for this team.' in context['limitations']


def test_no_data_team_returns_normalized_bullpen_concentration_context_shape(client):
    with client.application.app_context():
        _seed_team_identity(126, 12601)

        context = build_team_bullpen_context(126)

    concentration = context['bullpen_concentration_context']
    assert set(concentration) == BULLPEN_CONCENTRATION_CONTEXT_KEYS
    assert concentration['reference_date'] is None
    assert concentration['window_start_10d'] is None
    assert concentration['window_end_10d'] is None
    assert concentration['top_three_workload_share_10d'] is None
    assert concentration['league_top_three_workload_share_10d'] is None
    assert concentration['top_three_share_delta_vs_league'] is None
    assert concentration['bullpen_workload_total_10d'] == 0
    assert concentration['concentration_band'] == 'insufficient_data'
    assert concentration['top_three_relievers_10d'] == []
    assert concentration['qualifying_reliever_count_10d'] == 0
    assert concentration['bullpen_workload_appearances_10d'] == 0
    assert concentration['league_team_count_10d'] == 0
    assert concentration['excluded_row_reasons'] == {}
    assert 'No stored game-log context was found for this team.' in context['limitations']


def test_no_data_team_returns_normalized_bullpen_optionality_context_shape(client):
    with client.application.app_context():
        _seed_team_identity(131, 13101)

        context = build_team_bullpen_context(131)

    optionality = context['bullpen_optionality_context']
    assert set(optionality) == BULLPEN_OPTIONALITY_CONTEXT_KEYS
    assert optionality['context_available'] is False
    assert optionality['reference_date'] is None
    assert optionality['available_arms_count'] == 0
    assert optionality['monitor_arms_count'] == 0
    assert optionality['restricted_arms_count'] == 0
    assert optionality['clean_workload_options'] == []
    assert optionality['secondary_options'] == []
    assert optionality['practical_close_game_paths_count'] == 0
    assert optionality['optionality_band'] == 'insufficient_data'
    assert optionality['optionality_summary_inputs'] == {
        'available_count': 0,
        'clean_count': 0,
        'secondary_count': 0,
        'restricted_count': 0,
        'practical_paths': 0,
        'band': 'insufficient_data',
    }
    assert 'No stored game-log context was found for this team.' in context['limitations']


def test_shorter_starter_outings_detected(client):
    with client.application.app_context():
        starter = _seed_pitcher(118, 'Shorter Starter', 11801)
        _seed_log(starter, 1, 118011, innings=4.2, pitches=82, games_started=1)
        _seed_log(starter, 3, 118012, innings=4.1, pitches=88, games_started=1)
        _seed_log(starter, 8, 118013, innings=6.0, pitches=96, games_started=1)
        _seed_log(starter, 10, 118014, innings=6.2, pitches=98, games_started=1)

        context = build_team_bullpen_context(118, reference_date=REF)

    rotation = context['rotation_context']
    _assert_normalized_context_shapes(context)
    assert rotation['context_available'] is True
    assert rotation['window_days'] == 7
    assert rotation['starter_avg_ip_last_7'] == 4.5
    assert rotation['starter_avg_ip_prev_7'] == 6.3
    assert rotation['trend'] == 'shorter_outings'
    assert rotation['rotation_avg_ip_7d'] == 4.5
    assert rotation['rotation_avg_ip_14d'] == 5.4
    assert rotation['rotation_ip_trend'] == -0.9
    assert rotation['early_bullpen_entry_rate'] == 50.0
    assert rotation['bullpen_coverage_ip_7d'] is None
    assert rotation['rotation_games_analyzed_7d'] == 2
    assert rotation['rotation_games_analyzed_14d'] == 4
    assert rotation['rotation_context_layer']['capability'] == 'rotation_context_v1'


def test_longer_starter_outings_detected(client):
    with client.application.app_context():
        starter = _seed_pitcher(119, 'Longer Starter', 11901)
        _seed_log(starter, 1, 119011, innings=6.2, pitches=92, games_started=1)
        _seed_log(starter, 4, 119012, innings=6.0, pitches=90, games_started=1)
        _seed_log(starter, 8, 119013, innings=4.2, pitches=84, games_started=1)
        _seed_log(starter, 12, 119014, innings=5.0, pitches=86, games_started=1)

        context = build_team_bullpen_context(119, reference_date=REF)

    rotation = context['rotation_context']
    _assert_normalized_context_shapes(context)
    assert rotation['context_available'] is True
    assert rotation['window_days'] == 7
    assert rotation['starter_avg_ip_last_7'] == 6.3
    assert rotation['starter_avg_ip_prev_7'] == 4.8
    assert rotation['trend'] == 'longer_outings'


def test_rising_bullpen_demand_detected(client):
    with client.application.app_context():
        reliever = _seed_pitcher(120, 'Busy Reliever', 12001)
        for idx, days_ago in enumerate([0, 1, 2, 4]):
            _seed_log(reliever, days_ago, 120010 + idx, innings=1.0, pitches=18, games_started=0)
        for idx, days_ago in enumerate([8, 12]):
            _seed_log(reliever, days_ago, 120020 + idx, innings=1.0, pitches=12, games_started=0)

        context = build_team_bullpen_context(120, reference_date=REF)

    demand = context['usage_demand_context']
    _assert_normalized_context_shapes(context)
    assert demand['context_available'] is True
    assert demand['window_days'] == 7
    assert demand['bullpen_appearances_last_7'] == 4
    assert demand['bullpen_appearances_prev_7'] == 2
    assert demand['bullpen_pitches_last_7'] == 72
    assert demand['bullpen_pitches_prev_7'] == 24
    assert demand['trend'] == 'increasing_demand'


def test_unknown_games_started_rows_do_not_count_as_bullpen_demand(client):
    with client.application.app_context():
        reliever = _seed_pitcher(125, 'Known Reliever', 12501)
        unknown = _seed_pitcher(125, 'Unknown Role', 12502)
        _seed_log(reliever, 1, 125011, innings=1.0, pitches=12, games_started=0)
        _seed_log(unknown, 1, 125012, innings=1.0, pitches=14, games_started=None)
        _seed_log(unknown, 2, 125013, innings=1.0, pitches=13, games_started=None)

        context = build_team_bullpen_context(125, reference_date=REF)

    demand = context['usage_demand_context']
    assert demand['bullpen_appearances_last_7'] == 1
    assert demand['unknown_start_rows_excluded'] == 2
    assert demand['start_classification_state'] == 'material_unknown'
    assert demand['context_available'] is False
    assert demand['trend'] == 'insufficient_start_data'
    assert any('More than 25%' in item for item in context['limitations'])


def test_falling_bullpen_demand_detected(client):
    with client.application.app_context():
        reliever = _seed_pitcher(121, 'Lighter Reliever', 12101)
        _seed_log(reliever, 1, 121011, innings=1.0, pitches=10, games_started=0)
        for idx, days_ago in enumerate([8, 9, 11, 13]):
            _seed_log(reliever, days_ago, 121020 + idx, innings=1.0, pitches=18, games_started=0)

        context = build_team_bullpen_context(121, reference_date=REF)

    demand = context['usage_demand_context']
    _assert_normalized_context_shapes(context)
    assert demand['context_available'] is True
    assert demand['window_days'] == 7
    assert demand['bullpen_appearances_last_7'] == 1
    assert demand['bullpen_appearances_prev_7'] == 4
    assert demand['bullpen_pitches_last_7'] == 10
    assert demand['bullpen_pitches_prev_7'] == 72
    assert demand['trend'] == 'decreasing_demand'


def test_bullpen_concentration_context_is_wired_with_league_baseline(client):
    with client.application.app_context():
        team_one = [
            _seed_pitcher(127, f'Context One Reliever {idx}', 12700 + idx)
            for idx in range(1, 7)
        ]
        team_two = [
            _seed_pitcher(128, f'Context Two Reliever {idx}', 12800 + idx)
            for idx in range(1, 5)
        ]
        for idx, pitches in enumerate([40, 40, 40, 30, 30, 20], start=1):
            _seed_log(team_one[idx - 1], idx % 4, 127000 + idx, innings=1.0, pitches=pitches)
        for idx, pitches in enumerate([80, 60, 40, 20], start=1):
            _seed_log(team_two[idx - 1], idx % 4, 128000 + idx, innings=1.0, pitches=pitches)

        context = build_team_bullpen_context(128, reference_date=REF)

    concentration = context['bullpen_concentration_context']
    _assert_normalized_context_shapes(context)
    assert concentration['top_three_workload_share_10d'] == 90.0
    assert concentration['league_top_three_workload_share_10d'] == 75.0
    assert concentration['top_three_share_delta_vs_league'] == 15.0
    assert concentration['bullpen_workload_total_10d'] == 200
    assert concentration['concentration_band'] == 'narrow'
    assert concentration['league_team_count_10d'] == 2
    assert [row['player_id'] for row in concentration['top_three_relievers_10d']] == [
        12801,
        12802,
        12803,
    ]


def test_bullpen_optionality_context_is_wired_from_current_availability(client):
    with client.application.app_context():
        clean_one = _seed_pitcher(
            129, 'Clean One', 12901, position='RP', roster_status=STATUS_ACTIVE,
        )
        clean_two = _seed_pitcher(
            129, 'Clean Two', 12902, position='RP', roster_status=STATUS_ACTIVE,
        )
        monitor = _seed_pitcher(
            129, 'Monitor Arm', 12903, position='RP', roster_status=STATUS_ACTIVE,
        )
        limited = _seed_pitcher(
            129, 'Limited Arm', 12904, position='RP', roster_status=STATUS_ACTIVE,
        )
        _seed_log(clean_one, 2, 129001, innings=1.0, pitches=12)
        _seed_log(clean_two, 3, 129002, innings=1.0, pitches=10)
        _seed_log(monitor, 1, 129003, innings=1.0, pitches=18)
        _seed_log(limited, 2, 129004, innings=1.0, pitches=10)
        for pitcher in (clean_one, clean_two, monitor):
            _seed_score(pitcher, raw_score=10.0)
        _seed_score(limited, raw_score=65.0, risk_level='HIGH')

        context = build_team_bullpen_context(129, reference_date=REF)

    optionality = context['bullpen_optionality_context']
    _assert_normalized_context_shapes(context)
    assert optionality['context_available'] is True
    assert optionality['available_arms_count'] == 2
    assert optionality['monitor_arms_count'] == 1
    assert optionality['restricted_arms_count'] == 1
    assert optionality['limited_arms_count'] == 1
    assert optionality['practical_close_game_paths_count'] == 2
    assert optionality['optionality_band'] == 'thin'
    assert optionality['optionality_summary_inputs'] == {
        'available_count': 2,
        'clean_count': 2,
        'secondary_count': 1,
        'restricted_count': 1,
        'practical_paths': 2,
        'band': 'thin',
    }
    assert [option['player_id'] for option in optionality['clean_workload_options']] == [
        12901,
        12902,
    ]
    assert optionality['secondary_options'] == [{
        'player_id': 12903,
        'name': 'Monitor Arm',
        'availability': 'Monitor',
        'reason': '18 pitches yesterday',
    }]


def test_league_sample_is_capped(client):
    with client.application.app_context():
        for offset in range(BULLPEN_CONTEXT_SAMPLE_CAP + 2):
            pitcher = _seed_team_identity(200 + offset, 20000 + offset)
            _seed_log(pitcher, 1, 200000 + offset, innings=1.0, games_started=0)

    response = client.get('/api/bullpen/context/diagnostic?mode=league_sample')

    assert response.status_code == 200
    body = response.get_json()
    assert body['mode'] == 'league_sample'
    assert body['sample_cap'] == BULLPEN_CONTEXT_SAMPLE_CAP
    assert len(body['results']) == BULLPEN_CONTEXT_SAMPLE_CAP
    assert len(body['sampled_team_ids']) == BULLPEN_CONTEXT_SAMPLE_CAP
    for result in body['results']:
        _assert_normalized_context_shapes(result)


def test_data_backed_and_no_data_contracts_have_the_same_shape(client):
    with client.application.app_context():
        no_data_pitcher = _seed_team_identity(122, 12201)
        data_pitcher = _seed_pitcher(123, 'Data Reliever', 12301)
        _seed_log(data_pitcher, 1, 123011, innings=1.0, pitches=16, games_started=0)

        no_data = build_team_bullpen_context(no_data_pitcher.team_id)
        data_backed = build_team_bullpen_context(data_pitcher.team_id, reference_date=REF)

    assert set(no_data['rotation_context']) == set(data_backed['rotation_context'])
    assert set(no_data['usage_demand_context']) == set(data_backed['usage_demand_context'])
    assert set(no_data['bullpen_concentration_context']) == set(data_backed['bullpen_concentration_context'])
    assert set(no_data['bullpen_optionality_context']) == set(data_backed['bullpen_optionality_context'])


def test_diagnostic_route_team_mode_returns_evidence_contract(client):
    with client.application.app_context():
        starter = _seed_pitcher(130, 'Context Starter', 13001)
        reliever = _seed_pitcher(130, 'Context Reliever', 13002)
        _seed_log(starter, 1, 130011, innings=5.0, pitches=84, games_started=1)
        _seed_log(starter, 8, 130012, innings=6.0, pitches=94, games_started=1)
        _seed_log(reliever, 1, 130021, innings=1.0, pitches=16, games_started=0)
        _seed_log(reliever, 8, 130022, innings=1.0, pitches=10, games_started=0)

    response = client.get('/api/bullpen/context/diagnostic?mode=team&team_id=130')

    assert response.status_code == 200
    body = response.get_json()
    assert body['capability'] == 'bullpen_context_engine_v1_diagnostic'
    assert body['ranking_applied'] is False
    assert body['selection_made'] is False
    assert body['mode'] == 'team'
    assert body['team_id'] == 130
    result = body['results'][0]
    _assert_normalized_context_shapes(result)
    assert result['team_id'] == 130
    assert result['rotation_context']['evidence_type'] == 'starter_innings_pitched'
    assert result['usage_demand_context']['evidence_type'] == 'bullpen_appearance_and_pitch_volume'
    assert result['bullpen_concentration_context']['capability'] == 'bullpen_concentration_context_v1'
    assert result['bullpen_optionality_context']['capability'] == 'bullpen_optionality_context_v1'
    assert result['availability_context'] == {
        'context_available': False,
        'reason': 'not_implemented',
        'data_source': None,
    }


def test_context_limitations_are_included(client):
    with client.application.app_context():
        pitcher = _seed_team_identity(140, 14001)
        _seed_log(pitcher, 1, 140011, innings=1.0, games_started=0)

    response = client.get('/api/bullpen/context/diagnostic?team_id=140')

    assert response.status_code == 200
    body = response.get_json()
    for limitation in [
        'Context is descriptive.',
        'Context is not causal proof.',
        'Context does not explain every bullpen state.',
        'Context does not override observations.',
    ]:
        assert limitation in body['limitations']
        assert limitation in body['results'][0]['limitations']
