from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import production_accuracy_reconciliation as audit
from services.mlb_club_directory import MLB_TEAM_IDS
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


SNAPSHOT_ID = 1672


@pytest.fixture
def database_app():
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


def _snapshot():
    return SimpleNamespace(
        id=SNAPSHOT_ID,
        sync_run_id=91,
        status='ready',
        is_published=True,
        published_at=datetime(2026, 8, 31, 10, 30),
        data_through=date(2026, 8, 31),
        availability_reference_date=date(2026, 9, 1),
        snapshot_generated_at=datetime(2026, 8, 31, 10, 29),
        source='external_schedule',
        payload_version=7,
        payload={},
    )


def _thresholds():
    return {
        'clean_share_fresh_min': [2, 3],
        'severe_share_vulnerable_min': [1, 3],
        'clean_count_fresh_min': 5,
        'severe_count_fresh_max': 1,
        'clean_count_vulnerable_max': 2,
    }


def _proof_team(team_id):
    return {
        'team_id': team_id,
        'active_pitcher_count': 7,
        'partition': {
            'clean_count': 5,
            'moderate_count': 1,
            'severe_count': 1,
            'unknown_count': 0,
        },
        'thresholds_applied': _thresholds(),
        'decisive_rule': 'fresh_coverage',
        'method_version': 'v3_phase_5',
        'final_team_state': {
            'readiness_status_code': 'operationally_stable',
            'published_public_state': 'fresh',
        },
    }


def _proof_row(teams):
    return SimpleNamespace(
        snapshot_id=SNAPSHOT_ID,
        data_through=date(2026, 8, 31),
        proof={
            'proof_generated_at': '2026-08-31T10:31:00Z',
            'publication': {
                'dashboard_snapshot_id': SNAPSHOT_ID,
                'sync_run_id': 91,
                'data_through': '2026-08-31',
                'expected_method_version': 'v3_phase_5',
            },
            'teams': teams,
            'overall_verdict': 'PASS',
        },
        overall_verdict='PASS',
        captured_team_count=30,
        method_version='v3_phase_5',
    )


def test_team_state_reconciliation_requires_exactly_30_and_recomputes_contract_a(monkeypatch):
    proof = _proof_row([_proof_team(team_id) for team_id in MLB_TEAM_IDS])
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: proof)
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result == {
        'checked': 30, 'correct': 30, 'incorrect': 0,
        'unproven': 0, 'status': audit.PASS,
    }
    assert mismatches == []


def test_team_state_reconciliation_detects_corrupted_published_state(monkeypatch):
    teams = [_proof_team(team_id) for team_id in MLB_TEAM_IDS]
    teams[4]['final_team_state']['readiness_status_code'] = 'operationally_stressed'
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: _proof_row(teams))
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result['status'] == audit.FAIL
    assert result['incorrect'] == 1
    assert mismatches[0]['domain'] == 'team_states.contract_a'


@pytest.mark.parametrize('shape', ('missing', 'duplicate', 'unexpected'))
def test_team_state_reconciliation_rejects_invalid_mlb_team_set(monkeypatch, shape):
    teams = [_proof_team(team_id) for team_id in MLB_TEAM_IDS]
    if shape == 'missing':
        teams.pop()
    elif shape == 'duplicate':
        teams[-1] = deepcopy(teams[0])
    else:
        teams[-1]['team_id'] = 999
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: _proof_row(teams))
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result['status'] == audit.FAIL
    assert any(item['domain'] == 'team_states.team_set' for item in mismatches)


def test_team_state_reconciliation_rejects_contradictory_persisted_metadata(monkeypatch):
    row = _proof_row([_proof_team(team_id) for team_id in MLB_TEAM_IDS])
    row.overall_verdict = 'FAIL'
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: row)
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result['status'] == audit.FAIL
    assert any(
        item['domain'] == 'team_states.proof_publication_identity'
        for item in mismatches
    )


