from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
import models.prospect  # noqa: F401
from services.availability import (
    STATUS_AVAILABLE,
    STATUS_LIMITED,
    STATUS_MONITOR,
)
from services.bullpen_concentration_context import build_bullpen_concentration_context
from services.bullpen_context import build_team_bullpen_context
from services.bullpen_optionality_context import build_bullpen_optionality_context
from services.injury_context import build_injury_context
from services.role_stability_context import build_role_stability_context
from services.rotation_context import build_rotation_context
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs
from utils.time import utc_now_naive


REF = date(2026, 6, 20)
REPO_ROOT = Path(__file__).resolve().parents[2]
LAYER_SERVICE_PATHS = [
    REPO_ROOT / 'backend' / 'services' / 'rotation_context.py',
    REPO_ROOT / 'backend' / 'services' / 'bullpen_concentration_context.py',
    REPO_ROOT / 'backend' / 'services' / 'bullpen_optionality_context.py',
    REPO_ROOT / 'backend' / 'services' / 'role_stability_context.py',
    REPO_ROOT / 'backend' / 'services' / 'injury_context.py',
    REPO_ROOT / 'backend' / 'services' / 'bullpen_context.py',
]


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


def pitcher(
    player_id,
    name=None,
    *,
    team_id=1,
    position='RP',
    roster_status=STATUS_ACTIVE,
):
    return SimpleNamespace(
        id=player_id + 100000,
        mlb_id=player_id,
        full_name=name or f'Pitcher {player_id}',
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position=position,
        active=True,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
    )


def log(
    player_id,
    days_ago,
    pitches,
    *,
    team_id=1,
    games_started=0,
    outs=3,
    game_pk=None,
    game_type='R',
):
    return SimpleNamespace(
        pitcher_id=player_id + 100000,
        pitcher=pitcher(player_id, team_id=team_id),
        mlb_game_pk=game_pk or (team_id * 100000 + player_id + days_ago),
        game_date=REF - timedelta(days=days_ago),
        game_type=game_type,
        games_started=games_started,
        innings_pitched_outs=outs,
        innings_pitched=outs / 3.0,
        pitches_thrown=pitches,
    )


def availability_record(player_id, status=STATUS_AVAILABLE, *, inputs=None):
    return {
        'pitcher_id': player_id + 100000,
        'pitcher': pitcher(player_id),
        'availability': {
            'availability_status': status,
            'data_state': 'fresh',
            'confidence': 'high',
            'reasons': [],
            'inputs': inputs or {
                'appearances_last_5_days': 1,
                'pitches_last_5_days': 12,
                'pitches_last_3_days': 12,
                'pitches_yesterday': 0,
                'back_to_back': False,
            },
            'roster_status': {
                'status': STATUS_ACTIVE,
                'is_active_mlb': True,
            },
        },
    }


def active_record(p):
    return {
        'pitcher': p,
        'availability': {
            'roster_status': {
                'status': STATUS_ACTIVE,
                'is_active_mlb': True,
            },
        },
    }


def seed_pitcher(team_id, name, mlb_id, *, position='RP', roster_status=STATUS_ACTIVE):
    row = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position=position,
        active=True,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
        roster_status_updated_at=utc_now_naive() if roster_status else None,
    )
    db.session.add(row)
    db.session.commit()
    return row


def seed_log(row, days_ago, game_pk, *, innings=1.0, pitches=12, games_started=0):
    outs = parse_mlb_innings_to_outs(innings)
    db.session.add(GameLog(
        pitcher_id=row.id,
        mlb_game_pk=game_pk,
        game_date=REF - timedelta(days=days_ago),
        innings_pitched=outs_to_decimal_innings(outs),
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        games_started=games_started,
        game_type='R',
    ))
    db.session.commit()


def seed_score(row, raw_score=10.0, risk_level='LOW'):
    db.session.add(FatigueScore(
        pitcher_id=row.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        risk_level=risk_level,
    ))
    db.session.commit()


