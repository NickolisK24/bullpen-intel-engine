from datetime import date, timedelta
from pathlib import Path
import json
import subprocess

import pytest

import freeze_policy

from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot
from services import sync_metadata
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
from tests.generated_team_pages import (
    ROUTED_TEAM_PREVIEW_DELIVERY_FILES,
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


def _freeze_today(monkeypatch, today):
    """Pin the product current date these gates measure staleness against.

    ``snapshot_unavailable_reason`` computes ``product_current_date() -
    data_through`` and fails closed once that age reaches the unavailable
    threshold. Every fixture below uses fixed calendar dates, so without a
    frozen clock the gate being exercised changes as wall-clock time moves and
    the test eventually asserts something it was never written to assert.
    """
    monkeypatch.setattr(dashboard_snapshot, 'product_current_date', lambda: today)


def test_snapshot_trust_gates_behavior(monkeypatch):
    ref = date(2026, 7, 5)
    # Without this the freshness gate returns first once the fixtures age past
    # the unavailable threshold, and the mismatch assertion below silently stops
    # testing the mismatch gate. It began failing on 2026-08-03 for exactly that
    # reason: 2026-07-04 plus the 30-day threshold.
    _freeze_today(monkeypatch, ref)

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


def test_freshness_fail_closed_boundary_is_the_unavailable_threshold(monkeypatch):
    """The boundary itself, pinned — and pinned against a controlled clock.

    This is the gate that swallowed the mismatch assertion above. It is worth
    owning directly rather than only as the thing another test has to avoid:
    the day the threshold moves, this fails and names the new boundary instead
    of some unrelated assertion changing meaning.

    Both sides are asserted. A one-sided test would pass just as happily if the
    gate fired a day early, or never fired at all.
    """
    stale_after, unavailable_after = sync_metadata.freshness_thresholds()
    assert (stale_after, unavailable_after) == (14, 30)

    ref = date(2026, 7, 5)
    fresh = _snapshot_row(ref)

    _freeze_today(monkeypatch, ref + timedelta(days=unavailable_after - 1))
    assert dashboard_snapshot.snapshot_unavailable_reason(fresh) is None

    _freeze_today(monkeypatch, ref + timedelta(days=unavailable_after))
    assert dashboard_snapshot.snapshot_unavailable_reason(fresh) == (
        'dashboard_snapshot_freshness_fail_closed'
    )


def test_freshness_fail_closed_outranks_the_more_specific_reasons(monkeypatch):
    """Documents the ordering that made the original failure confusing.

    A stale snapshot reports staleness even when a more specific defect is also
    present. That is the current contract; this test records it so a future
    change to gate precedence is a deliberate, visible decision rather than a
    silent one.
    """
    ref = date(2026, 7, 5)
    _, unavailable_after = sync_metadata.freshness_thresholds()
    mismatch = _snapshot_row(
        ref,
        payload=_snapshot_payload(ref),
        row_data_through=date(2026, 7, 4),
    )

    _freeze_today(monkeypatch, date(2026, 7, 4) + timedelta(days=unavailable_after))
    assert dashboard_snapshot.snapshot_unavailable_reason(mismatch) == (
        'dashboard_snapshot_freshness_fail_closed'
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
    """The legacy What Changed surfaces stay byte-frozen on a branch.

    Exact paths only. This guard used to also refuse every path under
    ``frontend/`` and ``backend/migrations/``, which owned no invariant here --
    the freeze is about What Changed, not about two directories -- and that
    breadth is what accumulated thirty-four per-change allowlists in this one
    function. See backend/tests/freeze_policy.py.
    """
    changed = _changed_files_vs_main()
    if not changed:
        pytest.skip('git diff against origin/main unavailable')

    moved = freeze_policy.protected_hits(
        changed,
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
        approved=(
            freeze_policy.D054_LEAGUE_TEAM_STATE_LISTING_PATHS
            + freeze_policy.D055_TEAM_BOARD_WORKLOAD_CONTEXT_PATHS
            + freeze_policy.GAP51_REST_STATUS_CARRIER_PATHS
            + freeze_policy.GAP51_REST_STATUS_FROZEN_READER_PATHS
            + freeze_policy.GAP30_TEAM_STATE_DELTA_PATHS
            + freeze_policy.GAP31_REST_STATUS_DELTA_PATHS
        ),
    )
    assert moved == [], (
        f'frozen legacy What Changed surfaces changed: {moved}. These are '
        'frozen deliberately; changing one needs its own review, not an '
        'allowlist entry here.'
    )


def test_d054_records_the_exact_board_freshness_change_authority():
    decision = (
        REPO_ROOT
        / 'docs/decisions/2026-08-15-governed-league-team-state-listing.md'
    ).read_text(encoding='utf-8')
    for required in (
        '`backend/services/board_freshness.py`',
        'already-selected Dashboard snapshot explicitly',
        'suppress the runtime sync overlay',
        'zero-argument and default callers retain their prior behavior',
        'freshness calculations, stale gates, and fail-closed semantics do not change',
        'reuses existing published-snapshot freshness',
        'freshness authority',
    ):
        assert required in decision


def test_routed_team_preview_delivery_touches_no_snapshot_trust_surface():
    """The DIST-003 delivery allowance is an exemption from the path guard, not
    from its purpose.

    This freeze protects snapshot trust. The routing table is allowed to change
    so already-generated pages can be served, so this proves the thing the
    guard actually cares about: the file is a static rewrite/header table and
    declares no snapshot, publication, freshness, or Team State surface at all.
    Every rewrite destination is a static file inside the deployed frontend, so
    no route added here can reach a backend read, a snapshot selection, or a
    trust gate.
    """
    for relative in ROUTED_TEAM_PREVIEW_DELIVERY_FILES:
        config = json.loads(
            (REPO_ROOT / relative).read_text(encoding='utf-8'),
        )

        # A static route/header table and nothing else. The one redirect family
        # canonicalizes immutable share URLs on the same origin; no function,
        # cron, environment, or backend hop can be introduced silently.
        assert sorted(config) == ['headers', 'redirects', 'rewrites'], relative

        assert config['redirects'] == [{
            'source': '/share/:publicId/',
            'destination': '/share/:publicId',
            'permanent': True,
        }]

        for rewrite in config['rewrites']:
            destination = rewrite['destination']
            # Static, same-origin, in-bundle. Never an API path and never an
            # absolute URL to another host.
            assert destination.startswith('/'), (relative, destination)
            assert not destination.startswith('//'), (relative, destination)
            assert destination.endswith('.html'), (relative, destination)
            assert '/api/' not in destination, (relative, destination)

        # No snapshot-trust vocabulary reaches the routing table in either
        # language: nothing here selects, gates, dates, or describes a
        # published snapshot.
        source = (REPO_ROOT / relative).read_text(encoding='utf-8')
        for token in (
            'snapshot', 'dashboard_snapshot', 'published_at', 'is_published',
            'data_through', 'freshness', 'trusted', 'team_state',
            'what_changed', 'availability', 'publication',
        ):
            assert token not in source.lower(), (relative, token)


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
