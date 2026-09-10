# D-055 Rest Status publication authority

- **Date:** 2026-08-20
- **Status:** Phase 1 implementation complete; integration pending
- **Scope:** Add a dormant D-055 Rest Status carrier to new immutable Team Board
  publications. D-055 meaning and public reader behavior are unchanged.

## Decision

Gap #51 uses a staged authority transition. Phase 1 gives the publication
writer enough authority to store the exact completed D-055 `rest_status`
object. It does not make that carrier a public-reader dependency.

`backend/services/bullpen_board.py` remains the sole Rest Status semantic owner.
Publication calls its thin `author_rest_status` wrapper around the existing
`build_rest_status` implementation once per represented team, then stores the
complete result by value in the immutable `trusted_team_boards` package.

The D-055 population, evidence gates, counting rules, summary wording, and
zero/null/unavailable behavior are unchanged.

## Phase 1: dormant writer capability

New publication candidates store:

- the complete existing `rest_status` public object;
- `method_version = d055_rest_status_v1`;
- `public_contract_version = d055_rest_status_public_v1`;
- the existing Team Board package contract;
- population basis `represented_default_visible_active_bullpen`;
- population authority `trusted_team_boards.default_pitcher_ids`;
- membership authority `eligible_bullpen_pitcher_contexts`;
- reference-date policy `d055_availability_reference_date_v1`; and
- the package's exact availability reference date.

The containing Dashboard snapshot remains the authority for team identity,
represented date, snapshot and sync-run identity, publication state, and trust.

Readers retain their pre-Phase-1 behavior. `/board` and `/board-v2` continue to
author Rest Status through the current canonical request path and do not consume
or require the dormant carrier. A historical package without the new field
therefore behaves exactly as it did before Phase 1.

No historical package is replayed, mutated, backfilled, or assigned a synthetic
carrier. Only newly constructed publication candidates can contain the field.

## Production carrier qualification

Mechanism capability is not production qualification. After Phase 1 merges and
deploys, one naturally scheduled, first-attempt full-daily publication must be
observed read-only.

The qualification predicate requires a persisted, ready, published Dashboard
snapshot with publication identity, the expected Team Board package contract,
matching represented/reference dates, complete represented-team coverage, exact
D-055 version and population authority, and one structurally valid carrier for
every represented team. A governed unavailable Rest Status is valid; a missing,
unstamped, malformed, partial, candidate-only, or unpublished carrier is not.

Qualification does not mutate or promote a snapshot. Failed publication cannot
qualify, and ordinary workflow dispatch is not a substitute for the scheduled
production writer.

## Phase 2: reader enforcement

Phase 2 is not implemented here. It may begin only after production carrier
qualification succeeds. That separate package will make `/board` consume the
frozen carrier, route `/board-v2` through the same trusted frozen board, and
prohibit request-time D-055 recomputation on both trusted public routes.

## Gap boundaries

Gap #31 means a future D-055 `rest_status.rested_arm_count` delta. It remains
open: Phase 1 does not place Rest Status in the delta sidecar and does not begin
comparison evidence. Future comparison must use frozen publication values only.

Per-arm Clean Option movement remains Gap #29. Team State What Changed and the
Gap #50 Arm Read substrate are unchanged. No `/changes` field, frontend path,
database table, migration, or historical snapshot changes in Phase 1.

## Freeze authority

The only frozen production path authorized in Phase 1 is:

- `backend/services/bullpen_board.py`

`backend/services/public_serving_authority.py` owns the trusted writer carrier
and is not freeze-listed. No API route, Team Board v2 path, directory, wildcard,
or generic public-surface exception is granted.
