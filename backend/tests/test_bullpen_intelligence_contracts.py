from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
import models.prospect  # noqa: F401
from services.availability import STATUS_AVAILABLE
from services.bullpen_capacity import (
    CAPABILITY as CAPACITY_CAPABILITY,
    UNAVAILABLE_ZERO_OUTS_LIMITATION,
)
from services.bullpen_environment import CAPABILITY as ENVIRONMENT_CAPABILITY
from services.bullpen_stability import (
    CAPABILITY as STABILITY_CAPABILITY,
    CURRENT_ASSIGNMENT_LIMITATION as STABILITY_CURRENT_ASSIGNMENT_LIMITATION,
    USAGE_PATTERN_LIMITATION as STABILITY_USAGE_PATTERN_LIMITATION,
)
from services.four_beat_stories import (
    RULE_HIDDEN_CAPACITY_LOSS,
    RULE_PRESSURE_DISTRIBUTION,
    RULE_SPECIAL_SITUATION,
    RULE_STRESS_TRANSFER,
    RULE_SUSTAINABILITY_QUESTION,
    TeamInputs,
    assemble_story,
    compute_team_story_inputs,
    evaluate_team_rules,
)
from services.rotation_support_pressure import (
    CAPABILITY as ROTATION_CAPABILITY,
    CURRENT_ASSIGNMENT_LIMITATION as ROTATION_CURRENT_ASSIGNMENT_LIMITATION,
    OPENER_BULK_LIMITATION,
)
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15
import services.sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.innings import outs_to_decimal_innings
from utils.time import utc_now_naive


TEAM_CAPACITY_ELEVATED = 601
TEAM_ROTATION_HEAVY = 602


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_pitcher(
    name,
    *,
    team_id,
    mlb_id,
    team_abbr,
    position='RP',
    roster_status=STATUS_ACTIVE,
    raw_score=10.0,
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=team_abbr,
        position=position,
        active=True,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
        roster_status_updated_at=utc_now_naive() if roster_status else None,
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=raw_score,
        risk_level='LOW',
        calculated_at=utc_now_naive(),
    ))
    db.session.commit()
    return pitcher


def _add_log(
    pitcher,
    *,
    game_pk,
    days_ago,
    outs,
    games_started,
    pitches=12,
    save=False,
    hold=False,
    leverage_index=None,
):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=date.today() - timedelta(days=days_ago),
        game_type='R',
        games_started=games_started,
        innings_pitched=outs_to_decimal_innings(outs),
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        save=save,
        save_situation=save,
        hold=hold,
        leverage_index=leverage_index,
    ))


def _seed_supportive_rotation_with_elevated_capacity():
    team_id = TEAM_CAPACITY_ELEVATED
    team_abbr = 'CIX'
    relievers = [
        _seed_pitcher(f'Capacity Stable Arm {idx}', team_id=team_id, mlb_id=60100 + idx, team_abbr=team_abbr)
        for idx in range(1, 4)
    ]
    unavailable = _seed_pitcher(
        'Capacity Unavailable Arm',
        team_id=team_id,
        mlb_id=60150,
        team_abbr=team_abbr,
        roster_status=STATUS_IL_15,
    )
    starters = [
        _seed_pitcher(
            f'Capacity Starter {idx}',
            team_id=team_id,
            mlb_id=60170 + idx,
            team_abbr=team_abbr,
            position='SP',
        )
        for idx in range(1, 4)
    ]
    for idx, starter in enumerate(starters, start=1):
        game_pk = 601000 + idx
        _add_log(starter, game_pk=game_pk, days_ago=idx, outs=18, games_started=1, pitches=76)
        for reliever in relievers:
            _add_log(reliever, game_pk=game_pk, days_ago=idx, outs=3, games_started=0, pitches=10)
    # The unavailable reliever intentionally has no season relief outs. Capacity
    # should keep the arm in the count and fall back to count-based weighting.
    assert unavailable is not None
    db.session.commit()
    return team_id


def _seed_heavy_rotation_with_clear_capacity():
    team_id = TEAM_ROTATION_HEAVY
    team_abbr = 'RHI'
    relievers = [
        _seed_pitcher(f'Rotation Stable Arm {idx}', team_id=team_id, mlb_id=60200 + idx, team_abbr=team_abbr)
        for idx in range(1, 4)
    ]
    starters = [
        _seed_pitcher(
            f'Rotation Starter {idx}',
            team_id=team_id,
            mlb_id=60270 + idx,
            team_abbr=team_abbr,
            position='SP',
        )
        for idx in range(1, 4)
    ]
    for idx, starter in enumerate(starters, start=1):
        game_pk = 602000 + idx
        _add_log(starter, game_pk=game_pk, days_ago=idx, outs=12, games_started=1, pitches=66)
        for reliever in relievers:
            _add_log(reliever, game_pk=game_pk, days_ago=idx, outs=5, games_started=0, pitches=14)
    db.session.commit()
    return team_id