def test_team_state_reconciliation_accepts_governed_withholding(monkeypatch):
    teams = [_proof_team(team_id) for team_id in MLB_TEAM_IDS]
    withheld = teams[-1]
    withheld['active_pitcher_count'] = None
    withheld['partition'] = {
        'clean_count': None,
        'moderate_count': None,
        'severe_count': None,
        'unknown_count': None,
    }
    withheld['decisive_rule'] = 'data_limited'
    withheld['partition_invariant_state'] = 'not_applicable'
    withheld['final_team_state'] = {
        'readiness_status_code': 'data_limited',
        'published_public_state': None,
    }
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: _proof_row(teams))
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result['status'] == audit.PASS
    assert mismatches == []


def test_missing_required_proof_is_a_hard_error(monkeypatch):
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: None)
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result['status'] == audit.FAIL
    assert result['incorrect'] == 30
    assert mismatches[0]['domain'] == 'team_states.required_proof_missing'


def test_workload_reconciliation_detects_corrupted_fixture(monkeypatch):
    snapshot = _snapshot()
    record = {
        'pitcher_id': 42,
        'last_workload_appearance': {'game_date': '2026-08-31', 'pitches': 12},
        'workload_facts': {
            'appearances_last_7': 1,
            'appearances_last_14': 1,
            'pitches_last_7_days': 12,
            'innings_last_7_days': 1.0,
            'days_since_last_appearance': 0,
        },
        'availability': {
            'availability_status': 'Available',
            'inputs': {'days_rest': 1},
        },
    }
    monkeypatch.setattr(audit, '_team_packages', lambda snap: {
        '110': {'default_pitcher_ids': [42], 'records': [record]},
    })
    log = SimpleNamespace(
        id=5, pitcher_id=42, game_date=date(2026, 8, 31), mlb_game_pk=99,
        pitches_thrown=31, innings_pitched_outs=3,
    )
    monkeypatch.setattr(audit, '_record_logs', lambda pitcher_ids, through: {42: [log]})
    monkeypatch.setattr(audit, '_current_pitchers', lambda pitcher_ids: {
        42: SimpleNamespace(id=42, team_id=110, active=True),
    })
    monkeypatch.setattr(audit, '_score_for_record', lambda pitcher_id, row: None)
    mismatches = []
    domains = audit._membership_workload(snapshot, mismatches)
    assert domains['workload_values']['status'] == audit.FAIL
    assert domains['rest_patterns']['status'] == audit.FAIL
    assert {item['domain'] for item in mismatches} >= {
        'workload.last_workload_appearance',
        'workload.pitches_last_7_days',
        'rest.days_since_last_appearance',
    }


def _single_pitcher_membership_audit(
    monkeypatch, *, record, log, pitcher_team=110, score=None,
):
    monkeypatch.setattr(audit, '_team_packages', lambda snap: {
        '110': {'default_pitcher_ids': [42], 'records': [record]},
    })
    monkeypatch.setattr(audit, '_record_logs', lambda pitcher_ids, through: {42: [log]})
    monkeypatch.setattr(audit, '_current_pitchers', lambda pitcher_ids: {
        42: SimpleNamespace(id=42, team_id=pitcher_team, active=True),
    })
    monkeypatch.setattr(audit, '_score_for_record', lambda pitcher_id, row: score)
    monkeypatch.setattr(
        audit, '_score_reference_date',
        lambda stored_score: _snapshot().availability_reference_date,
    )
    mismatches = []
    return audit._membership_workload(_snapshot(), mismatches), mismatches


def _current_record(*, pitches=12, availability_status='Monitor'):
    return {
        'pitcher_id': 42,
        'last_workload_appearance': {
            'game_date': '2026-08-31',
            'pitches': pitches,
        },
        'workload_facts': {
            'appearances_last_7': 1,
            'appearances_last_14': 1,
            'pitches_last_7_days': pitches,
            'innings_last_7_days': 1.0,
            'days_since_last_appearance': 1,
        },
        'availability': {
            'availability_status': availability_status,
            'inputs': {
                'days_rest': 1,
                'freshness_state': 'fresh' if pitches is not None else 'incomplete',
                'latest_game_date': '2026-08-31',
                'reference_date': '2026-09-01',
            },
        },
    }


