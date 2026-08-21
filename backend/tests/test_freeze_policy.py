"""Red/green proof for the narrowed freeze policy.

The four branch-diff guards used to widen their protected sets with directory
prefixes and one substring test. This module pins the resulting behavior with
fabricated changed-path sets, so the policy is provable without touching a real
product file to provoke a guard.

Each case states which of the two failure modes it protects against:

- *green* -- a path no invariant owns must not be refused, because that is what
  forced ordinary work into hand-maintained allowlists;
- *red* -- a genuinely frozen path must still be refused, because narrowing the
  guards must not quietly unprotect anything.
"""

from pathlib import Path

import freeze_policy


# --- Paths no invariant owns. All of these were refused before the narrowing.

UNRELATED_FRONTEND = 'frontend/src/components/UI/ExampleUnusedComponent.jsx'
UNRELATED_FRONTEND_TEST = 'frontend/tests/exampleUnusedComponent.test.mjs'
UNRELATED_MIGRATION = 'backend/migrations/versions/example_future_migration.py'
ARCHIVED_NAME_COLLISION = 'docs/archive/example_public_team_relief_work_history.md'
UNRELATED_DOC = 'docs/current/EXAMPLE_RUNBOOK.md'
UNRELATED_SCRIPT = 'backend/scripts/example_operator_tool.py'

HARMLESS_PATHS = (
    UNRELATED_FRONTEND,
    UNRELATED_FRONTEND_TEST,
    UNRELATED_MIGRATION,
    ARCHIVED_NAME_COLLISION,
    UNRELATED_DOC,
    UNRELATED_SCRIPT,
)

# --- Every protected catalogue, as the guards apply it.

ALL_GUARD_QUERIES = (
    (
        'frozen legacy What Changed',
        {'exact': freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS},
    ),
    (
        'frozen public routes',
        {'exact': freeze_policy.FROZEN_PUBLIC_ROUTE_PATHS},
    ),
    (
        'phase 0E legacy public',
        {
            'exact': freeze_policy.FROZEN_PHASE0E_LEGACY_PUBLIC_PATHS,
            'prefixes': (freeze_policy.PUBLIC_API_PREFIX,),
            'approved': freeze_policy.INTERNAL_ONLY_API_PATHS,
        },
    ),
    (
        'appearance-team runtime surfaces',
        {
            'exact': (
                freeze_policy.APPEARANCE_TEAM_PROTECTED_PATHS
                + freeze_policy.SHARE_ARTIFACT_SCHEMA_PATHS
            ),
            'prefixes': (
                freeze_policy.PUBLIC_API_PREFIX,
                freeze_policy.TEAM_STATE_PATH_PREFIX,
                freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,
                freeze_policy.SHARE_ARTIFACT_MODEL_PREFIX,
            ),
            'approved': (
                'backend/services/public_team_relief_work.py',
                'backend/api/performance_intelligence_admin.py',
            ) + freeze_policy.TB09A_DELTA_SUBSTRATE_PATHS,
        },
    ),
)


# ── green: unrelated work is not refused ────────────────────────────────────

def test_no_guard_refuses_an_unrelated_frontend_file():
    """The defect that started H-1: deleting unimported UI components required
    editing four backend allowlists purely because of the path prefix."""
    for label, query in ALL_GUARD_QUERIES:
        assert freeze_policy.protected_hits([UNRELATED_FRONTEND], **query) == [], label


def test_no_guard_refuses_an_unrelated_migration():
    """A new migration is a schema question, answered by the schema invariants
    (single Alembic head, upgrade/downgrade), not by a historical path freeze."""
    for label, query in ALL_GUARD_QUERIES:
        assert freeze_policy.protected_hits([UNRELATED_MIGRATION], **query) == [], label


def test_no_guard_refuses_an_archived_document_whose_name_collides():
    """A markdown record naming a protected service is not that service.

    Under substring matching this exact shape failed a runtime-surface guard.
    """
    for label, query in ALL_GUARD_QUERIES:
        assert freeze_policy.protected_hits(
            [ARCHIVED_NAME_COLLISION], **query
        ) == [], label


def test_no_guard_refuses_any_harmless_path_even_all_at_once():
    for label, query in ALL_GUARD_QUERIES:
        assert freeze_policy.protected_hits(list(HARMLESS_PATHS), **query) == [], label


