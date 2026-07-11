import ast
import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask

import models.dashboard_snapshot  # noqa: F401
import models.sync_run  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import dashboard_snapshot
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE = '/api/system/internal/snapshot-audit'
ADMIN_HEADERS = {ADMIN_TOKEN_HEADER: 'admin-secret'}


@pytest.fixture
def app():
    from api.system import system_bp

    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    flask_app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    db.init_app(flask_app)
    flask_app.register_blueprint(system_bp, url_prefix='/api/system')

    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def client(app):
    return app.test_client()


def _slate_coverage(ref):
    return {
        'slate_date': ref.isoformat(),
        'games_scheduled': 0,
        'games_final': 0,
        'games_fully_ingested': 0,
        'games_incomplete': 0,
        'games_failed': 0,
        'games_postponed': 0,
        'games_suspended': 0,
        'games_included': 0,
        'validations_passed': True,
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'reason_codes': ['no_scheduled_games', 'slate_complete'],
        'degradation_reasons': [],
        'marker_counts': {
            'fully_processed': 0,
            'incomplete': 0,
            'failed': 0,
            'missing': 0,
        },
    }


def _payload(
    ref,
    *,
    state='insufficient_context',
    reason_codes=None,
    limitations=None,
    what_changed_overrides=None,
):
    what_changed = {
        'state': state,
        'reason_codes': list(reason_codes or ['stored_reason']),
        'limitations': list(limitations or ['Stored comparison limitation.']),
        'ignored_large_field': {'not': 'returned'},
    }
    what_changed.update(what_changed_overrides or {})
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': datetime(2026, 7, ref.day, 12, 0, 0).isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'freshness': {
            'data_through': ref.isoformat(),
            'availability_reference_date': ref.isoformat(),
            'reference_date': ref.isoformat(),
            'sync_status': 'success',
            'validations_passed': True,
            'complete_enough_to_publish': True,
            'slate_coverage': _slate_coverage(ref),
            'reason_codes': ['stored_freshness_reason'],
            'limitations': ['Stored freshness limitation.'],
        },
        'what_changed_since_yesterday': what_changed,
    }