def test_context_layer_contracts_stay_predictable_for_missing_partial_and_complete_inputs():
    complete_logs = [
        log(1, 1, 50, games_started=1, outs=18, game_pk=1),
        log(2, 1, 20, game_pk=1),
        log(3, 2, 18, game_pk=2),
        log(4, 11, 16, game_pk=3),
    ]

    rotation_missing = build_rotation_context([], reference_date=REF)
    rotation_complete = build_rotation_context(complete_logs, reference_date=REF)
    concentration_missing = build_bullpen_concentration_context([], reference_date=REF)
    concentration_complete = build_bullpen_concentration_context(complete_logs, reference_date=REF)
    optionality_missing = build_bullpen_optionality_context([], reference_date=REF)
    optionality_partial = build_bullpen_optionality_context(
        [availability_record(1), availability_record(2, STATUS_MONITOR)],
        reference_date=REF,
    )
    stability_missing = build_role_stability_context([], reference_date=REF)
    stability_complete = build_role_stability_context(complete_logs, reference_date=REF)
    injury_missing = build_injury_context([], reference_date=REF)
    injury_complete = build_injury_context(
        [pitcher(1), pitcher(2, 'Inactive Arm', roster_status=STATUS_IL_15)],
        active_records=[active_record(pitcher(1))],
        reference_date=REF,
    )

    assert set(rotation_missing) == set(rotation_complete)
    assert set(concentration_missing) == set(concentration_complete)
    assert set(optionality_missing) == set(optionality_partial)
    assert set(stability_missing) == set(stability_complete)
    assert set(injury_missing) == set(injury_complete)
    assert optionality_missing['optionality_band'] == 'insufficient_data'
    assert stability_missing['stability_band'] == 'insufficient_data'
    assert injury_missing['depth_pressure_band'] == 'insufficient_data'


def test_valid_workload_authority_is_shared_by_concentration_and_role_stability():
    logs = [
        log(1, 1, 35),
        log(2, 1, 30),
        log(3, 2, 25),
        log(4, 3, 10),
        log(5, 1, 0, outs=0),  # preserved raw artifact, not workload.
        log(6, 1, 90, games_started=1, outs=18),
        log(1, 11, 32),
        log(2, 12, 28),
        log(3, 13, 24),
    ]

    concentration = build_bullpen_concentration_context(logs, reference_date=REF)
    stability = build_role_stability_context(logs, reference_date=REF)

    concentration_names = [
        row['name'] for row in concentration['top_three_relievers_10d']
    ]
    assert concentration_names == stability['current_operational_core']
    assert concentration['zero_pitch_artifact_rows_excluded_10d'] == 1
    assert concentration['excluded_starting_workload_rows_10d'] == 1
    assert stability['zero_pitch_artifact_rows_excluded_20d'] == 1
    assert stability['excluded_starting_workload_rows_20d'] == 1


def test_rotation_context_keeps_starter_and_bullpen_innings_separate_for_openers_and_doubleheaders():
    logs = [
        log(1, 1, 18, games_started=1, outs=3, game_pk=1001),
        log(2, 1, 32, games_started=0, outs=24, game_pk=1001),
        log(3, 1, 86, games_started=1, outs=18, game_pk=1002),
        log(4, 1, 18, games_started=0, outs=9, game_pk=1002),
    ]

    rotation = build_rotation_context(logs, reference_date=REF)

    assert rotation['games_analyzed_7d'] == 2
    assert rotation['rotation_avg_ip_7d'] == 3.5
    assert rotation['early_bullpen_entry_rate'] == 50.0
    assert rotation['bullpen_coverage_ip_7d'] == 5.5
    assert rotation['early_bullpen_entry_games_14d'] == 1


def test_optionality_respects_current_availability_and_injury_keeps_active_relief_out_of_inactive_depth():
    monitor_inputs = {
        'appearances_last_5_days': 2,
        'pitches_last_5_days': 26,
        'pitches_last_3_days': 26,
        'pitches_yesterday': 18,
        'back_to_back': False,
    }
    optionality = build_bullpen_optionality_context(
        [
            availability_record(1, STATUS_AVAILABLE),
            availability_record(2, STATUS_MONITOR, inputs=monitor_inputs),
            availability_record(3, STATUS_LIMITED),
        ],
        reference_date=REF,
    )
    active = pitcher(1, 'Active Relief')
    inactive = pitcher(2, 'Inactive Relief', roster_status=STATUS_IL_15)
    injury = build_injury_context(
        [active, inactive],
        active_records=[active_record(active)],
        reference_date=REF,
    )

    assert optionality['available_arms_count'] == 1
    assert optionality['monitor_arms_count'] == 1
    assert optionality['restricted_arms_count'] == 1
    assert optionality['practical_close_game_paths_count'] == 1
    assert injury['active_bullpen_arms_count'] == 1
    assert injury['inactive_bullpen_arms_count'] == 1
    assert injury['inactive_bullpen_arms'][0]['name'] == 'Inactive Relief'