def _assert_capacity_contract(capacity):
    assert capacity['capability'] == CAPACITY_CAPABILITY
    assert capacity['source'] == 'backend'
    assert set(capacity) >= {'capacity_loss', 'trust_capacity_loss'}
    for key in ('capacity_loss', 'trust_capacity_loss'):
        section = capacity[key]
        assert 'status' in section
        assert 'summary' in section
        assert 'definitions' in section
        assert 'limitations' in section


def _assert_rotation_contract(pressure):
    assert pressure['capability'] == ROTATION_CAPABILITY
    assert pressure['source'] == 'backend'
    assert pressure['window_days'] == 7
    assert pressure['reference_date']
    assert set(pressure) >= {
        'status',
        'games_in_window',
        'games_analyzed',
        'games_excluded',
        'definitions',
        'limitations',
        'source_limitations',
        'summary',
    }


def _assert_stability_contract(stability):
    assert stability['capability'] == STABILITY_CAPABILITY
    assert stability['source'] == 'backend'
    assert stability['window_days'] == 14
    assert stability['reference_date']
    assert set(stability) >= {
        'status',
        'recently_used_bullpen_count',
        'new_or_reintroduced_arm_count',
        'stable_core_count',
        'definitions',
        'limitations',
        'source_limitations',
        'summary',
    }


def _assert_environment_contract(environment):
    assert environment['capability'] == ENVIRONMENT_CAPABILITY
    assert environment['source'] == 'backend'
    assert set(environment) >= {
        'status',
        'primary_pressure_sources',
        'context_flags',
        'supporting_reads',
        'definitions',
        'limitations',
        'source_limitations',
        'summary',
    }


def _story_pitcher(pid):
    return SimpleNamespace(
        id=pid,
        full_name=f'Story Arm {pid}',
        team_id=1,
        team_name='Story Team',
        team_abbreviation='STY',
    )


def _story_record(pitcher):
    return {
        'pitcher': pitcher,
        'score': SimpleNamespace(pitcher_id=pitcher.id, risk_level='LOW', raw_score=10),
        'availability': {
            'availability_status': STATUS_AVAILABLE,
            'confidence': 'high',
            'data_state': 'fresh',
            'reasons': [],
            'limitations': [],
        },
        'eligibility': {'eligible': True, 'role': 'Reliever', 'limitations': []},
        'roster_status': {'status': STATUS_ACTIVE, 'is_active_mlb': True},
        'pitcher_labels': {
            'role': {'key': 'bridge_arm', 'label': 'Bridge Arm'},
            'read': {'key': 'clean_option', 'label': 'Clean Option'},
        },
    }


def _story_log(pid, days_ago, pitches):
    return SimpleNamespace(
        pitcher_id=pid,
        game_date=date(2026, 6, 18) - timedelta(days=days_ago),
        pitches_thrown=pitches,
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
    )


def _story_text(story):
    return ' '.join(
        str(value or '')
        for value in (
            story.get('title'),
            story.get('body'),
            *(beat.get('text') for beat in story.get('beats') or []),
        )
    )


def test_team_board_payload_exposes_all_intelligence_layers_with_contract_fields(client):
    with client.application.app_context():
        team_id = _seed_supportive_rotation_with_elevated_capacity()

    body = client.get(f'/api/bullpen/teams/{team_id}/board').get_json()

    assert set(body) >= {
        'capacity_intelligence',
        'rotation_support_pressure',
        'bullpen_stability',
        'bullpen_environment',
    }
    _assert_capacity_contract(body['capacity_intelligence'])
    _assert_rotation_contract(body['rotation_support_pressure'])
    _assert_stability_contract(body['bullpen_stability'])
    _assert_environment_contract(body['bullpen_environment'])