def _sync_run(ref, *, job_name='phase0h_internal_snapshot_audit_test'):
    row = SyncRun(
        job_name=job_name,
        started_at=datetime(2026, 7, ref.day, 11, 59, 0),
        completed_at=datetime(2026, 7, ref.day, 12, 0, 0),
        status='success',
        stage='published',
        source='phase0h_test',
        latest_game_date=ref,
        latest_workload_date=ref,
        latest_fatigue_calculated_at=datetime(2026, 7, ref.day, 12, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _snapshot(
    ref,
    *,
    sync_run=None,
    status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
    is_published=True,
    generated_offset_minutes=0,
    published_at=None,
    payload=None,
    payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
    source='phase0h_test',
):
    run = sync_run or _sync_run(ref)
    row = DashboardSnapshot(
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=status,
        is_published=is_published,
        published_at=(
            published_at
            if published_at is not None
            else (
                datetime(2026, 7, ref.day, 12, 5, 0)
                + timedelta(minutes=generated_offset_minutes)
                if is_published
                else None
            )
        ),
        payload=payload if payload is not None else _payload(ref),
        payload_version=payload_version,
        data_through=ref,
        availability_reference_date=ref,
        snapshot_generated_at=datetime(2026, 7, ref.day, 12, 0, 0) + timedelta(minutes=generated_offset_minutes),
        source=source,
        error_message=None if status == dashboard_snapshot.SNAPSHOT_STATUS_READY else 'pending_review',
    )
    db.session.add(row)
    db.session.flush()
    if is_published:
        run.published_dashboard_snapshot_id = row.id
    return row


def _entry(payload, snapshot_id):
    return next(row for row in payload['recent_snapshots'] if row['id'] == snapshot_id)


def test_snapshot_audit_requires_admin_token(app, client):
    response = client.get(ROUTE)
    assert response.status_code == 401

    wrong = client.get(ROUTE, headers={ADMIN_TOKEN_HEADER: 'wrong'})
    assert wrong.status_code == 401

    allowed = client.get(ROUTE, headers=ADMIN_HEADERS)
    assert allowed.status_code == 200


def test_snapshot_audit_quotes_stored_snapshot_trust_state(app, client):
    with app.app_context():
        baseline = _snapshot(date(2026, 7, 4), generated_offset_minutes=1)
        current = _snapshot(
            date(2026, 7, 5),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 5),
                state='changes_detected',
                reason_codes=['stored_current_reason'],
                limitations=['Stored current limitation.'],
            ),
        )
        pending = _snapshot(
            date(2026, 7, 6),
            status=dashboard_snapshot.SNAPSHOT_STATUS_PENDING,
            is_published=False,
            generated_offset_minutes=3,
        )
        db.session.commit()
        baseline_id = baseline.id
        current_id = current.id
        pending_id = pending.id
        current_what_changed = current.payload['what_changed_since_yesterday']
        current_sync_run_id = current.sync_run_id
        current_trust = {
            'unavailable_reason': dashboard_snapshot.snapshot_unavailable_reason(current),
            'current_enough': dashboard_snapshot.snapshot_current_enough(current),
            'payload_version_valid': dashboard_snapshot.payload_version_valid(current),
        }

    response = client.get(ROUTE, headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['capability'] == 'phase0h_internal_snapshot_audit'
    assert payload['route_status'] == 'internal_admin_only'
    assert payload['internal_only_watermark'] == {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }
    assert payload['request'] == {'date': None, 'window_days': 7}
    assert payload['latest_snapshot']['id'] == pending_id
    assert payload['latest_snapshot']['status'] == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
    assert payload['latest_valid_snapshot_id'] == current_id
    assert payload['diagnostics']['snapshot_id'] == pending_id
    assert payload['sections_present']['latest_snapshot'] is True

    current_entry = _entry(payload, current_id)
    assert current_entry['snapshot_type'] == dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD
    assert current_entry['status'] == dashboard_snapshot.SNAPSHOT_STATUS_READY
    assert current_entry['is_published'] is True
    assert current_entry['data_through'] == '2026-07-05'
    assert current_entry['availability_reference_date'] == '2026-07-05'
    assert current_entry['payload_version'] == dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION
    assert current_entry['source'] == 'phase0h_test'
    assert current_entry['sync_run_id'] == current_sync_run_id
    assert current_entry['sync_run'] == {
        'id': current_sync_run_id,
        'job_name': 'phase0h_internal_snapshot_audit_test',
        'status': 'success',
        'stage': 'published',
        'failed_stage': None,
        'published_dashboard_snapshot_id': current_id,
    }
    assert current_entry['trust'] == current_trust
    assert current_entry['payload_freshness']['data_through'] == '2026-07-05'
    assert current_entry['payload_freshness']['availability_reference_date'] == '2026-07-05'
    assert current_entry['payload_freshness']['reason_codes'] == ['stored_freshness_reason']
    assert current_entry['payload_freshness']['slate_coverage'] == {
        'slate_date': '2026-07-05',
        'validations_passed': True,
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'reason_codes': ['no_scheduled_games', 'slate_complete'],
    }
    assert 'games_scheduled' not in current_entry['payload_freshness']['slate_coverage']
    assert current_entry['embedded_what_changed'] == {
        'state': current_what_changed['state'],
        'reason_codes': current_what_changed['reason_codes'],
        'limitations': current_what_changed['limitations'],
    }
    assert current_entry['baseline_adjacency'] == {
        'prior_data_through': '2026-07-04',
        'prior_published_snapshot_id': baseline_id,
        'adjacent_published_baseline_present': True,
    }
    assert current_entry['comparison_contract_check'] == {
        'prior_required_data_through': '2026-07-04',
        'adjacent_published_baseline_present': True,
        'adjacent_trusted_baseline_present': True,
        'stored_comparison_available': None,
        'stored_comparison_current_date': None,
        'stored_comparison_baseline_date': None,
        'stored_comparison_matches_adjacent_contract': None,
        'notes': [
            'stored_comparison_metadata_absent',
            'stored_comparison_not_available',
        ],
    }

    baseline_entry = _entry(payload, baseline_id)
    assert baseline_entry['baseline_adjacency'] == {
        'prior_data_through': '2026-07-03',
        'prior_published_snapshot_id': None,
        'adjacent_published_baseline_present': False,
    }


def test_snapshot_audit_empty_table_is_valid(client):
    response = client.get(ROUTE, headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['latest_snapshot'] is None
    assert payload['latest_valid_snapshot_id'] is None
    assert payload['recent_snapshots'] == []
    summary = payload['snapshot_adjacency_summary']
    assert summary['published_snapshot_count'] == 0
    assert summary['trusted_published_snapshot_count'] == 0
    assert summary['data_through_dates'] == []
    assert summary['adjacent_published_pairs'] == []
    assert summary['adjacent_published_pair_count'] == 0
    assert summary['missing_prior_dates'] == []
    assert summary['trusted_pair_count'] == 0
    assert summary['comparable_adjacent_pair_count'] == 0
    assert summary['non_comparable_count'] == 0
    assert summary['non_comparable_reason_codes'] == []
    assert summary['non_adjacent_comparison_count'] == 0
    assert summary['non_adjacent_comparisons'] == []
    assert summary['response_mode'] == 'bounded_summary'
    assert 'latest_snapshot' in payload['missing_sections']
    assert 'recent_snapshots' in payload['missing_sections']


def test_snapshot_audit_window_14_and_production_shaped_rows_are_bounded(
    app,
    client,
):
    with app.app_context():
        _snapshot(date(2026, 7, 4), generated_offset_minutes=1)
        current = _snapshot(
            date(2026, 7, 5),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 5),
                what_changed_overrides={
                    'comparison_available': False,
                    'current_date': '2026-07-05',
                    'baseline_date': '2026-07-03',
                    'items_count': 12,
                    'omitted_count': 3,
                    'comparison': {
                        'comparison_available': False,
                        'current_date': '2026-07-05',
                        'baseline_date': '2026-07-03',
                        'reason_codes': ['stored_non_adjacent_baseline'],
                    },
                },
            ),
        )
        db.session.commit()
        current_id = current.id

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-05&window=14',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['request'] == {'date': '2026-07-05', 'window_days': 14}
    assert payload['served_freshness']['data_through'] == '2026-07-05'
    assert payload['served_freshness']['snapshot_id'] == current_id
    assert payload['served_freshness']['response_mode'] == 'bounded_summary'
    assert payload['diagnostics']['response_mode'] == 'bounded_summary'
    assert payload['served_freshness']['data_through'] == '2026-07-05'

    current_entry = _entry(payload, current_id)
    assert current_entry['embedded_what_changed']['items_count'] == 12
    assert current_entry['embedded_what_changed']['omitted_count'] == 3
    contract_check = current_entry['comparison_contract_check']
    assert contract_check['stored_comparison_available'] is False
    assert contract_check['stored_comparison_current_date'] == '2026-07-05'
    assert contract_check['stored_comparison_baseline_date'] == '2026-07-03'
    assert contract_check['stored_comparison_matches_adjacent_contract'] is False
    assert 'stored_comparison_non_adjacent' in contract_check['notes']


