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

    # backend/services/sync.py and backend/services/dashboard_snapshot.py were
    # removed from this freeze for the July 2026 appearance-ledger trust
    # incident: the daily gameLog lane and the snapshot publish gate had to
    # change to stop incomplete appearance history from publishing as current.
    # Their behavior is now pinned by dedicated regression suites
    # (test_statusless_split_finality.py, test_postgame_lookback.py,
    # test_appearance_ledger.py) instead of a diff freeze.
    frozen_paths = {
        'backend/services/what_changed_since_yesterday.py',
        'backend/services/what_changed_since_yesterday_public.py',
        'backend/services/team_changes.py',
        'frontend/src/components/dashboard/WhatChangedCard.jsx',
        'backend/services/board_freshness.py',
        'backend/services/slate_coverage.py',
    }
    allowed_phase_a_audience_signup_files = {
        'backend/migrations/versions/2f7b9c1a5d43_add_audience_subscribers.py',
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/utils/api.js',
        'frontend/tests/intelligenceSurface.test.mjs',
    }
    allowed_bullpen_game_context_files = {
        'frontend/src/components/bullpen/TeamReliefWorkPanel.jsx',
        'frontend/tests/teamReliefWorkPanel.test.mjs',
    }
    allowed_pitcher_ledger_coverage_files = {
        'backend/migrations/versions/7c4d2e9f1a6b_add_pitcher_season_ledger_coverage.py',
    }
    allowed_public_what_changed_contract_files = {
        # Ratified Branch 1 backend-contract completion for the stored public
        # what_changed_since_yesterday payload's top-level state.
        'backend/services/what_changed_since_yesterday_public.py',
        # fix/what-changed-daily-sync: the prior-snapshot trust gate now anchors
        # on durable publication proof (published_at / was_published) instead of
        # the transient is_published serving flag, so repeated same-date syncs no
        # longer strand the daily comparison as no_prior_snapshot /
        # prior_snapshot_unpublished. Public vocabulary, reason codes, states,
        # and prediction/ranking/evidence boundaries are unchanged.
        'backend/services/what_changed_since_yesterday.py',
    }
    allowed_phase0i_roster_readiness_files = {
        'frontend/src/adapters/operatingStateReadModel.js',
        'frontend/src/components/bullpen/board/BullpenBoardView.jsx',
            'frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx',
            'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js',
            'frontend/src/components/dashboard/Dashboard.jsx',
            'frontend/src/components/dashboard/AvailabilityDashboardSummary.jsx',
            'frontend/src/components/dashboard/availabilityDashboardSummaryView.js',
            'frontend/src/components/dashboard/injuryIlContextView.js',
            'frontend/tests/availabilityDashboardSummary.test.mjs',
            'frontend/tests/injuryIlContext.test.mjs',
            'frontend/tests/tonightsBullpenBoard.test.mjs',
        }
    allowed_public_role_vocabulary_files = {
        # fix/public-relief-role-consistency: one canonical public relief-role
        # vocabulary (middle_relief -> depth_arm -> Middle Relief Arm) across
        # the chip, disclosure, and dashboard surfaces.
        'frontend/src/utils/pitcherLabels.js',
        'frontend/src/components/bullpen/board/tonightsBullpenBoardView.js',
        'frontend/tests/fixtures/bullpenBoardFixtures.mjs',
        'frontend/tests/pitcherLabels.test.mjs',
        'frontend/tests/pitcherUsageRole.test.mjs',
    }
    allowed_relief_role_input_integrity_files = {
        # fix/relief-role-input-integrity: one backend-authored public role
        # read owns the chip and disclosure; Compare inherits it untransformed.
        'frontend/tests/teamBullpenComparison.test.mjs',
    }
    allowed_legacy_retirement_files = {
        'frontend/package-lock.json',
        'frontend/package.json',
        'frontend/src/App.jsx',
        'frontend/src/components/admin/ProductIntelligenceAdmin.jsx',
        'frontend/src/components/bullpen/Bullpen.jsx',
        'frontend/src/components/dashboard/BullpenLandscape.jsx',
        'frontend/src/components/home/IntelligenceSurface.jsx',
        'frontend/src/components/layout/Footer.jsx',
        'frontend/src/components/methodology/Methodology.jsx',
        'frontend/src/components/share/TeamShareButton.jsx',
        'frontend/src/components/stories/Stories.jsx',
        'frontend/src/components/trust/DataTrust.jsx',
        'frontend/src/hooks/useProductIntelligence.js',
        'frontend/src/utils/adminProductEvents.js',
        'frontend/src/utils/analytics.js',
        'frontend/src/utils/api.js',
        'frontend/src/utils/productIdentity.js',
        'frontend/src/utils/productIntelligence.js',
        'frontend/tests/analytics.test.mjs',
        'frontend/tests/authClient.test.mjs',
        'frontend/tests/intelligenceSurface.test.mjs',
        'frontend/tests/navigationRoutes.test.mjs',
        'frontend/tests/productIntelligence.test.mjs',
        'frontend/tests/productIntelligenceAdmin.test.mjs',
    }
    allowed_trusted_traffic_files = {
        'frontend/src/components/bullpen/Bullpen.jsx',
        'frontend/src/components/bullpen/board/BullpenComparisonView.jsx',
        'frontend/src/components/bullpen/board/TonightsBullpenBoard.jsx',
        'frontend/src/components/bullpen/board/teamBullpenComparisonView.js',
        'frontend/src/components/share/EvidenceShareMenu.jsx',
        'frontend/src/components/share/TeamShareButton.jsx',
        'frontend/src/components/stories/Stories.jsx',
        'frontend/src/utils/adminDateTime.js',
        'frontend/src/utils/evidenceCardModel.js',
        'frontend/src/utils/evidenceCardStory.js',
        'frontend/tests/canonicalEvidenceLinks.test.mjs',
        'frontend/src/utils/evidenceCardRenderer.js',
        'frontend/src/utils/evidenceCardText.js',
        'frontend/src/utils/shareActions.js',
        'frontend/src/utils/teamShare.js',
        'frontend/tests/evidenceCards.test.mjs',
        'frontend/tests/bullpenOperatingStateCard.test.mjs',
        'frontend/tests/operatingStateReadModel.test.mjs',
        'frontend/tests/fixtures/bullpenComparisonFixtures.mjs',
        'frontend/tests/shareActions.test.mjs',
        'frontend/tests/teamShare.test.mjs',
        'backend/migrations/versions/a9e4c7d2f1b6_add_trusted_external_traffic.py',
        'backend/migrations/versions/b2e7c4a9d1f3_add_traffic_evidence_context.py',
        'backend/migrations/versions/c4f8a2d6e9b3_add_traffic_share_actions.py',
        'backend/migrations/versions/d7e4f1a8c2b6_add_share_story_context.py',
        'frontend/src/components/TrafficRouteObserver.jsx',
        'frontend/src/components/admin/TrafficIntelligenceAdmin.jsx',
        'frontend/src/utils/trafficMeasurement.js',
        'frontend/src/utils/trafficReporting.js',
        'frontend/tests/trafficIntelligenceAdmin.test.mjs',
        'frontend/tests/trafficMeasurement.test.mjs',
    }
    allowed_wp42_schedule_files = {
        'backend/migrations/versions/e6b4c2a8d1f3_add_slate_games.py',
        'frontend/src/components/posts/PrivatePosts.jsx',
        'frontend/src/components/posts/privatePostsView.js',
        'frontend/tests/privatePosts.test.mjs',
        'backend/migrations/versions/f7c5d3b9a2e1_add_editorial_post_history.py',
        'backend/migrations/versions/a1d8e4c6b2f0_extend_editorial_post_history.py',
    }
    assert not sorted(
        (frozen_paths & changed) - allowed_public_what_changed_contract_files
    )
    allowed_public_trust_consistency_files = {
        # fix/public-trust-consistency: the Data & Trust availability usage check
        # folds the internal Avoid tier into the single public Unavailable row so
        # the same public label never appears twice. Public vocabulary, sample
        # sizes, and conservative framing are unchanged.
        'frontend/src/components/trust/AvailabilityBacktestCard.jsx',
        'frontend/tests/availabilityBacktest.test.mjs',
    }
    assert not sorted(
        path for path in changed
        if path.startswith('frontend/')
        if path not in allowed_phase_a_audience_signup_files
        if path not in allowed_bullpen_game_context_files
        if path not in allowed_pitcher_ledger_coverage_files
        if path not in allowed_phase0i_roster_readiness_files
        if path not in allowed_public_role_vocabulary_files
        if path not in allowed_relief_role_input_integrity_files
        if path not in allowed_legacy_retirement_files
        if path not in allowed_trusted_traffic_files
        if path not in allowed_wp42_schedule_files
        if path not in allowed_public_trust_consistency_files
    )
    assert not sorted(
        path for path in changed
        if path.startswith('backend/migrations/')
        if path not in allowed_phase_a_audience_signup_files
        if path not in allowed_pitcher_ledger_coverage_files
        if path not in allowed_trusted_traffic_files
        if path not in allowed_wp42_schedule_files
    )


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