def test_team_board_contract_keeps_concepts_and_statuses_independent(client):
    with client.application.app_context():
        team_id = _seed_supportive_rotation_with_elevated_capacity()

    body = client.get(f'/api/bullpen/teams/{team_id}/board').get_json()
    capacity_loss = body['capacity_intelligence']['capacity_loss']
    rotation = body['rotation_support_pressure']
    stability = body['bullpen_stability']
    environment = body['bullpen_environment']

    assert capacity_loss['status'] == 'elevated'
    assert capacity_loss['unavailable_capacity_pct'] == 25
    assert UNAVAILABLE_ZERO_OUTS_LIMITATION in capacity_loss['limitations']

    assert rotation['status'] == 'supportive'
    assert rotation['starter_avg_innings'] == 6.0
    assert rotation['short_start_rate'] == 0.0

    assert stability['status'] == 'stable'
    assert stability['stable_core_count'] == 3
    assert stability['new_or_reintroduced_arm_count'] == 0

    assert environment['status'] == 'pressure_with_context'
    assert environment['primary_pressure_sources'] == ['capacity_loss']
    assert environment['supporting_reads']['capacity_loss_status'] == 'elevated'
    assert environment['supporting_reads']['rotation_support_status'] == 'supportive'
    assert environment['supporting_reads']['bullpen_stability_status'] == 'stable'

    assert 'capacity_loss' not in rotation
    assert 'unavailable_capacity_pct' not in rotation
    assert 'starter_avg_innings' not in capacity_loss
    assert 'short_start_count' not in stability
    assert 'new_or_reintroduced_arm_count' not in body['capacity_intelligence']
    assert 'starter_avg_innings' not in environment
    assert 'unavailable_capacity_pct' not in environment


def test_rotation_pressure_can_be_heavy_without_capacity_or_churn_escalation(client):
    with client.application.app_context():
        team_id = _seed_heavy_rotation_with_clear_capacity()

    body = client.get(f'/api/bullpen/teams/{team_id}/board').get_json()
    capacity_loss = body['capacity_intelligence']['capacity_loss']
    rotation = body['rotation_support_pressure']
    stability = body['bullpen_stability']
    environment = body['bullpen_environment']

    assert capacity_loss['status'] == 'clear'
    assert capacity_loss['unavailable_capacity_pct'] == 0

    assert rotation['status'] == 'heavy_pressure'
    assert rotation['short_start_rate'] == 1.0
    assert rotation['bullpen_innings_required'] == 15.0

    assert stability['status'] == 'stable'
    assert stability['new_or_reintroduced_arm_count'] == 0
    assert environment['status'] == 'pressure_with_context'
    assert environment['primary_pressure_sources'] == ['rotation_support_pressure']


def test_source_limitations_and_definitions_survive_in_final_board_payload(client):
    with client.application.app_context():
        team_id = _seed_supportive_rotation_with_elevated_capacity()

    body = client.get(f'/api/bullpen/teams/{team_id}/board').get_json()
    capacity_loss = body['capacity_intelligence']['capacity_loss']
    rotation = body['rotation_support_pressure']
    stability = body['bullpen_stability']
    environment = body['bullpen_environment']

    available_definition = capacity_loss['definitions']['available_capacity_pct']
    assert 'not classified as fully unavailable' in available_definition
    assert 'not be read as clean or fully available capacity' in available_definition

    assert ROTATION_CURRENT_ASSIGNMENT_LIMITATION in rotation['source_limitations']
    assert OPENER_BULK_LIMITATION in rotation['source_limitations']
    assert STABILITY_CURRENT_ASSIGNMENT_LIMITATION in stability['source_limitations']
    assert STABILITY_USAGE_PATTERN_LIMITATION in stability['source_limitations']
    assert ROTATION_CURRENT_ASSIGNMENT_LIMITATION in environment['source_limitations']
    assert OPENER_BULK_LIMITATION in environment['source_limitations']
    assert STABILITY_CURRENT_ASSIGNMENT_LIMITATION in environment['source_limitations']
    assert STABILITY_USAGE_PATTERN_LIMITATION in environment['source_limitations']


def test_dashboard_payload_exposes_league_contracts_for_all_intelligence_layers(client):
    with client.application.app_context():
        elevated_team = _seed_supportive_rotation_with_elevated_capacity()
        heavy_team = _seed_heavy_rotation_with_clear_capacity()

    body = client.get('/api/bullpen/dashboard').get_json()

    assert body['capacity_intelligence']['capability'] == 'league_bullpen_capacity_intelligence_v1'
    assert body['rotation_support_pressure']['capability'] == 'league_rotation_support_pressure_v1'
    assert body['bullpen_stability']['capability'] == 'league_bullpen_stability_v1'
    assert body['bullpen_environment']['capability'] == 'league_bullpen_environment_v1'
    for layer in (
        'capacity_intelligence',
        'rotation_support_pressure',
        'bullpen_stability',
        'bullpen_environment',
    ):
        assert body[layer]['source'] == 'backend'
        assert str(elevated_team) in body[layer]['by_team_id']
        assert str(heavy_team) in body[layer]['by_team_id']

    assert body['capacity_intelligence']['by_team_id'][str(elevated_team)]['capacity_loss']['status'] == 'elevated'
    assert body['rotation_support_pressure']['by_team_id'][str(heavy_team)]['status'] == 'heavy_pressure'
    assert body['bullpen_stability']['by_team_id'][str(heavy_team)]['status'] == 'stable'
    assert body['bullpen_environment']['by_team_id'][str(elevated_team)]['primary_pressure_sources'] == [
        'capacity_loss'
    ]
    assert body['bullpen_environment']['by_team_id'][str(heavy_team)]['primary_pressure_sources'] == [
        'rotation_support_pressure'
    ]