def test_snapshot_audit_large_payloads_return_compact_summaries(app, client):
    raw_marker = 'raw-dashboard-fragment-should-not-return'
    start = date(2026, 6, 20)

    def large_payload(ref):
        prior = ref - timedelta(days=1)
        payload = _payload(
            ref,
            what_changed_overrides={
                'comparison': {
                    'comparison_available': True,
                    'current_date': ref.isoformat(),
                    'baseline_date': prior.isoformat(),
                    'reason_codes': ['stored_adjacent_comparison'],
                    'items': [
                        {'marker': raw_marker, 'blob': 'x' * 1000}
                        for _ in range(30)
                    ],
                },
                'items': [
                    {'marker': raw_marker, 'blob': 'y' * 1000}
                    for _ in range(30)
                ],
                'unknown_top_level': raw_marker,
            },
        )
        payload['teams'] = [
            {'marker': raw_marker, 'blob': 'z' * 2000}
            for _ in range(50)
        ]
        payload['freshness']['raw_large_marker'] = raw_marker
        payload['freshness']['slate_coverage']['raw_coverage_marker'] = raw_marker
        return payload

    with app.app_context():
        for offset in range(15):
            ref = start + timedelta(days=offset)
            _snapshot(
                ref,
                generated_offset_minutes=offset,
                payload=large_payload(ref),
            )
        db.session.commit()

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-04&window=14',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert len(response.data) < 70000
    body = response.get_data(as_text=True)
    assert raw_marker not in body
    assert '"teams"' not in body
    assert '"items"' not in body
    payload = response.get_json()
    assert len(payload['recent_snapshots']) == 15
    assert all(
        row['response_mode'] == 'bounded_summary'
        for row in payload['recent_snapshots']
    )
    summary = payload['snapshot_adjacency_summary']
    assert summary['trusted_pair_count'] == 14
    assert summary['comparable_adjacent_pair_count'] == 14
    assert summary['non_comparable_count'] == 0
    assert summary['non_adjacent_comparison_count'] == 0
    assert summary['non_comparable_reason_codes'] == []


def test_snapshot_audit_operator_recent_row_limit_override(app):
    with app.app_context():
        for offset in range(5):
            _snapshot(
                date(2026, 7, 5),
                generated_offset_minutes=offset,
            )
        db.session.commit()

        from services import internal_snapshot_audit as audit_service

        payload = audit_service.build_internal_snapshot_audit_payload(
            product_date='2026-07-05',
            window_days='14',
            recent_row_query_limit='3',
        )

    summary = payload['snapshot_adjacency_summary']
    assert summary['recent_row_query_limit'] == 3
    assert summary['recent_rows_truncated'] is True
    assert payload['diagnostics']['recent_row_query_limit'] == 3
    assert payload['diagnostics']['recent_rows_truncated'] is True


def test_snapshot_audit_rejects_invalid_recent_row_limit(app):
    with app.app_context():
        from services import internal_snapshot_audit as audit_service

        with pytest.raises(
            audit_service.SnapshotAuditRequestError,
            match='recent_row_query_limit_invalid',
        ):
            audit_service.build_internal_snapshot_audit_payload(
                product_date='2026-07-05',
                window_days='14',
                recent_row_query_limit='0',
            )


def test_snapshot_audit_missing_incomplete_sections_are_diagnostics_not_crashes(
    app,
    client,
):
    with app.app_context():
        current = _snapshot(
            date(2026, 7, 5),
            payload={
                'capability': 'bullpen_dashboard',
                'freshness': {
                    'data_through': '2026-07-05',
                    'reason_codes': ['stored_freshness_without_slate_coverage'],
                },
                'what_changed_since_yesterday': {
                    'state': 'insufficient_context',
                    'reason_codes': ['stored_comparison_unavailable'],
                    'comparison_available': False,
                },
            },
        )
        db.session.commit()
        current_id = current.id

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-05&window=14',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['latest_valid_snapshot_id'] is None
    assert 'latest_valid_snapshot' in payload['missing_sections']
    assert payload['diagnostics']['reason'] == 'dashboard_snapshot_slate_coverage_missing'

    current_entry = _entry(payload, current_id)
    assert current_entry['trust']['unavailable_reason'] == (
        'dashboard_snapshot_slate_coverage_missing'
    )
    assert current_entry['payload_freshness'] == {
        'data_through': '2026-07-05',
        'reason_codes': ['stored_freshness_without_slate_coverage'],
    }
    assert current_entry['comparison_contract_check']['stored_comparison_available'] is False
    assert 'stored_comparison_not_available' in current_entry['comparison_contract_check']['notes']
    assert 'adjacent_baseline_missing' in current_entry['comparison_contract_check']['notes']


