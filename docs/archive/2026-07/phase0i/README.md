# Phase 0I Roster Availability Context

Phase 0I status: complete.

This document records the implementation branch:
`phase-0i-roster-readiness-contract`.

Phase 0I makes roster availability context safe to use publicly by requiring a
fresh, complete official roster snapshot before BaseballOS serves current roster
depth claims. When that evidence is stale, missing, partial, or internally
inconsistent, the product fails closed: recent workload evidence can still be
shown, but current active-roster counts and usable-depth totals are withheld.

## Existing Architecture Verified

The canonical roster authority remains:

- `backend/services/roster_status.py`
- `backend/services/roster_authority.py`
- stored `RosterStatusSnapshot` rows
- official roster sync and roster source-readiness checks

The canonical workload authority remains the existing availability and workload
stack built from completed-game evidence. Phase 0I does not merge workload
availability with official roster status; it only gates public current-roster
claims on roster-source readiness.

## Public Contract

The public roster-readiness contract is `public_roster_readiness_v1`.

It records:

- whether current roster claims are available;
- whether roster-derived counts are withheld;
- which source family was checked;
- the last verified date, last attempted timestamp, data-through date, and
  stale threshold;
- typed reason codes;
- public reader limitations;
- coverage details for league or team scope.

The source authority is official MLB roster data as stored in roster status
snapshots. The contract does not treat workload rows, postgame boxscore rows, or
missing public flags as proof of active roster depth.

## Count Identities

When roster readiness passes, the established identities remain in force:

- `bullpen_arms` means confirmed active MLB bullpen candidates;
- `inactive_roster_context_count` means official off-active-roster bullpen
  context;
- `roster_unknown_count` means unconfirmed roster status;
- workload availability groups reconcile to the trusted active bullpen universe;
- IL, optioned/minors, 40-man-only, non-roster, DFA, special-list, and unknown
  statuses do not count toward confirmed active workload depth.

## Fail-Closed Behavior

Roster-derived public counts are withheld when:

- roster snapshots have never been fetched;
- the latest roster snapshot is stale for the served reference date;
- active team coverage is incomplete;
- unresolved roster-status failures exist;
- pitcher cache fields diverge from stored roster snapshots;
- required snapshot provenance is missing.

When withheld, count fields remain `null` instead of being converted to zero.
Evidence lists and category evidence are emptied so public consumers cannot
reconstruct current active-roster claims from unsafe partial data.

## Team Board

The Team Board keeps recent workload cards visible because those cards are
workload evidence, not current active-roster proof.

When roster readiness is not available:

- board group counts render as withheld;
- total pitcher counts are withheld;
- the Roster Authority banner explains that current usable bullpen depth is
  withheld until roster status is verified;
- the unavailable-roster toggle is disabled because unavailable roster context
  is not safe to expand;
- Recent Bullpen Work stays visible as workload evidence, but current-roster
  scope and per-appearance roster-status sentences are replaced by a roster
  coverage limitation;
- team context, team shape, and bullpen stress avoid zero-substituted roster
  counts.

## Dashboard

The league dashboard now carries the same roster-readiness contract. If roster
readiness is not available, the availability summary, injury and IL context
withhold league and followed-team roster counts and render the limitation
instead of implying a current active-roster picture.

## Postgame Cache Guard

Postgame pitching lines no longer create or restore `ACTIVE` roster status.
They may preserve a current team assignment when no official assignment evidence
blocks that update, but they write `UNKNOWN` roster status for postgame-created
or postgame-reactivated pitcher rows unless official roster evidence proves a
more specific status.

Official roster sync evidence remains authoritative over postgame cache writes.
Inactive, IL, optioned, minors, non-roster, 40-man-only, DFA, bereavement, and
unknown official statuses are not overwritten as active by final-game pitching
lines.

## Public Language Boundary

Phase 0I does not add private injury, health, medical, manager-intent, fantasy,
betting, or prediction claims. Public copy separates official roster status from
health certainty and keeps unknown roster status unknown.

## Surfaces Verified

Team Board and Dashboard received runtime changes. Today, Stories, Compare,
Pitcher Detail, All Pitchers/search, Recent Bullpen Work, Data & Trust, and
Methodology-facing copy were checked for unsupported current-roster, health, and
workload/roster-mixing claims; no Phase 0I redesign was introduced on those
surfaces.

## Deferred Work

- No migrations.
- No production backfill.
- No new roster ingestion source.
- No private injury or health interpretation.
- No broader player-stat or general roster-analysis surface.
- No Phase 0K methodology rewrite beyond recording this closeout.
- Between-games roster movement during doubleheaders remains unverified by this
  branch; if official roster evidence is not current enough for the served
  reference, public current-depth claims must continue to fail closed.

## Tests Added Or Updated

- Backend tests cover the public roster-readiness contract, missing-readiness
  count withholding, Team Board payload behavior, dashboard injury/IL
  withholding, roster sync provenance, and postgame roster-status cache guards.
- Frontend tests cover withheld Team Board counts, disabled unavailable-roster
  context, roster-limited Recent Bullpen Work framing, dashboard availability
  and injury/IL withheld states, and the operating-state adapter avoiding
  zero-substituted roster pressure.
- Existing roster status, roster authority, source readiness, dashboard,
  postgame, availability, comparison, stories, pitcher, and build gates were
  rerun for regression coverage.

## Known Limits

The contract can only certify the official roster snapshot evidence already
stored by the platform. If that stored evidence is stale, incomplete, or
inconsistent, the public product withholds current roster-depth claims rather
than inferring from workload evidence or old cache state.