def test_context_services_do_not_use_machine_clock_or_story_output_surfaces():
    forbidden_tokens = [
        'datetime.utcnow',
        'date.today',
        'new Date(',
        'generate_story',
        'build_story',
        'create_story',
        'story_renderer',
        'rank_',
        'ranking_applied = True',
        'prediction_applied = True',
        'selection_made = True',
    ]
    for path in LAYER_SERVICE_PATHS:
        source = path.read_text(encoding='utf-8')
        for token in forbidden_tokens:
            assert token not in source, f'{token} found in {path.name}'


def test_aggregate_context_handles_no_games_in_window_with_safe_defaults(client):
    with client.application.app_context():
        row = seed_pitcher(910, 'No Window Reliever', 91001, position='RP')
        seed_log(row, 45, 910001)

        context = build_team_bullpen_context(910, reference_date=REF)

    assert context['reference_date'] == '2026-06-20'
    assert context['rotation_context']['context_available'] is False
    assert context['bullpen_concentration_context']['bullpen_workload_total_10d'] == 0
    assert context['role_stability_context']['context_available'] is False
    assert context['injury_context']['inactive_bullpen_arms_count'] == 0
    assert 'stories' not in context


def test_aggregate_context_uses_stored_data_through_date_when_freshness_is_stale(client):
    stale_reference = REF - timedelta(days=30)
    with client.application.app_context():
        row = seed_pitcher(912, 'Stale Data Reliever', 91201, position='RP')
        db.session.add(GameLog(
            pitcher_id=row.id,
            mlb_game_pk=912001,
            game_date=stale_reference,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            pitches_thrown=15,
            games_started=0,
            game_type='R',
        ))
        db.session.commit()

        context = build_team_bullpen_context(912)

    assert context['reference_date'] == stale_reference.isoformat()
    assert context['data_through_date'] == stale_reference.isoformat()
    assert context['bullpen_concentration_context']['reference_date'] == stale_reference.isoformat()
    assert context['bullpen_concentration_context']['bullpen_workload_total_10d'] == 15
    assert 'stories' not in context


def test_story_intelligence_readiness_payload_has_neutral_inputs_without_generating_stories(client):
    with client.application.app_context():
        starter = seed_pitcher(911, 'Context Starter', 91101, position='SP')
        relievers = [
            seed_pitcher(911, f'Context Reliever {idx}', 91110 + idx, position='RP')
            for idx in range(1, 5)
        ]
        inactive = seed_pitcher(
            911,
            'Inactive Depth Arm',
            91150,
            position='RP',
            roster_status=STATUS_IL_15,
        )
        seed_log(starter, 1, 911001, innings=4.0, pitches=80, games_started=1)
        for idx, pitches in enumerate([28, 24, 20, 10], start=1):
            seed_log(relievers[idx - 1], idx, 911010 + idx, innings=1.0, pitches=pitches)
            seed_score(relievers[idx - 1], raw_score=10.0)
        for idx, pitches in enumerate([26, 22, 18], start=1):
            seed_log(relievers[idx - 1], idx + 11, 911100 + idx, innings=1.0, pitches=pitches)

        context = build_team_bullpen_context(911, reference_date=REF)

    readiness_inputs = {
        'observation': context['bullpen_concentration_context']['top_three_relievers_10d'],
        'baseline': {
            'rotation_avg_ip_14d': context['rotation_context']['rotation_avg_ip_14d'],
            'previous_core': context['role_stability_context']['previous_operational_core'],
        },
        'cause': {
            'rotation_ip_trend': context['rotation_context']['rotation_ip_trend'],
            'inactive_bullpen_arms_count': context['injury_context']['inactive_bullpen_arms_count'],
        },
        'interpretation': {
            'concentration_band': context['bullpen_concentration_context']['concentration_band'],
            'optionality_band': context['bullpen_optionality_context']['optionality_band'],
            'stability_band': context['role_stability_context']['stability_band'],
            'depth_pressure_band': context['injury_context']['depth_pressure_band'],
        },
        'forward_constraint': {
            'limitations': context['limitations'],
            'injury_context_confidence': context['injury_context']['injury_context_confidence'],
        },
    }

    assert readiness_inputs['observation']
    assert readiness_inputs['baseline']['previous_core']
    assert readiness_inputs['cause']['inactive_bullpen_arms_count'] == 1
    assert all(readiness_inputs['interpretation'].values())
    assert readiness_inputs['forward_constraint']['limitations']
    assert 'stories' not in context
    assert 'story' not in readiness_inputs
