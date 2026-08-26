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

# TB-09A, August 18 2026. Newly published immutable Team State artifacts may
# stage one append-only Team Board delta sidecar from the exact readiness read
# already in the generation transaction. The artifact payload, lifecycle,
# integrity, eligibility, public serving contract, and historical artifacts are
# unchanged. The authorization is recorded in
# docs/decisions/2026-08-18-versioned-daily-delta-substrate.md.
#
# The exception is one exact orchestration path. It grants no Team State owner,
# Share Artifact model/repository, public API, migration, or directory exemption.
TB09A_DELTA_SUBSTRATE_PATHS = (
    'backend/services/share_artifact_generation.py',
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

# D-056, August 18 2026. The published Team State path classified bullpen
# availability on the trusted source's slate instead of the canonical next-day
# availability reference every other read of the same bullpen uses (the Team Board,
# the readiness route, and the calibration shadow). One local variable was answering
# two questions -- roster membership, which genuinely needs the slate, and
# availability, which needs slate + 1 -- so arms that worked the day before the slate
# were held out of the clean bucket and the artifact's own freshness metadata
# disagreed with the date it classified at. The decision authority is recorded in
# docs/decisions/2026-08-18-team-state-availability-reference-date.md.
#
# This exception is exact-path and decision-linked. Contract A is untouched: no
# threshold, precedence, partition mapping, vocabulary, or v3_phase_5 semantic
# moves, and its freeze test against the calibration contract stays green. No stored
# artifact is rewritten, no publication gate changes, no schema or migration is
# involved, and the proof capture added to dashboard_snapshot.py is env-gated,
# side-channel, and runs only after publication has already committed.
#
# What the guards protect is proved directly and on every run by
# test_team_state_vnext_contract_a.py and test_team_state_reference_date_split.py --
# both stronger statements than a diff check. As with the reviewed exceptions above,
# these entries go inert the moment this branch merges, because the paths land on
# origin/main and can no longer appear in a future ``git diff origin/main...HEAD``.
D056_TEAM_STATE_REFERENCE_DATE_PATHS = (
    'backend/services/share_artifact_generation.py',
    'backend/services/team_state_card_metrics.py',
    'backend/services/team_state_vnext_production_proof.py',
    'backend/services/dashboard_snapshot.py',
)

# Gap #30, August 20 2026. The reader-facing What Changed contract may add one
# Team State lane sourced exclusively from compatible frozen Team Board delta
# sidecars. The existing game-date status/appearance lanes, availability
# calculation, Team State classifier, historical rows, and legacy fields remain
# unchanged. The authority is recorded in
# docs/decisions/2026-08-20-governed-team-state-what-changed.md.
GAP30_TEAM_STATE_DELTA_PATHS = (
    'backend/services/team_changes.py',
)

# Gap #31, August 21 2026. What Changed may compare only the exact frozen
# D-055 rested-arm count carried by compatible trusted publications. Newly
# created sidecars retain that carrier directly; pre-activation natural
# sidecars may read it from their immutable source package without mutation or
# recomputation. Decision authority:
# docs/decisions/2026-08-21-governed-rest-status-what-changed.md.
GAP31_REST_STATUS_DELTA_PATHS = (
    'backend/services/share_artifact_generation.py',
    'backend/services/team_changes.py',
)

# Gap #51 Phase 1, August 20 2026. New immutable Team Board publications may
# carry one dormant D-055 Rest Status object authored through the existing
# semantic owner. Public readers remain on their pre-Phase-1 behavior until a
# natural scheduled publication is qualified and Phase 2 is separately
# reviewed. The authority is recorded in
# docs/decisions/2026-08-20-d055-rest-status-publication-authority.md.
GAP51_REST_STATUS_CARRIER_PATHS = (
    'backend/services/bullpen_board.py',
)

# Gap #51 Phase 2, August 21 2026. Snapshot 626 qualified the dormant carrier
# across all 30 represented teams, authorizing trusted `/board` and `/board-v2`
# readers to project that exact frozen D-055 object. Publication authoring stays
# unchanged; no Rest Status delta, replay, backfill, or historical mutation is
# authorized. The authority is recorded in
# docs/decisions/2026-08-21-d055-rest-status-frozen-reader-enforcement.md.
GAP51_REST_STATUS_FROZEN_READER_PATHS = (
    'backend/api/team_board_v2.py',
    'backend/services/bullpen_board.py',
)

# Gap #32, August 20 2026. New immutable Team Board publications may author the
# already-public 7-day and 14-day official relief-work windows against their
# represented date, and newly published Team State artifacts may copy those
# exact frozen values into the existing prospective delta sidecar. No reader
# delta, historical replay, current-roster reinterpretation, or public-route
# behavior is authorized. The authority is recorded in
# docs/decisions/2026-08-20-prospective-workload-window-delta-substrate.md.
GAP32_WORKLOAD_WINDOW_PATHS = (
    'backend/services/public_team_relief_work.py',
    'backend/services/share_artifact_generation.py',
)

# Rotation/Roster Intelligence bundle, August 20 2026. The existing immutable
# Team Board package already carries the canonical Rotation Impact read and the
# exact default-visible bullpen membership. Newly published Team State
# artifacts may copy those same-cycle values into the existing prospective
# delta sidecar. No reader-facing delta, historical replay, roster backfill, or
# Share Artifact payload change is authorized. The authority is recorded in
# docs/decisions/2026-08-20-rotation-roster-intelligence-authority.md.
ROTATION_ROSTER_INTELLIGENCE_PATHS = (
    'backend/services/share_artifact_generation.py',
)

# Roles & Deployment Intelligence, August 20 2026. The canonical public relief
# owner may add descriptive 14-day save/hold/finish/multi-inning profiles, and
# Share Artifact generation may hand their already-frozen carrier to the
# existing prospective delta sidecar. No inning-band publication, leverage
# promotion, role-title inference, historical replay, or reader delta is
# authorized. Decision authority:
# docs/decisions/2026-08-20-roles-deployment-intelligence-authority.md.
ROLES_DEPLOYMENT_INTELLIGENCE_PATHS = (
    'backend/services/public_team_relief_work.py',
    'backend/services/share_artifact_generation.py',
)

# Team Board Performance, August 21 2026. The existing Team Board v2 route may
# add the approved M-001 Current Active-Pen ERA read using the represented
# default-visible bullpen population and the established season-to-date
# performance authority. No Team State, share artifact, historical, ranking,
# or additional performance-metric gate is opened. Decision authority:
# docs/decisions/2026-08-21-team-board-performance-intelligence.md.
TEAM_BOARD_PERFORMANCE_INTELLIGENCE_PATHS = (
    'backend/api/team_board_v2.py',
)

# TODAY-04, August 24 2026. The existing Tonight snapshot reader advances its
# compatibility contract from ``tonight_v2`` to ``tonight_v3`` so cached
# payloads predating the additive recent-bullpen-volume carrier cannot
# masquerade as current. Snapshot authority, publication behavior, and every
# baseball semantic remain unchanged; the version and fail-closed behavior are
# pinned directly by test_tonight_intelligence_snapshot.py.
TODAY04_TONIGHT_SNAPSHOT_CONTRACT_PATHS = (
    'backend/services/tonight_intelligence_snapshot.py',
)

# TODAY-05, August 24 2026. The same frozen Tonight snapshot reader advances to
# ``tonight_v4`` so cached payloads predating the additive rotation-context
# carrier cannot appear current. The TODAY-04 exception above is retained as
# historical package evidence but is no longer the active branch approval.
TODAY05_TONIGHT_SNAPSHOT_CONTRACT_PATHS = (
    'backend/services/tonight_intelligence_snapshot.py',
)

# PIT-01, August 24 2026. The existing Pitcher detail route composes canonical
# role/read labels and the unchanged public recent-work carrier into one bounded
# current-state response. The recent-work service accepts already-resolved
# pitcher/freshness inputs solely to avoid duplicate lookup work; its standalone
# route, facts, date semantics, and sentences remain unchanged.
PIT01_PITCHER_CURRENT_STATE_PATHS = (
    'backend/api/bullpen.py',
    'backend/services/public_recent_work.py',
)

# SD-01, August 25 2026. The unified discovery package adds one bounded public
# identity-search route. It composes the existing team directory, pitcher-search,
# and product-day schedule owners and returns canonical identities only: no
# destination intelligence, baseball ranking, or write path is introduced.
#
# The Phase 0E public-prefix guard still protects every other backend/api path.
# This exact-path exception becomes inert after merge because the file will no
# longer differ from origin/main.
SD01_UNIFIED_SEARCH_PATHS = (
    'backend/api/search.py',
)

# PI-01, August 25 2026. The existing Team State share entry may project its
# already-published, integrity-verified artifact through the canonical public
# citation contract. This exact route remains read-only and lazy; it does not
# alter Team State, evidence selection, publication, or appearance-team
# authority. The route's lifecycle and integrity behavior is pinned by the
# focused Share Artifact endpoint and public-read tests.
PI01_TEAM_STATE_CITATION_PATHS = (
    'backend/api/share_cards.py',
)

# PI-02, August 25 2026. Since Yesterday citations bind the already-authored
# public adjacent-snapshot comparison to the existing immutable ShareArtifact
# lifecycle. Generation remains downstream of trusted snapshot publication;
# the public route only performs an exact, integrity-verified read. No Team
# State, change selection, evidence, or appearance-team authority moves.
PI02_SINCE_YESTERDAY_CITATION_PATHS = (
    'backend/api/share_cards.py',
    'backend/services/share_artifact_public.py',
    'backend/services/share_artifact_publication_hook.py',
    'backend/services/share_artifact_repository.py',
    'backend/services/share_artifact_since_yesterday.py',
)

# HIST-01, August 25 2026. Team State History reads only retained, published,
# integrity-verified Team State ShareArtifacts through one bounded public route.
# It does not recompute Team State, backfill dates, or read appearance-team
# authority. Exact dated claims and citation identities remain frozen by the
# existing ShareArtifact lifecycle and the focused History contract tests.
HIST01_TEAM_STATE_TIMELINE_PATHS = (
    'backend/api/team_history.py',
    'backend/services/team_state_history.py',
)

# HOTFIX-02, August 26 2026. New Share Artifacts must compute their immutable
# integrity hash while still draft and flush the complete sealed publication
# state once. This exact exception permits only the publication primitive repair;
# the Share Artifact model, schema, and neighboring services remain frozen.
SHARE_ARTIFACT_PUBLICATION_SEAL_PATHS = (
    'backend/services/share_artifacts.py',
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