def test_snapshot_audit_unexpected_exception_returns_degraded_fallback_json(
    app,
    client,
    monkeypatch,
):
    """Summary failure degrades to bounded DB-row fallback JSON — never 502."""
    from services import internal_snapshot_audit as audit_service

    with app.app_context():
        row = _snapshot(date(2026, 7, 5))
        db.session.commit()
        row_id = row.id

    def fail_payload(**_kwargs):
        raise RuntimeError(
            'database password=secret token=abc123 host=internal.example'
        )

    monkeypatch.setattr(
        audit_service,
        'build_internal_snapshot_audit_payload',
        fail_payload,
    )

    response = client.get(f'{ROUTE}?window=14', headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['capability'] == 'phase0h_internal_snapshot_audit'
    assert payload['route_status'] == 'degraded'
    assert payload['route_access'] == 'internal_admin_only'
    assert payload['response_mode'] == 'fallback_db_row_metadata'
    assert payload['internal_only_watermark'] == {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }
    assert payload['request'] == {'date': None, 'window_days': 14}
    assert payload['ratification_ready'] is False
    assert payload['decision_4_5_supported'] is False
    assert payload['ratification_blocked_reason'] == (
        'fallback_row_metadata_cannot_prove_trusted_pairs'
    )

    diagnostic_codes = {entry['code'] for entry in payload['diagnostics']}
    assert 'audit_summary_unavailable' in diagnostic_codes
    assert 'fallback_db_row_summary_only' in diagnostic_codes
    summary_diagnostic = next(
        entry for entry in payload['diagnostics']
        if entry['code'] == 'audit_summary_unavailable'
    )
    assert summary_diagnostic['failure_code'] == 'summary_exception:RuntimeError'

    latest = payload['latest_snapshot']
    assert latest['id'] == row_id
    assert latest['data_through'] == '2026-07-05'
    assert latest['status'] == dashboard_snapshot.SNAPSHOT_STATUS_READY
    assert latest['is_published'] is True
    assert latest['trust_evaluated'] is False
    assert latest['response_mode'] == 'db_row_metadata_only'
    assert 'trust' not in latest
    assert payload['recent_snapshot_count'] == len(payload['recent_snapshots'])
    assert payload['recent_snapshots'][0]['id'] == row_id

    adjacency = payload['snapshot_adjacency_summary']
    assert adjacency['available'] is False
    assert adjacency['trusted_pair_count'] is None
    assert adjacency['comparable_adjacent_pair_count'] is None
    assert adjacency['non_comparable_count'] is None
    assert adjacency['non_comparable_reason_codes'] is None
    assert adjacency['non_adjacent_comparison_count'] is None

    body = response.get_data(as_text=True).lower()
    for leaked in ('password', 'secret', 'token', 'internal.example', 'abc123'):
        assert leaked not in body


def test_snapshot_audit_time_budget_exceeded_raises_summary_unavailable(app):
    from services import internal_snapshot_audit as audit_service

    with app.app_context():
        with pytest.raises(audit_service.SnapshotAuditSummaryUnavailable) as excinfo:
            audit_service.build_internal_snapshot_audit_payload(
                time_budget_seconds=-1,
            )
    assert excinfo.value.code == 'summary_time_budget_exceeded'
    assert excinfo.value.stage == 'summary_build_started'


def test_snapshot_audit_time_budget_exceeded_returns_degraded_fallback(
    app,
    client,
    monkeypatch,
):
    from services import internal_snapshot_audit as audit_service

    with app.app_context():
        _snapshot(date(2026, 7, 5))
        db.session.commit()

    monkeypatch.setattr(audit_service, 'SUMMARY_TIME_BUDGET_SECONDS', -1)

    response = client.get(f'{ROUTE}?window=14', headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['route_status'] == 'degraded'
    assert payload['ratification_ready'] is False
    assert payload['decision_4_5_supported'] is False
    assert payload['request']['window_days'] == 14
    summary_diagnostic = next(
        entry for entry in payload['diagnostics']
        if entry['code'] == 'audit_summary_unavailable'
    )
    assert summary_diagnostic['failure_code'] == 'summary_time_budget_exceeded'
    assert summary_diagnostic['failure_stage'] == 'summary_build_started'
    assert payload['latest_snapshot']['data_through'] == '2026-07-05'


def test_snapshot_audit_empty_table_fallback_reports_no_rows_without_faking(
    client,
    monkeypatch,
):
    from services import internal_snapshot_audit as audit_service

    def fail_payload(**_kwargs):
        raise RuntimeError('summary unavailable')

    monkeypatch.setattr(
        audit_service,
        'build_internal_snapshot_audit_payload',
        fail_payload,
    )

    response = client.get(ROUTE, headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['route_status'] == 'degraded'
    assert payload['request'] == {'date': None, 'window_days': 7}
    assert payload['latest_snapshot'] is None
    assert payload['recent_snapshots'] == []
    assert payload['recent_snapshot_count'] == 0
    assert payload['snapshot_adjacency_summary']['trusted_pair_count'] is None
    assert payload['snapshot_adjacency_summary']['available'] is False
    assert payload['ratification_ready'] is False


def test_snapshot_audit_returns_bounded_error_when_fallback_also_fails(
    client,
    monkeypatch,
):
    from services import internal_snapshot_audit as audit_service

    def fail_summary(**_kwargs):
        raise RuntimeError(
            'database password=secret token=abc123 host=internal.example'
        )

    def fail_fallback(**_kwargs):
        raise RuntimeError('fallback also failed password=secret')

    monkeypatch.setattr(
        audit_service,
        'build_internal_snapshot_audit_payload',
        fail_summary,
    )
    monkeypatch.setattr(
        audit_service,
        'build_internal_snapshot_audit_fallback_payload',
        fail_fallback,
    )

    response = client.get(ROUTE, headers=ADMIN_HEADERS)

    assert response.status_code == 500
    payload = response.get_json()
    assert payload == {
        'capability': 'phase0h_internal_snapshot_audit',
        'route_status': 'internal_admin_only',
        'internal_only_watermark': {
            'internal_only': True,
            'admin_gated': True,
            'phase0b_public_evidence_gate': 'closed',
            'public_evidence_exposure': False,
            'quote_only_rendered_claims': True,
        },
        'status': 'error',
        'error': 'internal_snapshot_audit_failed',
        'http_status': 500,
    }
    body = json.dumps(payload).lower()
    for leaked in ('password', 'secret', 'token', 'internal.example', 'abc123'):
        assert leaked not in body


def test_snapshot_audit_checkpoint_logs_redact_token_and_payloads(
    app,
    client,
    caplog,
    monkeypatch,
):
    raw_marker = 'raw-dashboard-fragment-should-not-log'
    with app.app_context():
        payload = _payload(date(2026, 7, 5))
        payload['freshness']['raw_log_marker'] = raw_marker
        _snapshot(date(2026, 7, 5), payload=payload)
        db.session.commit()

    with caplog.at_level(logging.INFO):
        success = client.get(f'{ROUTE}?window=14', headers=ADMIN_HEADERS)
    assert success.status_code == 200
    log_text = ' '.join(record.getMessage() for record in caplog.records)
    assert '[snapshot-audit] stage=auth_passed' in log_text
    assert 'stage=latest_snapshot_query_started' in log_text
    assert 'stage=response_construction_finished' in log_text
    assert 'stage=summary_succeeded' in log_text
    assert 'admin-secret' not in log_text
    assert raw_marker not in log_text
    assert 'stored_freshness_reason' not in log_text

    caplog.clear()
    from services import internal_snapshot_audit as audit_service

    def fail_payload(**_kwargs):
        raise RuntimeError('boom admin-secret should never be logged anyway')

    monkeypatch.setattr(
        audit_service,
        'build_internal_snapshot_audit_payload',
        fail_payload,
    )
    with caplog.at_level(logging.INFO):
        degraded = client.get(ROUTE, headers=ADMIN_HEADERS)
    assert degraded.status_code == 200
    failure_log_text = ' '.join(record.getMessage() for record in caplog.records)
    assert 'error_type=RuntimeError' in failure_log_text
    assert 'stage=fallback_succeeded' in failure_log_text
    assert 'admin-secret' not in failure_log_text
    assert raw_marker not in failure_log_text


def test_snapshot_audit_extracts_nested_what_changed_without_dumping_items(app, client):
    with app.app_context():
        _snapshot(date(2026, 6, 30), generated_offset_minutes=1)
        current = _snapshot(
            date(2026, 7, 1),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 1),
                what_changed_overrides={
                    'comparison_available': False,
                    'current_date': '2026-07-01',
                    'baseline_date': '2026-06-30',
                    'item_count': 2,
                    'items': [{'team': 'not_returned'}],
                    'unknown_top_level': 'not_returned',
                    'comparison': {
                        'comparison_available': True,
                        'current_date': '2026-07-01',
                        'baseline_date': '2026-06-28',
                        'reason_codes': ['example_reason'],
                        'items': [{'team': 'not_returned_nested'}],
                        'unknown_nested': 'not_returned',
                    },
                },
            ),
        )
        db.session.commit()
        current_id = current.id

    response = client.get(f'{ROUTE}?dataThrough=2026-07-01', headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    current_entry = _entry(payload, current_id)
    assert current_entry['embedded_what_changed'] == {
        'state': 'insufficient_context',
        'reason_codes': ['stored_reason'],
        'limitations': ['Stored comparison limitation.'],
        'comparison_available': False,
        'baseline_date': '2026-06-30',
        'current_date': '2026-07-01',
        'item_count': 2,
        'comparison': {
            'reason_codes': ['example_reason'],
            'comparison_available': True,
            'baseline_date': '2026-06-28',
            'current_date': '2026-07-01',
        },
    }
    serialized = json.dumps(current_entry)
    assert 'not_returned' not in serialized
    assert 'items' not in serialized
    assert 'unknown_top_level' not in serialized
    assert 'unknown_nested' not in serialized
    assert current_entry['comparison_contract_check']['stored_comparison_available'] is True
    assert current_entry['comparison_contract_check']['stored_comparison_current_date'] == '2026-07-01'
    assert current_entry['comparison_contract_check']['stored_comparison_baseline_date'] == '2026-06-28'
    assert (
        current_entry['comparison_contract_check']['stored_comparison_matches_adjacent_contract']
        is False
    )
    assert 'stored_comparison_non_adjacent' in current_entry['comparison_contract_check']['notes']


def test_snapshot_audit_adjacent_stored_comparison_passes_contract(app, client):
    with app.app_context():
        _snapshot(date(2026, 6, 30), generated_offset_minutes=1)
        current = _snapshot(
            date(2026, 7, 1),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 1),
                what_changed_overrides={
                    'comparison': {
                        'comparison_available': True,
                        'current_date': '2026-07-01',
                        'baseline_date': '2026-06-30',
                    },
                },
            ),
        )
        db.session.commit()
        current_id = current.id

    response = client.get(f'{ROUTE}?dataThrough=2026-07-01', headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    contract_check = _entry(payload, current_id)['comparison_contract_check']
    assert contract_check['stored_comparison_available'] is True
    assert contract_check['stored_comparison_current_date'] == '2026-07-01'
    assert contract_check['stored_comparison_baseline_date'] == '2026-06-30'
    assert contract_check['stored_comparison_matches_adjacent_contract'] is True
    assert 'stored_comparison_non_adjacent' not in contract_check['notes']


def test_snapshot_audit_uses_historical_publication_for_deactivated_baseline(
    app,
    client,
):
    with app.app_context():
        baseline = _snapshot(
            date(2026, 7, 9),
            is_published=False,
            published_at=datetime(2026, 7, 9, 12, 5, 0),
            generated_offset_minutes=1,
        )
        current = _snapshot(
            date(2026, 7, 10),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 10),
                state='changes_detected',
                what_changed_overrides={
                    'comparison_available': True,
                    'current_date': '2026-07-10',
                    'baseline_date': '2026-07-09',
                    'comparison': {
                        'comparison_available': True,
                        'current_date': '2026-07-10',
                        'baseline_date': '2026-07-09',
                    },
                },
            ),
        )
        db.session.commit()
        baseline_id = baseline.id
        current_id = current.id

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-10&window=14',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    summary = payload['snapshot_adjacency_summary']
    assert summary['publication_basis'] == 'historical_published_at'
    assert summary['active_published_snapshot_count'] == 1
    assert summary['historical_publication_candidate_count'] == 2
    assert summary['historically_published_snapshot_count'] == 2
    assert summary['trusted_historical_snapshot_count'] == 2
    assert summary['published_snapshot_count'] == 2
    assert summary['trusted_published_snapshot_count'] == 2
    assert summary['data_through_dates'] == ['2026-07-09', '2026-07-10']
    assert summary['adjacent_published_pair_count'] == 1
    assert summary['trusted_pair_count'] == 1
    assert summary['comparable_adjacent_pair_count'] == 1
    assert summary['non_comparable_count'] == 0
    assert summary['non_adjacent_comparison_count'] == 0
    assert summary['adjacent_published_pairs'] == [{
        'current_data_through': '2026-07-10',
        'prior_data_through': '2026-07-09',
        'current_snapshot_id': current_id,
        'prior_snapshot_id': baseline_id,
    }]

    baseline_entry = _entry(payload, baseline_id)
    assert baseline_entry['is_published'] is False
    assert baseline_entry['trust']['unavailable_reason'] == (
        'dashboard_snapshot_not_published'
    )
    assert baseline_entry['historical_publication'] == {
        'historically_published': True,
        'unavailable_reason': None,
        'published_at': '2026-07-09T12:05:00',
        'active_publication_required': False,
    }

    current_entry = _entry(payload, current_id)
    assert current_entry['comparison_contract_check'] == {
        'prior_required_data_through': '2026-07-09',
        'adjacent_published_baseline_present': True,
        'adjacent_trusted_baseline_present': True,
        'stored_comparison_available': True,
        'stored_comparison_current_date': '2026-07-10',
        'stored_comparison_baseline_date': '2026-07-09',
        'stored_comparison_matches_adjacent_contract': True,
        'notes': [],
    }