def test_a_document_named_after_a_frozen_module_is_not_frozen():
    """Same collision class, stated against the What Changed freeze."""
    lookalikes = [
        'docs/archive/what_changed_since_yesterday_notes.md',
        'docs/audits/board_freshness_review.md',
        'frontend/src/components/dashboard/WhatChangedCard.test-notes.md',
    ]
    assert freeze_policy.protected_hits(
        lookalikes, exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS
    ) == []


# ── red: frozen surfaces are still refused ──────────────────────────────────

def test_frozen_what_changed_path_is_still_refused():
    changed = [UNRELATED_FRONTEND, 'backend/services/team_changes.py']
    assert freeze_policy.protected_hits(
        changed, exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS
    ) == ['backend/services/team_changes.py']


def test_the_frozen_frontend_what_changed_card_is_still_refused():
    """One frontend file genuinely is frozen. Removing the blanket prefix must
    not have taken it with them."""
    assert freeze_policy.protected_hits(
        ['frontend/src/components/dashboard/WhatChangedCard.jsx'],
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
    ) == ['frontend/src/components/dashboard/WhatChangedCard.jsx']


def test_frozen_public_route_is_still_refused():
    assert freeze_policy.protected_hits(
        ['backend/api/bullpen.py'], exact=freeze_policy.FROZEN_PUBLIC_ROUTE_PATHS
    ) == ['backend/api/bullpen.py']


def test_a_new_public_api_module_is_still_refused():
    """The public API prefix still catches a route module that no catalogue
    names yet, which is the reason it stays a prefix."""
    assert freeze_policy.protected_hits(
        ['backend/api/brand_new_public_route.py'],
        prefixes=(freeze_policy.PUBLIC_API_PREFIX,),
    ) == ['backend/api/brand_new_public_route.py']


def test_team_state_and_share_artifact_surfaces_are_still_refused():
    changed = [
        'backend/services/team_state_payload.py',
        'backend/services/share_artifact_generation.py',
        'backend/models/share_artifact.py',
        'backend/migrations/versions/c1a7f4e2b9d6_add_share_artifacts.py',
        UNRELATED_FRONTEND,
    ]
    hits = freeze_policy.protected_hits(
        changed,
        exact=(
            freeze_policy.APPEARANCE_TEAM_PROTECTED_PATHS
            + freeze_policy.SHARE_ARTIFACT_SCHEMA_PATHS
        ),
        prefixes=(
            freeze_policy.TEAM_STATE_PATH_PREFIX,
            freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,
            freeze_policy.SHARE_ARTIFACT_MODEL_PREFIX,
        ),
    )
    assert hits == [
        'backend/migrations/versions/c1a7f4e2b9d6_add_share_artifacts.py',
        'backend/models/share_artifact.py',
        'backend/services/share_artifact_generation.py',
        'backend/services/team_state_payload.py',
    ]
    assert UNRELATED_FRONTEND not in hits


def test_source_authority_services_are_still_refused():
    for relative in freeze_policy.APPEARANCE_TEAM_PROTECTED_PATHS:
        assert freeze_policy.protected_hits(
            [relative], exact=freeze_policy.APPEARANCE_TEAM_PROTECTED_PATHS
        ) == [relative]


# ── matcher semantics ───────────────────────────────────────────────────────

def test_a_name_prefix_does_not_escape_its_directory():
    """``backend/services/share_artifact`` is a filename prefix in exactly that
    directory, not a free-floating substring."""
    assert freeze_policy.matches(
        'backend/services/share_artifacts.py',
        prefixes=(freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,),
    )
    for elsewhere in (
        'backend/scripts/share_artifact_export.py',
        'docs/current/share_artifact_operations.md',
        'frontend/src/components/share/share_artifact_view.js',
    ):
        assert not freeze_policy.matches(
            elsewhere, prefixes=(freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,)
        ), elsewhere


def test_a_directory_prefix_matches_only_below_that_directory():
    assert freeze_policy.matches('backend/api/x.py', prefixes=('backend/api/',))
    assert not freeze_policy.matches(
        'backend/api_helpers/x.py', prefixes=('backend/api/',)
    )
    assert not freeze_policy.matches(
        'docs/backend/api/notes.md', prefixes=('backend/api/',)
    )


