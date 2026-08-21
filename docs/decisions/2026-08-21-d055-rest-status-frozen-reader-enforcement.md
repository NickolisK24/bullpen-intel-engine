# D-055 Rest Status frozen-reader enforcement

- **Date:** 2026-08-21
- **Status:** Implementation complete; integration pending
- **Scope:** Activate the already-qualified frozen Rest Status carrier for the
  trusted Team Board readers. D-055 semantics and publication authoring do not
  change, and Rest Status comparison remains out of scope.

## Production qualification

Scheduled first-attempt workflow run `32472742333`, sync run `813`, published
Dashboard snapshot `626`, represented date `2026-08-20`, and availability
reference date `2026-08-21` established the Phase 2 activation boundary.
`qualify_rest_status_carrier(snapshot_626)` returned `qualified=true` for all
30 represented teams: 17 carriers were available, 13 were governed unavailable,
and none were missing, malformed, unstamped, or incompatible.

This was a natural scheduled publication, not a fixture or historical repair.

## Decision

Trusted `/board` reads project the complete frozen `rest_status` object from the
team entry in `trusted_team_board_publication_v1`. Trusted `/board-v2` reads use
`build_published_team_board` as the same base authority and then apply only the
existing v2 read-model composition. Both surfaces therefore expose the same
publication's D-055 object.

Trusted request-time D-055 recomputation is prohibited. `author_rest_status`
and `build_rest_status` remain authorized only where the existing canonical
publication or explicit non-trusted computation paths need to author a value.
The Phase 1 writer remains unchanged.

## Frozen authority

The reader requires the existing authority exactly:

- method `d055_rest_status_v1`;
- public contract `d055_rest_status_public_v1`;
- Team Board package contract `trusted_team_board_publication_v1`;
- population basis `represented_default_visible_active_bullpen`;
- population authority `trusted_team_boards.default_pitcher_ids`;
- membership authority `eligible_bullpen_pitcher_contexts`;
- reference policy `d055_availability_reference_date_v1`; and
- the package's exact availability reference date.

The frozen object retains exactly `available`, `active_arm_count`,
`rested_arm_count`, `worked_yesterday_count`, `back_to_back_count`, `summary`,
and `reason_code`. Zero remains zero. A valid governed-unavailable object remains
verbatim unavailable with withheld counts and its backend-owned reason.

## Fail-closed and historical behavior

A missing historical carrier yields scoped `frozen_rest_status_missing`.
Malformed values or incompatible authority yield scoped
`frozen_rest_status_invalid`. Neither case authorizes replay, current-roster
reinterpretation, package repair, backfill, synthetic stamping, or mutation of
any snapshot or sidecar.

Reader-time changes to mutable workload or roster rows cannot refresh the
published Rest Status. The immutable carrier remains the only trusted authority.

## Gap and evidence boundaries

Gap #31 remains `OPEN — REST STATUS DELTA AUTHORITY NOT ACTIVATED`. This decision
does not add Rest Status to the delta sidecar, compare `rested_arm_count`, change
`/changes`, add materiality rules, or change What Changed rendering.

Snapshot 626 remains the first natural endpoint for Arm Read, workload 7d/14d,
Rotation Impact, bullpen membership, and deployment profile. This reader change
does not alter any of their method, public, carrier, population, reference, or
compatibility authority and does not restart those evidence clocks.

## Query and presentation boundary

`/board-v2` replaces its live full-board construction with the existing trusted
published-board read. It does not add a package fetch, per-pitcher query, D-055
query, or second package parser. Its other independently governed optional
sections keep their existing owners. The frontend receives the same seven-field
Rest Status object and requires no change.

## Freeze authority

This decision authorizes exactly:

- `backend/api/team_board_v2.py`; and
- `backend/services/bullpen_board.py`.

The first routes the real v2 endpoint through existing trusted authority. The
second adds an explicit frozen projection mode while preserving live authoring
for publication and non-trusted callers. No wildcard, directory, generic API,
frontend, What Changed, Share Artifact, or migration exception is granted.