def test_snapshot_audit_never_published_ready_snapshot_does_not_qualify(
    app,
    client,
):
    with app.app_context():
        never_published = _snapshot(
            date(2026, 7, 9),
            is_published=False,
            generated_offset_minutes=1,
        )
        current = _snapshot(
            date(2026, 7, 10),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 10),
                what_changed_overrides={
                    'comparison': {
                        'comparison_available': True,
                        'current_date': '2026-07-10',
                        'baseline_date': '2026-07-09',
                    },
                },
            ),
        )
        db.session.commit()
        never_published_id = never_published.id
        current_id = current.id

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-10&window=14',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    summary = payload['snapshot_adjacency_summary']
    assert summary['historical_publication_candidate_count'] == 1
    assert summary['historically_published_snapshot_count'] == 1
    assert summary['trusted_historical_snapshot_count'] == 1
    assert summary['data_through_dates'] == ['2026-07-10']
    assert summary['adjacent_published_pair_count'] == 0
    assert summary['trusted_pair_count'] == 0
    assert summary['comparable_adjacent_pair_count'] == 0
    current_entry = _entry(payload, current_id)
    assert current_entry['comparison_contract_check'][
        'adjacent_published_baseline_present'
    ] is False
    assert 'adjacent_baseline_missing' in current_entry[
        'comparison_contract_check'
    ]['notes']
    never_published_entry = _entry(payload, never_published_id)
    assert never_published_entry['historical_publication'][
        'unavailable_reason'
    ] == 'dashboard_snapshot_never_published'


