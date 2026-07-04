# Phase 0D Base-State Gap Decision Record

## Verified Schema Gap

The stored final play-by-play foundation keeps normalized event facts such as
game identity, event order, inning, half-inning, post-play outs, post-play
score, pitcher identity, batter identity, team identity, and source provenance.

It does not store base-runner state before or after a play.

Because runner occupancy is not stored on `game_play_by_play_events`, Phase
0D-03 cannot determine runners on base when a pitcher entered from the stored
PBP foundation.

## Current Decision

`appearance_entry_base_state` remains `UNKNOWN` for every eligible appearance.

Phase 0D-03 does not reconstruct runner state from plate appearance sequences,
scoring plays, event text, or inferred advancement.

The gap is recorded as evidence so downstream work can cite the limitation
instead of treating an entry as clean or traffic-laden from PBP.

The decision is made in 0D-09, not here.

## Resolution Paths

1. Future scoped 0C-style base-state foundation addendum.

   This path would store runner state on normalized events, add correction
   policy coverage, define re-normalization behavior for source corrections,
   and validate that stored runner state is finality-safe.

2. Permanent acceptance of boxscore-only inherited attribution.

   This path would keep PBP entry base state unknown and rely only on
   boxscore-backed `game_logs.inherited_runners` and
   `game_logs.inherited_runners_scored` where those fields exist. The tradeoff
   is per-appearance attribution without per-play or per-inning base-state
   granularity.

## Consequences

For 0D-04 inherited traffic:

- inherited-runner facts can cite boxscore-backed game-log fields
- PBP cannot say whether entry base state was clean or traffic-laden
- zero inherited runners is a boxscore interpretation, not a reconstructed PBP
  base state

For 0D-07 pressure context:

- base occupancy cannot be used as an input unless a later foundation addendum
  stores runner state
- pressure-like reads must stay out of 0D-03

For per-inning clean/traffic granularity:

- Phase 0D-03 cannot classify an inning or entry as clean from PBP
- later clean/traffic work must either use boxscore fields with clear limits or
  wait for a base-state foundation addendum

## Exit Decision

Phase 0D-09 decides whether BaseballOS adds a base-state foundation addendum or
permanently accepts boxscore-only inherited attribution with documented
granularity limits.
