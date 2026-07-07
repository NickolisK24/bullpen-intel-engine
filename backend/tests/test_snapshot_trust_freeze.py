from datetime import date
from pathlib import Path
import subprocess

import pytest

from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot
from services.what_changed_since_yesterday import (
    REASON_COMPARISON_WITHHELD,
    REASON_CURRENT_SLATE_COVERAGE_MISSING,
    REASON_CURRENT_SLATE_INCOMPLETE,
    REASON_CURRENT_SNAPSHOT_UNTRUSTED,
    REASON_DATA_THROUGH_MISSING,
    REASON_NO_PRIOR_SNAPSHOT,
    REASON_PRIOR_SLATE_COVERAGE_MISSING,
    REASON_PRIOR_SLATE_INCOMPLETE,
    REASON_PRIOR_SNAPSHOT_UNPUBLISHED,
    REASON_SNAPSHOTS_NOT_COMPARABLE,
    REASON_VALIDATIONS_FAILED,
    STATE_CHANGES_DETECTED,
    STATE_INSUFFICIENT_CONTEXT,
    STATE_NO_MEANINGFUL_CHANGES,
    build_what_changed_since_yesterday_payload,
)
from tests.test_phase0e_exit_docs import EXPECTED_ALEMBIC_HEAD, _alembic_heads


REPO_ROOT = Path(__file__).resolve().parents[2]


def _coverage(ref):
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
    }


def _snapshot_payload(ref):
    return {
        'capability': 'bullpen_dashboard',
        'freshness': {
            'data_through': ref.isoformat(),
            'availability_reference_date': ref.isoformat(),
            'validations_passed': True,
            'complete_enough_to_publish': True,
            'slate_coverage': _coverage(ref),
        },
        'capacity_intelligence': {
            'teams': [
                {
                    'team_id': 147,
                    'team_name': 'Test Club',
                    'team_abbreviation': 'TST',
                    'resource_health': {'state': 'stable', 'confidence': 'high'},
                    'trust_hierarchy': {'hierarchy_confidence': 'high'},
                },
            ],
        },
    }


def _snapshot_row(
    ref,
    *,
    status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
    is_published=True,
    payload=None,
    payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
    row_data_through=None,
):
    return DashboardSnapshot(
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        status=status,
        is_published=is_published,
        payload=payload if payload is not None else _snapshot_payload(ref),
        payload_version=payload_version,
        data_through=row_data_through or ref,
        availability_reference_date=row_data_through or ref,
        source='phase0h_freeze_test',
    )


def _metadata(ref, *, is_published=True, status='ready', trusted_current_payload=True):
    return {
        'data_through': ref.isoformat(),
        'availability_reference_date': ref.isoformat(),
        'is_published': is_published,
        'status': status,
        'trusted_current_payload': trusted_current_payload,
    }


def test_snapshot_trust_constants_frozen():
    assert dashboard_snapshot.SNAPSHOT_STATUS_READY == 'ready'
    assert dashboard_snapshot.SNAPSHOT_STATUS_PENDING == 'pending'
    assert dashboard_snapshot.SNAPSHOT_STATUS_FAILED == 'failed'
    assert dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION == 1
    assert dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD == 'bullpen_dashboard'
    assert dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING == (
        'dashboard_snapshot_slate_coverage_missing'
    )
    assert dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE == (
        'dashboard_snapshot_slate_coverage_incomplete'
    )

    assert STATE_CHANGES_DETECTED == 'changes_detected'
    assert STATE_NO_MEANINGFUL_CHANGES == 'no_meaningful_changes'
    assert STATE_INSUFFICIENT_CONTEXT == 'insufficient_context'
    assert REASON_NO_PRIOR_SNAPSHOT == 'no_prior_snapshot'
    assert REASON_PRIOR_SNAPSHOT_UNPUBLISHED == 'prior_snapshot_unpublished'
    assert REASON_CURRENT_SNAPSHOT_UNTRUSTED == 'current_snapshot_untrusted'
    assert REASON_SNAPSHOTS_NOT_COMPARABLE == 'snapshots_not_comparable'
    assert REASON_COMPARISON_WITHHELD == 'comparison_withheld'
    assert REASON_PRIOR_SLATE_COVERAGE_MISSING == 'prior_slate_coverage_missing'
    assert REASON_PRIOR_SLATE_INCOMPLETE == 'prior_slate_incomplete'
    assert REASON_CURRENT_SLATE_COVERAGE_MISSING == 'current_slate_coverage_missing'
    assert REASON_CURRENT_SLATE_INCOMPLETE == 'current_slate_incomplete'
    assert REASON_DATA_THROUGH_MISSING == 'data_through_missing'
    assert REASON_VALIDATIONS_FAILED == 'validations_failed'


