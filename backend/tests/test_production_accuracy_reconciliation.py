from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from services import production_accuracy_reconciliation as audit


SNAPSHOT_ID = 1672


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
            },
            'teams': teams,
        },
    )


def test_team_state_reconciliation_requires_exactly_30_and_recomputes_contract_a(monkeypatch):
    proof = _proof_row([_proof_team(team_id) for team_id in range(100, 130)])
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: proof)
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result == {
        'checked': 30, 'correct': 30, 'incorrect': 0,
        'unproven': 0, 'status': audit.PASS,
    }
    assert mismatches == []


def test_team_state_reconciliation_detects_corrupted_published_state(monkeypatch):
    teams = [_proof_team(team_id) for team_id in range(100, 130)]
    teams[4]['final_team_state']['readiness_status_code'] = 'operationally_stressed'
    monkeypatch.setattr(audit, 'load_durable_proof', lambda snapshot_id: _proof_row(teams))
    mismatches = []
    result = audit._team_states(_snapshot(), mismatches)
    assert result['status'] == audit.FAIL
    assert result['incorrect'] == 1
    assert mismatches[0]['domain'] == 'team_states.contract_a'


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