def test_reconciliation_detects_wrong_arm_read(monkeypatch):
    record = _current_record(availability_status='Available')
    log = SimpleNamespace(
        id=5, pitcher_id=42, game_date=date(2026, 8, 31), mlb_game_pk=99,
        pitches_thrown=12, innings_pitched_outs=3,
    )
    domains, mismatches = _single_pitcher_membership_audit(
        monkeypatch,
        record=record,
        log=log,
        score=SimpleNamespace(id=7, calculated_at=datetime(2026, 8, 31), raw_score=0.0),
    )
    assert domains['arm_reads']['status'] == audit.FAIL
    assert any(item['domain'] == 'arm_reads.classification' for item in mismatches)


def test_reconciliation_detects_wrong_bullpen_membership(monkeypatch):
    record = _current_record()
    log = SimpleNamespace(
        id=5, pitcher_id=42, game_date=date(2026, 8, 31), mlb_game_pk=99,
        pitches_thrown=12, innings_pitched_outs=3,
    )
    domains, mismatches = _single_pitcher_membership_audit(
        monkeypatch,
        record=record,
        log=log,
        pitcher_team=111,
        score=SimpleNamespace(id=7, calculated_at=datetime(2026, 8, 31), raw_score=0.0),
    )
    assert domains['bullpen_membership']['status'] == audit.FAIL
    assert any(
        item['domain'] == 'bullpen_membership.current_roster_authority'
        for item in mismatches
    )


def test_reconciliation_never_accepts_unknown_pitch_as_zero(monkeypatch):
    record = _current_record(pitches=None)
    record['workload_facts']['pitches_last_7_days'] = 0
    log = SimpleNamespace(
        id=5, pitcher_id=42, game_date=date(2026, 8, 31), mlb_game_pk=99,
        pitches_thrown=None, innings_pitched_outs=3,
    )
    domains, mismatches = _single_pitcher_membership_audit(
        monkeypatch,
        record=record,
        log=log,
        score=SimpleNamespace(id=7, calculated_at=datetime(2026, 8, 31), raw_score=0.0),
    )
    assert domains['workload_values']['status'] == audit.FAIL
    mismatch = next(
        item for item in mismatches
        if item['domain'] == 'workload.pitches_last_7_days'
    )
    assert mismatch['published_value'] == 0
    assert mismatch['recomputed_value'] is None


def test_team_aggregate_does_not_reassign_history_through_current_team(
    database_app, monkeypatch,
):
    pitcher = Pitcher(
        mlb_id=900042,
        full_name='Moved Reliever',
        team_id=146,
        team_name='Miami Marlins',
        team_abbreviation='MIA',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=990042,
        game_date=date(2026, 8, 30),
        game_type='R',
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=18,
        appearance_team_id=145,
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_source='test_game_side',
        appearance_team_reason='appearance_team_resolved_test',
    )
    db.session.add(log)
    db.session.commit()
    published_window = {
        'relief_appearances': 1,
        'pitchers_in_relief': 1,
        'pitches_total': 18,
        'appearances_with_pitches': 1,
    }
    monkeypatch.setattr(audit, '_team_packages', lambda snapshot: {
        '146': {
            'default_pitcher_ids': [],
            'records': [],
            'workload_windows': {
                'status': 'complete',
                'windows': {
                    'window_7': dict(published_window),
                    'window_14': dict(published_window),
                },
            },
        },
    })
    mismatches = []
    result = audit._team_aggregates(_snapshot(), mismatches)
    assert result['status'] == audit.FAIL
    assert all(item['team'] == 146 for item in mismatches)
    assert all(item['canonical_rows'] == [] for item in mismatches)
    assert any(
        item['domain'] == 'team_aggregates.workload_7d.relief_appearances'
        and item['published_value'] == 1
        and item['recomputed_value'] == 0
        for item in mismatches
    )