def test_snapshot_trust_gates_behavior():
    ref = date(2026, 7, 5)
    trusted = _snapshot_row(ref)
    assert dashboard_snapshot.snapshot_unavailable_reason(trusted) is None

    not_ready = _snapshot_row(ref, status=dashboard_snapshot.SNAPSHOT_STATUS_PENDING)
    assert dashboard_snapshot.snapshot_unavailable_reason(not_ready) == 'dashboard_snapshot_not_ready'

    unpublished = _snapshot_row(ref, is_published=False)
    assert dashboard_snapshot.snapshot_unavailable_reason(unpublished) == 'dashboard_snapshot_not_published'

    wrong_version = _snapshot_row(ref, payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION + 1)
    assert dashboard_snapshot.snapshot_unavailable_reason(wrong_version) == 'dashboard_snapshot_version_mismatch'

    mismatch = _snapshot_row(
        ref,
        payload=_snapshot_payload(ref),
        row_data_through=date(2026, 7, 4),
    )
    assert dashboard_snapshot.snapshot_unavailable_reason(mismatch) == (
        'dashboard_snapshot_data_through_mismatch'
    )


def test_what_changed_adjacency_fails_closed():
    current_ref = date(2026, 7, 5)
    current = _snapshot_payload(current_ref)

    no_prior = build_what_changed_since_yesterday_payload(
        current,
        None,
        require_trusted_snapshots=True,
        current_snapshot_metadata=_metadata(current_ref),
        prior_snapshot_metadata=None,
    )
    assert no_prior['state'] == STATE_INSUFFICIENT_CONTEXT
    assert REASON_NO_PRIOR_SNAPSHOT in no_prior['reason_codes']
    assert REASON_COMPARISON_WITHHELD in no_prior['reason_codes']

    non_adjacent_ref = date(2026, 7, 3)
    non_adjacent = build_what_changed_since_yesterday_payload(
        current,
        _snapshot_payload(non_adjacent_ref),
        require_trusted_snapshots=True,
        current_snapshot_metadata=_metadata(current_ref),
        prior_snapshot_metadata=_metadata(non_adjacent_ref),
    )
    assert non_adjacent['state'] == STATE_INSUFFICIENT_CONTEXT
    assert REASON_SNAPSHOTS_NOT_COMPARABLE in non_adjacent['reason_codes']
    assert REASON_COMPARISON_WITHHELD in non_adjacent['reason_codes']


def test_snapshot_builder_has_no_internal_evidence_imports():
    source = (REPO_ROOT / 'backend/services/dashboard_snapshot.py').read_text(
        encoding='utf-8',
    )
    for forbidden in (
        'evidence',
        'composed_read',
        'legacy_read',
        'reconciliation',
        'PHASE0E_READ_BUILD',
        'internal_pitcher',
        'internal_team',
    ):
        assert forbidden not in source


def test_frozen_legacy_what_changed_files_untouched():
    changed = _changed_files_vs_main()
    if not changed:
        pytest.skip('git diff against origin/main unavailable')

    frozen_paths = {
        'backend/services/what_changed_since_yesterday.py',
        'backend/services/what_changed_since_yesterday_public.py',
        'backend/services/team_changes.py',
        'frontend/src/components/dashboard/WhatChangedCard.jsx',
        'backend/services/dashboard_snapshot.py',
        'backend/services/board_freshness.py',
        'backend/services/slate_coverage.py',
        'backend/services/sync.py',
    }
    assert not sorted(frozen_paths & changed)
    assert not sorted(path for path in changed if path.startswith('frontend/'))
    assert not sorted(path for path in changed if path.startswith('backend/migrations/'))


def test_route_map_freeze(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    monkeypatch.setenv('TEST_DATABASE_URL', 'sqlite:///:memory:')

    from app import create_app

    flask_app = create_app('test')
    rules = {str(rule) for rule in flask_app.url_map.iter_rules()}
    assert '/api/system/internal/snapshot-audit' in rules
    assert '/api/system/internal/pitcher-evidence' in rules
    assert '/api/system/internal/team-evidence' in rules
    assert '/api/bullpen/pitchers/<int:pitcher_id>/recent-work' in rules
    assert '/api/bullpen/teams/<int:team_id>/relief-work' in rules
    assert '/api/bullpen/teams/<int:team_id>/changes' in rules
    assert {
        rule for rule in rules if 'snapshot-audit' in rule
    } == {'/api/system/internal/snapshot-audit'}


def test_alembic_head_unchanged():
    assert _alembic_heads() == {EXPECTED_ALEMBIC_HEAD}


def _changed_files_vs_main():
    commands = (
        ('git', 'diff', '--name-only', 'origin/main'),
        ('git', 'diff', '--cached', '--name-only', 'origin/main'),
    )
    values = []
    for command in commands:
        try:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            continue
        values.extend(result.stdout.splitlines())
    return {
        path.strip().replace('\\', '/')
        for path in values
        if path.strip()
    }
