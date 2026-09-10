from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from models.daily_closure import BaseballDateClosure
from models.repair_request import RepairRequest
from models.sync_certification import (
    SyncCertificationCheck, SyncCertificationRun, SyncLegacyTransitionState,
)
from models.sync_job import SyncJob
from scripts.run_sync_pipeline_certification import _parse_migration_heads
from services.sync_pipeline_certification import (
    ActivationControls, GATES, certification_checks, classify_operational_health,
    collect_operational_health, evaluate_certification, legacy_responsibility_map,
    persist_certification_report, persist_legacy_responsibility_map,
    validate_activation_controls,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


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


def _passing_evidence(*, warning_gate=None):
    evidence = {}
    for key in GATES:
        if key == 'A':
            continue
        evidence[key] = {
            'check_key': f'{key.lower()}_proof',
            'status': 'warning' if key == warning_gate else 'passing',
            'critical': key != warning_gate,
            'summary': f'Gate {key} proof recorded.',
            'evidence': {'fixture': True},
        }
    return evidence


def test_migration_head_parser_ignores_application_startup_noise():
    output = '[scheduler] AUTO_SYNC disabled\nc9d4e6f8a1b2 (head)\n'

    assert _parse_migration_heads(output) == ['c9d4e6f8a1b2']


def test_activation_controls_default_fail_closed():
    controls = ActivationControls.from_environment({})
    assert controls == ActivationControls()
    assert validate_activation_controls(controls) == ()


def test_activation_controls_reject_duplicate_writers_and_shadow_publication():
    controls = ActivationControls(
        pipeline_enabled=True, shadow_mode=True, publication_enabled=True,
        morning_enabled=True, closure_enabled=True,
        legacy_publication_enabled=True, legacy_schedulers_enabled=True,
    )
    violations = validate_activation_controls(controls)
    assert 'shadow_mode_cannot_publish' in violations
    assert 'uncontrolled_duplicate_publication_writers' in violations


def test_disabled_parent_rejects_enabled_child_flags():
    controls = ActivationControls(publication_enabled=True)
    assert validate_activation_controls(controls) == (
        'SYNC_PIPELINE_PUBLICATION_ENABLED_requires_SYNC_PIPELINE_ENABLED',
        'uncontrolled_duplicate_publication_writers',
    )


def test_every_gate_is_represented_and_missing_proof_is_no_go():
    checks = certification_checks(
        migration_heads=['c9d4e6f8a1b2'], integration_sha_matches=True,
        controls=ActivationControls(), evidence={},
    )
    result = evaluate_certification(checks)
    assert set(result['gate_statuses']) == set(GATES)
    assert result['gate_statuses']['A'] == 'passing'
    assert all(result['gate_statuses'][key] == 'blocked' for key in GATES if key != 'A')
    assert result['verdict'] == 'NO-GO'


def test_warning_only_condition_can_remain_go_with_caveat():
    checks = certification_checks(
        migration_heads=['c9d4e6f8a1b2'], integration_sha_matches=True,
        controls=ActivationControls(), evidence=_passing_evidence(warning_gate='J'),
    )
    result = evaluate_certification(checks)
    assert result['verdict'] == 'GO'
    assert result['gate_statuses']['J'] == 'warning'
    assert result['warnings']


def test_critical_failure_is_no_go():
    evidence = _passing_evidence()
    evidence['H'] = {
        'check_key': 'mixed_generation', 'status': 'failed', 'critical': True,
        'summary': 'A mixed-generation reader remains.',
    }
    result = evaluate_certification(certification_checks(
        migration_heads=['c9d4e6f8a1b2'], integration_sha_matches=True,
        controls=ActivationControls(), evidence=evidence,
    ))
    assert result['verdict'] == 'NO-GO'
    assert result['gate_statuses']['H'] == 'failed'


@pytest.mark.parametrize(
    ('signals', 'expected'),
    (({}, 'healthy'), ({'retry_wait_jobs': 1}, 'degraded'), ({'dead_jobs': 1}, 'blocked')),
)
def test_operational_health_vocabulary(signals, expected):
    assert classify_operational_health(signals)['status'] == expected


def test_continuous_warning_observations_are_visible_without_degrading_health():
    health = classify_operational_health({
        'continuous_warning_observations': 4,
        'continuous_stale_observations': 3,
        'continuous_safe_rejections': 1,
    })
    assert health['status'] == 'healthy'
    assert health['signals']['continuous_stale_observations'] == 3


def test_continuous_unresolved_required_work_degrades_health():
    health = classify_operational_health({'continuous_unhealthy_runs': 1})
    assert health['status'] == 'degraded'
    assert health['degraded_conditions'] == [
        'continuous_update_required_obligation_unresolved'
    ]


def test_database_health_detects_stale_dead_and_blocked_obligations(app):
    now = datetime(2026, 9, 9, 12)
    db.session.add(SyncJob(
        job_name='test_dead', job_family='test', lane='internal', scope_key='dead',
        product_date=date(2026, 9, 9), status='dead', attempts=3, max_attempts=3,
        priority=100,
    ))
    db.session.add(SyncJob(
        job_name='test_stale', job_family='test', lane='internal', scope_key='stale',
        product_date=date(2026, 9, 9), status='running', attempts=1, max_attempts=3,
        priority=100, lease_until=now - timedelta(minutes=1),
    ))
    db.session.add(BaseballDateClosure(
        baseball_date=date(2026, 9, 8), status='blocked',
        closure_schema_version='daily-closure-v1',
        recheck_policy_version='closure-recheck-v1',
    ))
    db.session.add(RepairRequest(
        request_key='request-1', request_fingerprint='r' * 64,
        schema_version='repair-request-v1', plan_version='repair-plan-v1',
        mode='targeted_repair', status='blocked', requested_scope_type='game',
        scope_json={'game_pk': 1}, baseball_date_start=date(2026, 9, 8),
        baseball_date_end=date(2026, 9, 8), source_domain='final_game',
        reason='test', requested_by='test', trigger_type='test', dry_run=True,
        correlation_id='correlation-1',
    ))
    db.session.commit()
    health = collect_operational_health(now=now)
    assert health['status'] == 'blocked'
    assert health['signals']['dead_jobs'] == 1
    assert health['signals']['stale_leases'] == 1
    assert health['signals']['blocked_closures'] == 1
    assert health['signals']['blocked_repairs'] == 1
    assert health['signals']['missing_roster_authority_teams'] == 30
    assert health['signals']['current_publication_missing'] == 1


def test_legacy_map_covers_every_active_responsibility_and_defers_publication(app):
    rows = legacy_responsibility_map()
    keys = {row['responsibility_key'] for row in rows}
    assert {
        'schedule_game_state', 'live_game_delta', 'final_game_reconciliation',
        'roster_transactions', 'impact_planning', 'derived_intelligence',
        'publication', 'morning_reconciliation', 'nightly_closure',
        'repair_backfill', 'request_time_writes', 'scheduler_authority',
    } <= keys
    publication = next(row for row in rows if row['responsibility_key'] == 'publication')
    assert publication['retirement_type'] == 'DEFER_RETIREMENT'
    assert persist_legacy_responsibility_map()
    assert persist_legacy_responsibility_map() == ()
    assert SyncLegacyTransitionState.query.count() == len(rows)


def test_certification_evidence_is_immutable_and_idempotent(app):
    controls = ActivationControls()
    report = evaluate_certification(certification_checks(
        migration_heads=['c9d4e6f8a1b2'], integration_sha_matches=True,
        controls=controls, evidence=_passing_evidence(),
    ))
    first = persist_certification_report(
        report, integration_commit_sha='a' * 40, migration_head='c9d4e6f8a1b2',
        environment='test', controls=controls,
    )
    second = persist_certification_report(
        report, integration_commit_sha='a' * 40, migration_head='c9d4e6f8a1b2',
        environment='test', controls=controls,
    )
    assert first.id == second.id
    assert first.verdict == 'GO'
    assert SyncCertificationRun.query.count() == 1
    assert SyncCertificationCheck.query.filter_by(certification_run_id=first.id).count() == len(report['checks'])