def test_stale_frozen_scores_use_their_own_canonical_reference_dates(monkeypatch):
    """Snapshot 1696's two exact discrepancy shapes remain independently provable."""
    snapshot = _snapshot()
    snapshot.id = 1696
    snapshot.data_through = date(2026, 8, 30)
    snapshot.availability_reference_date = date(2026, 8, 31)

    cases = {
        677: {
            'team_id': 145,
            'frozen_reference_date': date(2026, 7, 24),
            'score_id': 120842,
            'calculated_at': datetime(2026, 7, 24, 22, 34, 16),
            'published_appearances_14': 1,
            'published_days_rest': 14,
            'current_days_rest': 52,
            'logs': [
                (42893, date(2026, 7, 10), 30, 6),
                (42784, date(2026, 7, 9), 13, 3),
            ],
        },
        680: {
            'team_id': 146,
            'frozen_reference_date': date(2025, 9, 29),
            'score_id': 407,
            'calculated_at': datetime(2026, 6, 15, 20, 29, 49),
            'published_appearances_14': 2,
            'published_days_rest': 9,
            'current_days_rest': 345,
            'logs': [
                (30380, date(2025, 9, 20), 17, 3),
                (30379, date(2025, 9, 16), 27, 3),
                (30378, date(2025, 9, 14), 19, 3),
            ],
        },
    }
    packages = {}
    records = {}
    logs_by_pitcher = {}
    scores = {}
    for pitcher_id, case in cases.items():
        facts = {
            'calculated_at': case['calculated_at'].isoformat(),
            'appearances_last_7': 0,
            'appearances_last_14': case['published_appearances_14'],
            'pitches_last_7_days': 0,
            'innings_last_7_days': 0.0,
            'days_since_last_appearance': case['published_days_rest'],
        }
        latest_date = case['logs'][0][1]
        latest_pitches = case['logs'][0][2]
        record = {
            'pitcher_id': pitcher_id,
            'last_workload_appearance': {
                'game_date': latest_date.isoformat(),
                'pitches': latest_pitches,
            },
            'workload_facts': facts,
            'availability': {
                'availability_status': 'Monitor',
                'inputs': {
                    'days_rest': case['current_days_rest'],
                    'freshness_state': 'stale',
                    'latest_game_date': latest_date.isoformat(),
                    'reference_date': '2026-08-31',
                },
            },
        }
        records[pitcher_id] = record
        packages[str(case['team_id'])] = {
            'default_pitcher_ids': [pitcher_id],
            'records': [record],
        }
        logs_by_pitcher[pitcher_id] = [
            SimpleNamespace(
                id=row_id,
                pitcher_id=pitcher_id,
                game_date=game_date,
                mlb_game_pk=row_id + 700000,
                pitches_thrown=pitches,
                innings_pitched_outs=outs,
                innings_pitched=outs / 3.0,
                created_at=case['calculated_at'] - timedelta(minutes=1),
            )
            for row_id, game_date, pitches, outs in case['logs']
        ]
        scores[pitcher_id] = SimpleNamespace(
            id=case['score_id'],
            pitcher_id=pitcher_id,
            calculated_at=case['calculated_at'],
            raw_score=1.0,
        )

    monkeypatch.setattr(audit, '_team_packages', lambda snap: packages)
    monkeypatch.setattr(audit, '_record_logs', lambda pitcher_ids, through: logs_by_pitcher)
    monkeypatch.setattr(audit, '_current_pitchers', lambda pitcher_ids: {
        pitcher_id: SimpleNamespace(
            id=pitcher_id, team_id=case['team_id'], active=True,
        )
        for pitcher_id, case in cases.items()
    })
    monkeypatch.setattr(
        audit, '_score_for_record', lambda pitcher_id, row: scores[pitcher_id],
    )
    monkeypatch.setattr(
        audit,
        '_score_reference_date',
        lambda score: cases[score.pitcher_id]['frozen_reference_date'],
    )

    mismatches = []
    governed = []
    domains = audit._membership_workload(snapshot, mismatches, governed)

    assert domains['workload_values']['status'] == audit.PASS
    assert domains['rest_patterns']['status'] == audit.PASS
    assert mismatches == []
    assert [item['classification'] for item in governed] == [
        audit.HISTORICAL_METHOD_DIFFERENCE,
        audit.HISTORICAL_METHOD_DIFFERENCE,
    ]
    assert {
        (item['pitcher'], item['frozen_reference_date'])
        for item in governed
    } == {(677, '2026-07-24'), (680, '2025-09-29')}

    records[677]['workload_facts']['appearances_last_14'] = 2
    records[677]['workload_facts']['days_since_last_appearance'] = 15
    mismatches = []
    governed = []
    domains = audit._membership_workload(snapshot, mismatches, governed)

    assert domains['workload_values']['status'] == audit.FAIL
    assert domains['rest_patterns']['status'] == audit.FAIL
    mismatches_by_domain = {item['domain']: item for item in mismatches}
    assert mismatches_by_domain['workload.appearances_last_14']['published_value'] == 2
    assert mismatches_by_domain['workload.appearances_last_14']['recomputed_value'] == 1
    assert mismatches_by_domain['rest.days_since_last_appearance']['published_value'] == 15
    assert mismatches_by_domain['rest.days_since_last_appearance']['recomputed_value'] == 14