def test_windows_separators_normalize():
    assert freeze_policy.protected_hits(
        ['backend\\services\\team_changes.py'],
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
    ) == ['backend/services/team_changes.py']


def test_approved_paths_are_subtracted():
    assert freeze_policy.protected_hits(
        ['backend/api/system.py'],
        prefixes=(freeze_policy.PUBLIC_API_PREFIX,),
        approved=freeze_policy.INTERNAL_ONLY_API_PATHS,
    ) == []


def test_d054_exception_is_exact_decision_linked_and_does_not_unfreeze_paths():
    approved = freeze_policy.D054_LEAGUE_TEAM_STATE_LISTING_PATHS
    assert approved == (
        'backend/api/bullpen.py',
        'backend/services/board_freshness.py',
        'backend/services/dashboard_snapshot.py',
    )

    changed = ['backend/services/board_freshness.py']
    assert freeze_policy.protected_hits(
        changed,
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
    ) == changed
    assert freeze_policy.protected_hits(
        changed,
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
        approved=approved,
    ) == []

    assert freeze_policy.protected_hits(
        ['backend/services/team_changes.py'],
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
        approved=approved,
    ) == ['backend/services/team_changes.py']


def test_d055_exception_is_exact_decision_linked_and_does_not_unfreeze_paths():
    approved = freeze_policy.D055_TEAM_BOARD_WORKLOAD_CONTEXT_PATHS
    assert approved == (
        'backend/api/bullpen.py',
        'backend/services/bullpen_board.py',
    )

    for changed, exact in (
        (['backend/api/bullpen.py'], freeze_policy.FROZEN_PUBLIC_ROUTE_PATHS),
        (
            ['backend/services/bullpen_board.py'],
            freeze_policy.FROZEN_PHASE0E_LEGACY_PUBLIC_PATHS,
        ),
    ):
        assert freeze_policy.protected_hits(changed, exact=exact) == changed
        assert freeze_policy.protected_hits(
            changed,
            exact=exact,
            approved=approved,
        ) == []

    assert freeze_policy.protected_hits(
        ['backend/api/pitchers.py'],
        exact=freeze_policy.FROZEN_PUBLIC_ROUTE_PATHS,
        approved=approved,
    ) == ['backend/api/pitchers.py']

    # When no authorized path differs from main, the exception subtracts
    # nothing and therefore grants nothing.
    assert freeze_policy.protected_hits(
        ['backend/services/team_changes.py'],
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
        approved=approved,
    ) == ['backend/services/team_changes.py']

    decision = (
        Path(__file__).resolve().parents[2]
        / 'docs/decisions/2026-08-15-governed-team-board-workload-context.md'
    ).read_text(encoding='utf-8')
    for exact_path in approved:
        assert f'`{exact_path}`' in decision
    assert 'No directory, prefix, or' in decision
    assert 'global bypass is authorized.' in decision


def test_hotfix01_exception_is_exact_and_does_not_unfreeze_neighbors():
    approved = freeze_policy.HOTFIX01_TEAM_STATE_SUMMARY_AUTHORITY_PATHS
    assert approved == (
        'backend/services/team_state_public_vocabulary.py',
    )

    changed = ['backend/services/team_state_public_vocabulary.py']
    assert freeze_policy.protected_hits(
        changed,
        prefixes=(freeze_policy.TEAM_STATE_PATH_PREFIX,),
    ) == changed
    assert freeze_policy.protected_hits(
        changed,
        prefixes=(freeze_policy.TEAM_STATE_PATH_PREFIX,),
        approved=approved,
    ) == []

    assert freeze_policy.protected_hits(
        ['backend/services/team_state_payload.py'],
        prefixes=(freeze_policy.TEAM_STATE_PATH_PREFIX,),
        approved=approved,
    ) == ['backend/services/team_state_payload.py']


def test_tb09a_exception_is_exact_and_does_not_unfreeze_artifact_neighbors():
    approved = freeze_policy.TB09A_DELTA_SUBSTRATE_PATHS
    assert approved == ('backend/services/share_artifact_generation.py',)

    changed = ['backend/services/share_artifact_generation.py']
    assert freeze_policy.protected_hits(
        changed,
        prefixes=(freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,),
    ) == changed
    assert freeze_policy.protected_hits(
        changed,
        prefixes=(freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,),
        approved=approved,
    ) == []

    assert freeze_policy.protected_hits(
        ['backend/services/share_artifacts.py'],
        prefixes=(freeze_policy.SHARE_ARTIFACT_SERVICE_PREFIX,),
        approved=approved,
    ) == ['backend/services/share_artifacts.py']

    decision = (
        Path(__file__).resolve().parents[2]
        / 'docs/decisions/2026-08-18-versioned-daily-delta-substrate.md'
    ).read_text(encoding='utf-8')
    assert '`backend/services/share_artifact_generation.py`' in decision
    assert 'No Share Artifact payload or historical row is modified.' in decision


