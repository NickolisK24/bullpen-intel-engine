"""Shared catalogue for the branch-diff freeze guards.

Four guards compare the working branch against ``origin/main`` and fail when a
frozen surface changed:

- ``test_snapshot_trust_freeze.py::test_frozen_legacy_what_changed_files_untouched``
- ``test_public_team_relief_work.py::test_existing_public_routes_behavior_freeze``
- ``test_qa_reconciliation_scenarios.py::test_phase0e_switches_and_legacy_public_files_not_modified``
- ``test_appearance_team_authority.py::test_branch_touches_no_team_state_or_public_surface_files``

Why this module exists
----------------------
Each guard used to widen its protected set with directory prefixes --
``frontend/`` and ``backend/migrations/`` -- and one matched by substring. A
directory is not an invariant. The prefixes swept in every file under two large
trees, so ordinary work failed on files no invariant owned, and the only way
past was to name the change in a hand-maintained allowlist inside up to four
separate backend test modules. Thirty-four such allowlists had accumulated in
one guard alone.

Two concrete failures that motivated the narrowing:

1. Deleting five shared UI components that nothing imported required editing
   four backend allowlists, purely because the paths began with ``frontend/``.
2. Archiving ``docs/phase0g/public_team_relief_work_panel.md`` tripped a
   *runtime surface* guard, because the substring ``public_team_relief_work``
   appears in the markdown file's name. (That archiving is what moved it to
   ``docs/archive/2026-07/phase0g/``, where it lives today.)

What replaces them
------------------
The catalogues below name what the guards actually protect: exact repository
paths, plus ``backend/api/``, which is a genuine public-surface boundary rather
than an unrelated tree. Matching is whole-path or path-prefix only -- never
substring -- so a filename that merely contains a protected phrase is not a
protected file.

Historical allowlists are deliberately absent. Every one of them existed
because some past branch changed a protected path; each of those branches has
merged, so the path is in ``origin/main`` and can no longer appear in a future
``git diff origin/main...HEAD``. They protected nothing going forward. A future
approved change to a frozen surface adds its exception then, which is the rare
and deliberate event this mechanism is for.

This module holds the catalogue only. Each guard keeps its own diff helper and
its own assertions, so a guard still fails in its own voice.
"""

# ``backend/api/`` is the public HTTP surface. Unlike ``frontend/`` it is a
# boundary in its own right: every module in it defines routes readers reach.
PUBLIC_API_PREFIX = 'backend/api/'

# The legacy What Changed surfaces, frozen since the July 2026 appearance-ledger
# trust incident. ``sync.py`` and ``dashboard_snapshot.py`` were deliberately
# removed from this freeze then; their behavior is pinned by dedicated
# regression suites (test_statusless_split_finality.py, test_postgame_lookback.py,
# test_appearance_ledger.py) rather than by a diff freeze.
FROZEN_LEGACY_WHAT_CHANGED_PATHS = (
    'backend/services/what_changed_since_yesterday.py',
    'backend/services/what_changed_since_yesterday_public.py',
    'backend/services/team_changes.py',
    'frontend/src/components/dashboard/WhatChangedCard.jsx',
    'backend/services/board_freshness.py',
    'backend/services/slate_coverage.py',
)

# Public routes and the services behind them whose behavior is frozen: a change
# here alters what a reader receives.
FROZEN_PUBLIC_ROUTE_PATHS = (
    'backend/api/bullpen.py',
    'backend/api/pitchers.py',
    'backend/api/recent_work.py',
    'backend/api/system.py',
    'backend/services/public_recent_work.py',
    'backend/services/board_freshness.py',
    'backend/services/team_story_previews.py',
)

# Legacy public read/serving surfaces frozen at the Phase 0E exit. The public
# API prefix is checked alongside these.
FROZEN_PHASE0E_LEGACY_PUBLIC_PATHS = (
    'backend/services/dashboard_snapshot.py',
    'backend/services/bullpen_board.py',
    'backend/services/tonight_intelligence_snapshot.py',
    'backend/services/what_changed_since_yesterday.py',
    'backend/services/what_changed_since_yesterday_public.py',
)

# Team State ownership: the vocabulary, eligibility, payload and source modules
# that own the public Team State contract.
TEAM_STATE_PATH_PREFIX = 'backend/services/team_state_'

# Share Artifact immutability: the generation, repository, integrity and
# publication modules, their models, their routes, and the two shipped
# migrations that define their schema.
SHARE_ARTIFACT_SERVICE_PREFIX = 'backend/services/share_artifact'
SHARE_ARTIFACT_MODEL_PREFIX = 'backend/models/share_artifact'
SHARE_ARTIFACT_SCHEMA_PATHS = (
    'backend/migrations/versions/c1a7f4e2b9d6_add_share_artifacts.py',
    'backend/migrations/versions/e2b8d5a3c9f1_add_share_artifact_generation_audits.py',
)

# Source-authority surfaces the appearance-team guard protects by name.
APPEARANCE_TEAM_PROTECTED_PATHS = (
    'backend/services/season_era.py',
    'backend/services/bullpen_context.py',
    'backend/services/public_team_relief_work.py',
)

# Authenticated, non-public routes under backend/api/. They reach no reader, so
# the public-API prefix must not treat them as frozen public surface.
INTERNAL_ONLY_API_PATHS = (
    'backend/api/system.py',
    'backend/api/performance_intelligence_admin.py',
)


def normalize(path):
    """Repository-relative path with forward slashes and no surrounding space."""
    return str(path).strip().replace('\\', '/')


def matches(path, *, exact=(), prefixes=()):
    """True when ``path`` is one of ``exact`` or lives under one of ``prefixes``.

    Two prefix forms, both anchored -- never a bare substring search:

    - ending in ``/``  -> directory prefix, e.g. ``backend/api/``;
    - otherwise        -> filename prefix *within that exact directory*, so
      ``backend/services/share_artifact`` matches
      ``backend/services/share_artifacts.py`` but not a file of a similar name
      in any other directory.

    The anchoring is the point. ``docs/archive/2026-07/phase0g/
    public_team_relief_work_panel.md`` contains the name of a protected service
    and is not a protected file; a substring test called it one.
    """
    candidate = normalize(path)
    if candidate in {normalize(item) for item in exact}:
        return True
    candidate_dir, _, candidate_name = candidate.rpartition('/')
    for prefix in prefixes:
        clean = normalize(prefix)
        if clean.endswith('/'):
            if candidate.startswith(clean):
                return True
            continue
        prefix_dir, _, prefix_name = clean.rpartition('/')
        if candidate_dir == prefix_dir and candidate_name.startswith(prefix_name):
            return True
    return False


def protected_hits(changed, *, exact=(), prefixes=(), approved=()):
    """Sorted protected paths in ``changed``, minus any explicitly ``approved``.

    ``changed`` is the branch's changed-path list. The result is what the guard
    should refuse; an empty list means nothing frozen moved.
    """
    approved_set = {normalize(item) for item in approved}
    hits = {
        normalize(path)
        for path in changed
        if matches(path, exact=exact, prefixes=prefixes)
    }
    return sorted(hits - approved_set)