def test_frozen_recomputation_excludes_rows_created_after_score_calculation():
    calculated_at = datetime(2026, 7, 24, 22, 34, 16)
    score = SimpleNamespace(calculated_at=calculated_at)
    rows = [
        SimpleNamespace(
            id=1, game_date=date(2026, 7, 10), pitches_thrown=30,
            innings_pitched_outs=6, created_at=calculated_at-timedelta(minutes=1),
        ),
        SimpleNamespace(
            id=2, game_date=date(2026, 7, 20), pitches_thrown=15,
            innings_pitched_outs=3, created_at=calculated_at+timedelta(minutes=1),
        ),
    ]

    available = audit._rows_available_at_score_calculation(rows, score)
    recomputed = audit._recomputed_frozen_score_workload(
        available, date(2026, 7, 24),
    )

    assert [row.id for row in available] == [1]
    assert recomputed['appearances_last_14'] == 1
    assert recomputed['days_since_last_appearance'] == 14


@pytest.mark.parametrize(
    ('method_version', 'anchor', 'reason'),
    [
        (None, None, 'historical_reference_anchor_unavailable'),
        ('fatigue_score_workload_windows_v2', date(2026, 7, 24),
         'historical_workload_method_incompatible'),
    ],
)
def test_unreconstructible_historical_workload_is_unproven(
    monkeypatch, method_version, anchor, reason,
):
    snapshot = _snapshot()
    record = {
        'pitcher_id': 42,
        'last_workload_appearance': {'game_date': '2026-07-10', 'pitches': 12},
        'workload_facts': {
            'calculated_at': None,
            'method_version': method_version,
            'appearances_last_7': 1,
            'appearances_last_14': 1,
            'pitches_last_7_days': 12,
            'innings_last_7_days': 1.0,
            'days_since_last_appearance': 0,
        },
        'availability': {
            'availability_status': 'Monitor',
            'inputs': {'freshness_state': 'stale'},
        },
    }
    log = SimpleNamespace(
        id=5, pitcher_id=42, game_date=date(2026, 7, 10), mlb_game_pk=99,
        pitches_thrown=12, innings_pitched_outs=3,
    )
    score = SimpleNamespace(id=7, calculated_at=None, raw_score=0.0)
    monkeypatch.setattr(audit, '_team_packages', lambda snap: {
        '110': {'default_pitcher_ids': [42], 'records': [record]},
    })
    monkeypatch.setattr(audit, '_record_logs', lambda pitcher_ids, through: {42: [log]})
    monkeypatch.setattr(audit, '_current_pitchers', lambda pitcher_ids: {
        42: SimpleNamespace(id=42, team_id=110, active=True),
    })
    monkeypatch.setattr(audit, '_score_for_record', lambda pitcher_id, row: score)
    monkeypatch.setattr(audit, '_score_reference_date', lambda stored_score: anchor)

    mismatches = []
    domains = audit._membership_workload(snapshot, mismatches)

    assert domains['workload_values']['status'] == audit.UNPROVEN
    assert domains['workload_values']['unproven'] == 4
    assert domains['rest_patterns']['status'] == audit.UNPROVEN
    assert domains['rest_patterns']['unproven'] == 1
    issue = next(
        item for item in mismatches
        if item['domain'] == 'workload.historical_reference_unproven'
    )
    assert issue['recomputed_value'] == audit.HISTORICAL_REFERENCE_UNPROVEN
    assert issue['likely_originating_layer'] == reason