def test_gap30_exception_is_exact_and_decision_linked():
    approved = freeze_policy.GAP30_TEAM_STATE_DELTA_PATHS
    assert approved == ('backend/services/team_changes.py',)

    assert freeze_policy.protected_hits(
        ['backend/services/team_changes.py'],
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
        approved=approved,
    ) == []
    assert freeze_policy.protected_hits(
        ['backend/services/what_changed_since_yesterday.py'],
        exact=freeze_policy.FROZEN_LEGACY_WHAT_CHANGED_PATHS,
        approved=approved,
    ) == ['backend/services/what_changed_since_yesterday.py']

    decision = (
        Path(__file__).resolve().parents[2]
        / 'docs/decisions/2026-08-20-governed-team-state-what-changed.md'
    ).read_text(encoding='utf-8')
    assert '`backend/services/team_changes.py`' in decision
    assert 'No classifier is rerun' in decision


def test_gap51_phase1_exception_is_exact_and_decision_linked():
    approved = freeze_policy.GAP51_REST_STATUS_CARRIER_PATHS
    assert approved == ('backend/services/bullpen_board.py',)

    assert freeze_policy.protected_hits(
        ['backend/services/bullpen_board.py'],
        exact=freeze_policy.FROZEN_PHASE0E_LEGACY_PUBLIC_PATHS,
        approved=approved,
    ) == []
    assert freeze_policy.protected_hits(
        ['backend/api/team_board_v2.py'],
        prefixes=(freeze_policy.PUBLIC_API_PREFIX,),
        approved=approved,
    ) == ['backend/api/team_board_v2.py']

    decision = (
        Path(__file__).resolve().parents[2]
        / 'docs/decisions/2026-08-20-d055-rest-status-publication-authority.md'
    ).read_text(encoding='utf-8')
    assert '`backend/services/bullpen_board.py`' in decision
    assert 'Readers retain their pre-Phase-1 behavior' in decision


def test_gap32_workload_window_exception_is_exact_and_decision_linked():
    approved = freeze_policy.GAP32_WORKLOAD_WINDOW_PATHS
    assert approved == (
        'backend/services/public_team_relief_work.py',
        'backend/services/share_artifact_generation.py',
    )

    assert freeze_policy.protected_hits(
        list(approved),
        exact=(
            freeze_policy.FROZEN_PUBLIC_ROUTE_PATHS
            + freeze_policy.TB09A_DELTA_SUBSTRATE_PATHS
        ),
        approved=approved,
    ) == []
    assert freeze_policy.protected_hits(
        ['backend/api/team_board_v2.py'],
        prefixes=(freeze_policy.PUBLIC_API_PREFIX,),
        approved=approved,
    ) == ['backend/api/team_board_v2.py']

    decision = (
        Path(__file__).resolve().parents[2]
        / 'docs/decisions/2026-08-20-prospective-workload-window-delta-substrate.md'
    ).read_text(encoding='utf-8')
    assert '`backend/services/public_team_relief_work.py`' in decision
    assert '`backend/services/share_artifact_generation.py`' in decision
    assert 'No historical GameLog replay or backfill is authorized' in decision


def test_no_catalogue_uses_a_bare_directory_as_an_invariant():
    """H-1's success condition, stated as an assertion.

    ``frontend/`` and ``backend/migrations/`` must never come back as protected
    prefixes: neither is an invariant, and treating them as one is what forced
    per-change allowlists into four backend test modules.
    """
    banned = {'frontend/', 'frontend/src/', 'frontend/public/', 'backend/migrations/'}
    for label, query in ALL_GUARD_QUERIES:
        used = {freeze_policy.normalize(p) for p in query.get('prefixes', ())}
        assert not (used & banned), f'{label} reintroduced a blanket prefix: {used & banned}'