def test_four_beat_story_keeps_intelligence_layers_independent_from_rule_selection():
    pitchers = [_story_pitcher(idx) for idx in range(1, 7)]
    records = [_story_record(pitcher) for pitcher in pitchers]
    logs_by_pitcher = {
        pitcher.id: [_story_log(pitcher.id, 1, 10)]
        for pitcher in pitchers
    }
    capacity = {
        'capability': CAPACITY_CAPABILITY,
        'capacity_loss': {'status': 'elevated', 'summary': 'capacity sentinel'},
        'trust_capacity_loss': {'status': 'clear'},
    }
    rotation = {
        'capability': ROTATION_CAPABILITY,
        'status': 'heavy_pressure',
        'summary': 'rotation sentinel',
    }
    stability = {
        'capability': STABILITY_CAPABILITY,
        'status': 'moderate_churn',
        'summary': 'stability sentinel',
    }
    environment = {
        'capability': ENVIRONMENT_CAPABILITY,
        'status': 'multi_source_pressure',
        'summary': 'environment sentinel',
    }
    base_team_inputs = TeamInputs(
        team={'team_id': 1, 'team_name': 'Story Team', 'team_abbreviation': 'STY'},
        records=records,
        logs_by_pitcher=logs_by_pitcher,
        reference_date=date(2026, 6, 18),
    )
    intelligence_team_inputs = TeamInputs(
        team=base_team_inputs.team,
        records=records,
        logs_by_pitcher=logs_by_pitcher,
        reference_date=base_team_inputs.reference_date,
        capacity_by_team={1: capacity},
        rotation_support_by_team={1: rotation},
        bullpen_stability_by_team={1: stability},
        bullpen_environment_by_team={1: environment},
    )

    base_eval = evaluate_team_rules(base_team_inputs)
    intelligence_eval = evaluate_team_rules(intelligence_team_inputs)
    base_rules = [
        (item['rule_key'], item['status'], item['can_fire'], item.get('conditions'))
        for item in base_eval['evaluations']
    ]
    intelligence_rules = [
        (item['rule_key'], item['status'], item['can_fire'], item.get('conditions'))
        for item in intelligence_eval['evaluations']
    ]

    assert intelligence_rules == base_rules
    assert {item['rule_key'] for item in intelligence_eval['evaluations']} == {
        RULE_STRESS_TRANSFER,
        RULE_PRESSURE_DISTRIBUTION,
        RULE_SUSTAINABILITY_QUESTION,
        RULE_HIDDEN_CAPACITY_LOSS,
        RULE_SPECIAL_SITUATION,
    }

    inputs = compute_team_story_inputs(intelligence_team_inputs)
    story = assemble_story(RULE_PRESSURE_DISTRIBUTION, inputs)

    assert story['computed']['capacity_intelligence'] == capacity
    assert story['computed']['rotation_support_pressure'] == rotation
    assert story['computed']['bullpen_stability'] == stability
    assert story['computed']['bullpen_environment'] == environment
    assert story['slot_sources']['capacity_intelligence'] == CAPACITY_CAPABILITY
    assert story['slot_sources']['rotation_support_pressure'] == ROTATION_CAPABILITY
    assert story['slot_sources']['bullpen_stability'] == STABILITY_CAPABILITY
    assert story['slot_sources']['bullpen_environment'] == ENVIRONMENT_CAPABILITY
    assert story['computed']['why_context']['applied'] is False
    text = _story_text(story).lower()
    for unsupported_claim in (
        'capacity sentinel',
        'rotation sentinel',
        'stability sentinel',
        'environment sentinel',
        'heavy_pressure',
        'moderate_churn',
        'multi_source_pressure',
    ):
        assert unsupported_claim not in text