def test_served_read_model_detects_publication_generation_mixing(monkeypatch):
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: None)
    snapshot = _snapshot()
    snapshot.payload = {
        'publication_authority': {'snapshot_id': SNAPSHOT_ID + 1},
        audit.public_serving_authority.TEAM_BOARD_PACKAGE_KEY: {
            'contract': audit.public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
            'data_through': snapshot.data_through.isoformat(),
        },
    }
    mismatches = []
    result = audit._served_models(snapshot, mismatches)
    assert result['status'] == audit.FAIL
    assert mismatches[0]['domain'] == 'served_read_models.publication_authority_snapshot_id'


def _patch_internal_pass(monkeypatch):
    passed = audit._domain(checked=1, correct=1)
    monkeypatch.setattr(audit, '_publication_coherence', lambda *args: deepcopy(passed))
    monkeypatch.setattr(audit, '_game_ledger', lambda *args: (deepcopy(passed), deepcopy(passed)))
    monkeypatch.setattr(audit, '_membership_workload', lambda *args: {
        name: deepcopy(passed)
        for name in ('bullpen_membership', 'workload_values', 'rest_patterns', 'arm_reads')
    })
    monkeypatch.setattr(audit, '_team_states', lambda *args: deepcopy(passed))
    monkeypatch.setattr(audit, '_team_aggregates', lambda *args: deepcopy(passed))
    monkeypatch.setattr(audit, '_served_models', lambda *args: deepcopy(passed))


