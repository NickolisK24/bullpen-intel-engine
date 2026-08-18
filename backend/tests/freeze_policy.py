"""Shared catalogue for the branch-diff freeze guards.

Four guards compare the working branch against their governed branch baseline
and fail when a frozen surface changed. Three retain their historical
``origin/main`` baseline; the appearance-team guard resolves the actual pull-
request base so integration-branch history is not attributed to a feature PR:

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

This module holds the catalogue only. Each guard keeps its own assertions, so a
guard still fails in its own voice.
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

# Reviewed exceptions for the current branch, and only for the current branch.
#
# This is the rare, deliberate event the module docstring describes: an approved
# change to a frozen surface names its exception at the time it is made. Both
# public-API guards read this one tuple, so an exception is stated once rather
# than copied into two test modules -- the duplication this module exists to end.
#
# H-12, August 14 2026. Seven governing-document paths shipped in API response
# metadata and none of them resolved: the Recommendation Engine V1 policy,
# contract, and implementation plan, two V3 team-operations phase records, and a
# V5 observation phase record had all been archived to docs/archive/2026-06/.
# The values now name the canonical owner of each boundary instead, because an
# archived phase record is implementation history rather than the contract an
# API response obeys.
#
# The exception is exactly as wide as that change: these two modules' route
# handlers, response shapes, status codes, gating, and baseball values are
# untouched. Nothing here exempts the *behavior* these guards protect --
# test_document_authority_contract.py::TestCodeCitedDocumentPaths proves on
# every run that every cited path exists, is not archived, and belongs to the
# canonical or current-methodology class, which is a stronger statement than a
# diff check can make.
#
# Entries become inert the moment this branch merges: the paths land on
# origin/main and can no longer appear in a future ``git diff origin/main...HEAD``.
# Remove them when convenient; leaving them protects nothing and grants nothing.
H12_DOCUMENT_PATH_REPAIR_PATHS = (
    'backend/api/recommendations.py',
    'backend/api/team_operations.py',
)

# Reviewed exceptions for the current branch, and only for the current branch.
#
# H-6 / H-7 residual closeout, August 14 2026. Three frozen surfaces changed,
# and in each case the guard fired correctly: what a reader receives DID move.
# That is the package.
#
# * ``team_state_card_metrics.py`` (Team State prefix) and
#   ``share_artifact_public.py`` (Share Artifact service prefix) — the share
#   card published the availability ENGINE state into its reader-facing
#   Availability column, so ``Monitor`` and ``Avoid`` reached readers on a
#   public route. The metrics builder now projects through the public
#   vocabulary owner; the read boundary withholds a non-public value on an
#   already-published artifact.
# * ``bullpen_board.py`` (Phase 0E legacy public path) — the On Watch count is
#   authored whenever there is one, so generated previews stop collapsing onto
#   a single constant sentence.
#
# The exception is exactly as wide as those changes. No stored artifact is
# rewritten, no availability or Team State calculation moves, no threshold
# moves, and no publication gate changes. What the guards actually protect is
# proved directly and on every run by
# test_team_state_card_v1_2.py (public vocabulary, engine words absent,
# fail-closed withholding, ordering) and test_preview_evidence_corpus.py
# (evidence discrimination, determinism, count grammar) — both stronger
# statements than a diff check can make.
#
# Entries go inert the moment this branch merges: the paths land on origin/main
# and can no longer appear in a future ``git diff origin/main...HEAD``.
PUBLIC_INTEGRITY_RESIDUAL_PATHS = (
    'backend/services/bullpen_board.py',
    'backend/services/share_artifact_public.py',
    'backend/services/team_state_card_metrics.py',
)

# D-054, August 15 2026. The governed league Team State listing adds one public
# route, guarded snapshot reads, and snapshot-pinned reuse of the existing board
# freshness serializer. The decision authority is recorded in
# docs/decisions/2026-08-15-governed-league-team-state-listing.md.
#
# This exception is exact-path and decision-linked. In particular,
# board_freshness.py may accept an explicit snapshot and suppress its runtime
# overlay only for pinned serialization; default callers, freshness calculations,
# stale gates, and fail-closed semantics remain unchanged and directly tested.
# As with the reviewed exceptions above, these entries become inert after merge
# because the paths no longer differ from origin/main.
D054_LEAGUE_TEAM_STATE_LISTING_PATHS = (
    'backend/api/bullpen.py',
    'backend/services/board_freshness.py',
    'backend/services/dashboard_snapshot.py',
)

# D-055, August 15 2026. The Team Board contract may project already-public
# workload facts from its loaded fatigue and availability authority and author
# one fail-closed Rest Status block. The decision authority is recorded in
# docs/decisions/2026-08-15-governed-team-board-workload-context.md.
#
# This exception names only the route assembly and its existing presentation
# service. It grants no directory exemption, score exposure, recalculation,
# reader-path acquisition, Team State change, or publication-authority change.
# As with the reviewed exceptions above, these entries become inert after merge
# because the paths no longer differ from origin/main.
D055_TEAM_BOARD_WORKLOAD_CONTEXT_PATHS = (
    'backend/api/bullpen.py',
    'backend/services/bullpen_board.py',
)

# PRE-02, August 17 2026. The new versioned Team Board contract is additive.
# ``bullpen.py`` changes only by accepting an optional rotation callable; every
# legacy caller retains the original default owner and payload. The new API
# module owns only ``/board-v2`` and performs no writes or publication work.
PRE02_TEAM_BOARD_V2_PATHS = (
    'backend/api/bullpen.py',
    'backend/api/team_board_v2.py',
)

# HOTFIX-01, August 17 2026. The canonical Team State projection gains one
# deterministic summary field so reader surfaces no longer use the independent,
# count-derived board-health sentence as the explanation of Team State.
#
# The exception is one exact semantic-owner path. It grants no classifier,
# readiness, publication, artifact, migration, route, or directory exemption.
HOTFIX01_TEAM_STATE_SUMMARY_AUTHORITY_PATHS = (
    'backend/services/team_state_public_vocabulary.py',
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