@pytest.mark.parametrize(
    ('overrides', 'expected_reason'),
    (
        (
            {'status': dashboard_snapshot.SNAPSHOT_STATUS_PENDING},
            'dashboard_snapshot_not_ready',
        ),
        (
            {'status': dashboard_snapshot.SNAPSHOT_STATUS_FAILED},
            'dashboard_snapshot_not_ready',
        ),
        (
            {
                'payload_version': (
                    dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION + 1
                ),
            },
            'dashboard_snapshot_version_mismatch',
        ),
        (
            {
                'payload': _payload(
                    date(2026, 7, 9),
                    what_changed_overrides={},
                ),
                'payload_mutator': 'invalid_coverage',
            },
            'dashboard_snapshot_slate_coverage_incomplete',
        ),
    ),
)
def test_snapshot_audit_invalid_historical_candidates_do_not_qualify(
    app,
    client,
    overrides,
    expected_reason,
):
    overrides = dict(overrides)
    baseline_payload = overrides.pop('payload', None)
    if overrides.pop('payload_mutator', None) == 'invalid_coverage':
        baseline_payload['freshness']['slate_coverage'][
            'complete_enough_to_publish'
        ] = False

    with app.app_context():
        candidate = _snapshot(
            date(2026, 7, 9),
            is_published=False,
            published_at=datetime(2026, 7, 9, 12, 5, 0),
            generated_offset_minutes=1,
            payload=baseline_payload,
            **overrides,
        )
        current = _snapshot(
            date(2026, 7, 10),
            generated_offset_minutes=2,
            payload=_payload(
                date(2026, 7, 10),
                what_changed_overrides={
                    'comparison': {
                        'comparison_available': True,
                        'current_date': '2026-07-10',
                        'baseline_date': '2026-07-09',
                    },
                },
            ),
        )
        db.session.commit()
        candidate_id = candidate.id
        current_id = current.id

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-10&window=14',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    summary = payload['snapshot_adjacency_summary']
    assert summary['historical_publication_candidate_count'] == 2
    assert summary['historically_published_snapshot_count'] == 1
    assert summary['trusted_historical_snapshot_count'] == 1
    assert summary['data_through_dates'] == ['2026-07-10']
    assert summary['adjacent_published_pair_count'] == 0
    assert summary['trusted_pair_count'] == 0
    assert summary['comparable_adjacent_pair_count'] == 0
    assert _entry(payload, candidate_id)['historical_publication'][
        'unavailable_reason'
    ] == expected_reason
    assert _entry(payload, current_id)['comparison_contract_check'][
        'adjacent_trusted_baseline_present'
    ] is False