@pytest.mark.parametrize(
    ('case', 'domain_name', 'mismatch_domain'),
    [
        ('wrong_workload', 'workload_values', 'workload.pitches_last_7_days'),
        ('wrong_rest', 'rest_patterns', 'rest.days_since_last_appearance'),
        ('wrong_arm', 'arm_reads', 'arm_reads.classification'),
        ('wrong_team_state', 'team_states', 'team_states.contract_a'),
        ('missing_team_state_proof', 'team_states', 'team_states.required_proof_missing'),
        ('contradictory_team_state_proof', 'team_states', 'team_states.proof_publication_identity'),
        ('mixed_snapshot_ids', 'publication_coherence', 'publication_coherence.snapshot_not_trusted_publication'),
        ('missing_team', 'team_states', 'team_states.team_set'),
        ('duplicate_team', 'team_states', 'team_states.team_set'),
        ('wrong_membership', 'bullpen_membership', 'bullpen_membership.current_roster_authority'),
        ('current_team_reassigned_history', 'team_aggregates', 'team_aggregates.workload_7d.relief_appearances'),
        ('unknown_pitch_as_zero', 'workload_values', 'workload.pitches_last_7_days'),
        ('served_identity_mismatch', 'served_read_models', 'served_read_models.publication_authority_snapshot_id'),
    ],
)
def test_each_material_negative_case_forces_not_verified(
    monkeypatch, case, domain_name, mismatch_domain,
):
    _patch_internal_pass(monkeypatch)
    failed = audit._domain(checked=1, incorrect=1)
    evidence = audit._mismatch(
        mismatch_domain,
        SNAPSHOT_ID,
        'published_fixture_value',
        'independent_recomputed_value',
        team=110,
        pitcher=42,
        rows=[5],
        method_version='fixture_method_v1',
        likely_layer=case,
    )

    if domain_name in {
        'bullpen_membership', 'workload_values', 'rest_patterns', 'arm_reads',
    }:
        passed = audit._domain(checked=1, correct=1)

        def membership(_snapshot, mismatches, *_args):
            mismatches.append(evidence)
            return {
                name: deepcopy(failed if name == domain_name else passed)
                for name in (
                    'bullpen_membership', 'workload_values',
                    'rest_patterns', 'arm_reads',
                )
            }

        monkeypatch.setattr(audit, '_membership_workload', membership)
    else:
        target = {
            'publication_coherence': '_publication_coherence',
            'team_states': '_team_states',
            'team_aggregates': '_team_aggregates',
            'served_read_models': '_served_models',
        }[domain_name]

        def detector(_snapshot, mismatches):
            mismatches.append(evidence)
            return deepcopy(failed)

        monkeypatch.setattr(audit, target, detector)

    external_pass = {
        name: audit._domain(checked=1, correct=1)
        for name in ('games', 'pitching_lines', 'roster_authority')
    }
    report = audit.reconcile_publication(
        _snapshot(), external_domains=external_pass,
    )
    assert report['verdict'] == audit.NOT_VERIFIED
    assert evidence in report['mismatches']
    assert evidence['published_value'] != evidence['recomputed_value']
    assert evidence['canonical_rows'] == [5]


def test_verdict_logic_verified_conditional_and_not_verified(monkeypatch):
    _patch_internal_pass(monkeypatch)
    external_pass = {name: audit._domain(checked=1, correct=1) for name in ('games', 'pitching_lines', 'roster')}
    assert audit.reconcile_publication(_snapshot(), external_domains=external_pass)['verdict'] == audit.VERIFIED
    assert audit.reconcile_publication(_snapshot())['verdict'] == audit.CONDITIONALLY_VERIFIED
    assert audit.reconcile_publication(_snapshot(), external_required=True)['verdict'] == audit.NOT_VERIFIED


def test_console_and_json_shape_never_claim_zero_mismatches_for_zero_mlb_comparisons():
    from scripts.production_accuracy_reconciliation import render_console

    report = {
        'snapshot_id': SNAPSHOT_ID,
        'data_through': '2026-08-31',
        'verdict': audit.CONDITIONALLY_VERIFIED,
        'domains': {'games': audit._domain(checked=1, correct=1)},
        'external_mlb': audit._external_unproven('network unavailable'),
        'mismatches': [],
    }
    text = render_console(report)
    assert '0 compared; 1 unproven' in text
    assert 'mismatches: 0' not in text.lower()
    assert report['snapshot_id'] == SNAPSHOT_ID
    assert report['external_mlb']['games']['status'] == audit.UNPROVEN


def test_console_states_when_external_truth_was_explicitly_skipped():
    from scripts.production_accuracy_reconciliation import render_console

    report = {
        'snapshot_id': SNAPSHOT_ID,
        'data_through': '2026-08-31',
        'verdict': audit.CONDITIONALLY_VERIFIED,
        'domains': {},
        'external_mlb': audit._external_unproven('skipped by --skip-mlb'),
        'external_evidence_mode': 'skipped',
    }
    assert 'External truth was not checked (--skip-mlb).' in render_console(report)


def test_cli_rejects_require_and_skip_mlb_together():
    from scripts.production_accuracy_reconciliation import _args

    with pytest.raises(SystemExit):
        _args(['--snapshot-id', str(SNAPSHOT_ID), '--require-mlb', '--skip-mlb'])