def test_snapshot_audit_summarizes_adjacent_published_and_trusted_pairs(app, client):
    with app.app_context():
        first = _snapshot(date(2026, 6, 29), generated_offset_minutes=1)
        second = _snapshot(date(2026, 6, 30), generated_offset_minutes=2)
        untrusted = _snapshot(
            date(2026, 7, 1),
            generated_offset_minutes=3,
            payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION + 1,
        )
        missing_prior = _snapshot(date(2026, 7, 3), generated_offset_minutes=4)
        db.session.commit()
        ids = {
            'first': first.id,
            'second': second.id,
            'untrusted': untrusted.id,
            'missing_prior': missing_prior.id,
        }

    response = client.get(f'{ROUTE}?dataThrough=2026-07-03', headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.get_json()
    summary = payload['snapshot_adjacency_summary']
    assert summary['active_published_snapshot_count'] == 4
    assert summary['historical_publication_candidate_count'] == 4
    assert summary['historically_published_snapshot_count'] == 3
    assert summary['trusted_historical_snapshot_count'] == 3
    assert summary['published_snapshot_count'] == 3
    assert summary['trusted_published_snapshot_count'] == 3
    assert summary['data_through_dates'] == [
        '2026-06-29',
        '2026-06-30',
        '2026-07-03',
    ]
    assert summary['adjacent_published_pairs'] == [
        {
            'current_data_through': '2026-06-30',
            'prior_data_through': '2026-06-29',
            'current_snapshot_id': ids['second'],
            'prior_snapshot_id': ids['first'],
        },
    ]
    assert summary['adjacent_published_pair_count'] == 1
    assert summary['trusted_pair_count'] == 1
    assert summary['comparable_adjacent_pair_count'] == 0
    assert summary['non_comparable_count'] == 1
    assert 'stored_comparison_metadata_absent' in summary['non_comparable_reason_codes']
    assert 'stored_comparison_not_available' in summary['non_comparable_reason_codes']
    assert summary['non_adjacent_comparison_count'] == 0
    assert summary['missing_prior_dates'] == ['2026-06-29', '2026-07-03']
    missing_prior_entry = _entry(payload, ids['missing_prior'])
    assert missing_prior_entry['comparison_contract_check']['adjacent_published_baseline_present'] is False
    assert missing_prior_entry['comparison_contract_check']['adjacent_trusted_baseline_present'] is False
    assert 'adjacent_baseline_missing' in missing_prior_entry['comparison_contract_check']['notes']
    untrusted_entry = _entry(payload, ids['untrusted'])
    assert untrusted_entry['trust']['unavailable_reason'] == 'dashboard_snapshot_version_mismatch'
    assert untrusted_entry['historical_publication']['unavailable_reason'] == (
        'dashboard_snapshot_version_mismatch'
    )


def test_snapshot_audit_date_and_window_params(app, client):
    with app.app_context():
        first = _snapshot(date(2026, 7, 1), generated_offset_minutes=1)
        selected = _snapshot(date(2026, 7, 5), generated_offset_minutes=2)
        _snapshot(date(2026, 7, 6), generated_offset_minutes=3)
        db.session.commit()
        first_id = first.id
        selected_id = selected.id

    response = client.get(
        f'{ROUTE}?dataThrough=2026-07-05&window=99',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['request'] == {'date': '2026-07-05', 'window_days': 14}
    assert payload['latest_snapshot']['id'] == selected_id
    assert {row['id'] for row in payload['recent_snapshots']} >= {first_id, selected_id}

    bad_date = client.get(f'{ROUTE}?date=not-a-date', headers=ADMIN_HEADERS)
    assert bad_date.status_code == 400
    assert bad_date.get_json()['error'] == 'date_invalid'
    assert bad_date.get_json()['internal_only_watermark']['phase0b_public_evidence_gate'] == 'closed'

    bad_window = client.get(f'{ROUTE}?window=abc', headers=ADMIN_HEADERS)
    assert bad_window.status_code == 400
    assert bad_window.get_json()['error'] == 'window_invalid'

    bad_zero = client.get(f'{ROUTE}?window=0', headers=ADMIN_HEADERS)
    assert bad_zero.status_code == 400
    assert bad_zero.get_json()['error'] == 'window_invalid'


def test_snapshot_audit_is_quote_only_and_read_only(app, client):
    with app.app_context():
        _snapshot(date(2026, 7, 5))
        db.session.commit()

    response = client.get(ROUTE, headers=ADMIN_HEADERS)
    assert response.status_code == 200
    body = json.dumps(response.get_json()).lower()
    for forbidden in ('generated_summary', 'recommendation', 'prediction'):
        assert forbidden not in body

    source = (REPO_ROOT / 'backend/services/internal_snapshot_audit.py').read_text(
        encoding='utf-8',
    )
    for forbidden in (
        'build_dashboard_snapshot',
        'store_dashboard_snapshot',
        'publish_dashboard_snapshot',
        'mark_dashboard_snapshot_failed',
        'commit',
        'add(',
        'delete(',
    ):
        assert forbidden not in source


def test_snapshot_audit_import_surface():
    path = REPO_ROOT / 'backend/services/internal_snapshot_audit.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    allowed_from_imports = {
        '__future__': {'annotations'},
        'datetime': {'date', 'datetime', 'timedelta'},
        'time': {'monotonic'},
        'sqlalchemy': {'desc', 'text'},
        'models.dashboard_snapshot': {'DashboardSnapshot'},
        'models.sync_run': {'SyncRun'},
        'services': {'board_freshness'},
        'utils.db': {'db'},
        'services.dashboard_snapshot': {
            'DASHBOARD_PAYLOAD_VERSION',
            'DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE',
            'DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING',
            'SNAPSHOT_SOURCE_BUILDER_V2',
            'SNAPSHOT_STATUS_FAILED',
            'SNAPSHOT_STATUS_PENDING',
            'SNAPSHOT_STATUS_READY',
            'SNAPSHOT_TYPE_BULLPEN_DASHBOARD',
            'payload_version_valid',
            'snapshot_current_enough',
            'snapshot_unavailable_reason',
        },
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name for alias in node.names}
            assert names == set(), names
        if isinstance(node, ast.ImportFrom):
            assert node.module in allowed_from_imports, node.module
            imported = {alias.name for alias in node.names}
            assert imported <= allowed_from_imports[node.module], (node.module, imported)

    source = path.read_text(encoding='utf-8')
    for forbidden in (
        r'from\s+flask\b',
        r'import\s+flask\b',
        r'from\s+services\.what_changed_since_yesterday\b',
        r'import\s+services\.what_changed_since_yesterday\b',
        r'from\s+services\.what_changed_since_yesterday_public\b',
        r'import\s+services\.what_changed_since_yesterday_public\b',
        r'from\s+services\.team_changes\b',
        r'import\s+services\.team_changes\b',
        r'from\s+models\.(evidence|composed_read|legacy_read)',
        r'from\s+services\.(reconciliation|legacy_read|composed_read)',
        r'internal_pitcher_evidence',
        r'internal_team_evidence',
        r'from\s+services\s+import\s+slate_coverage\b',
        r'import\s+services\.slate_coverage\b',
        r'import\s+services\.sync\b',
        r'from\s+services\s+import\s+sync\b',
    ):
        assert not re.search(forbidden, source), forbidden


def test_snapshot_audit_not_referenced_by_public_modules():
    public_sources = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/api/pitchers.py',
        REPO_ROOT / 'backend/api/recent_work.py',
        REPO_ROOT / 'backend/api/team_recent_work.py',
        REPO_ROOT / 'backend/api/recommendations.py',
        REPO_ROOT / 'backend/api/explanations.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    )
    for path in public_sources:
        source = path.read_text(encoding='utf-8')
        assert 'internal_snapshot_audit' not in source, path
        assert 'internal/snapshot-audit' not in source, path

    for path in (REPO_ROOT / 'frontend/src').rglob('*'):
        if path.is_file():
            source = path.read_text(encoding='utf-8')
            assert 'internal_snapshot_audit' not in source, path
            assert 'internal/snapshot-audit' not in source, path
