# Bullpen Roster Composition Bugfix

## Public Feedback Source

A Reddit user reported that the Bullpen Board appeared to include Cincinnati
Reds starters and pitchers who were inactive or on the IL. The report was used
as the first reproduction case. No direct Reddit URL was provided with the
issue handoff.

## Reported Problem

The default Bullpen Board could represent a team's broader tracked pitcher pool
instead of the bullpen-relevant pitcher pool. For the Reds, the expanded
inactive/stale view exposed clear starters such as Andrew Abbott, Brady Singer,
Chase Burns, Nick Lodolo, and Rhett Lowder alongside relievers.

The risk was not Reds-specific. Any team with broad 40-man roster ingestion,
generic `P` positions, and recent starter workload could have the same default
bullpen composition problem.

## Reproduction Summary

The local Reds snapshot was stale relative to the active freshness window, so
the default Reds board returned zero current pitchers. Enabling inactive
pitchers exposed the underlying roster-composition issue: the board drew from
active tracked pitchers plus workload data and did not apply a bullpen
eligibility boundary before grouping availability.

The same pattern was checked against additional teams, where starter-length
usage patterns could enter bullpen-specific surfaces for non-Reds teams as
well.

## Root Cause

The root cause was in Bullpen Board filtering, with an upstream contribution
from roster ingestion:

- Roster ingestion seeds pitchers from the 40-man roster and marks them
  `active=True`.
- The `Pitcher` model does not store authoritative IL, optioned, active-roster,
  or probable-starter fields.
- Many MLB roster rows store a generic position value such as `P`, not `SP`,
  `RP`, or `CL`.
- The board path filtered for tracked active pitchers and recent workload, then
  grouped availability classifications directly.
- No reusable bullpen eligibility rule existed between broad pitcher
  availability data and bullpen-specific board counts.

## Fix

The fix adds a reusable backend bullpen eligibility filter and applies it before
Bullpen Board payload assembly:

- Explicit relief positions (`RP`, `CL`) are bullpen-relevant.
- Recent relief-length usage is bullpen-relevant when explicit roster role data
  is unavailable.
- Clear starter-length patterns are excluded from default bullpen counts.
- Inactive or stale bullpen-relevant pitchers are exposed only when inactive
  pitchers are included, and their cards carry an inactive-context label.
- Uncertain bullpen eligibility is withheld from default counts unless there is
  enough relief-length evidence to include it with a limitation.

The filter is team-agnostic. It does not hardcode the Reds or any player names.

## Why This Is Trust-Critical

Bullpen availability counts are only useful if the counted population is a
bullpen. Including starters, IL pitchers, inactive pitchers, or otherwise
non-bullpen arms makes availability totals look more complete than they are and
can mislead users about current bullpen shape.

This fix preserves the product boundary: it filters roster composition for a
descriptive bullpen surface only. It does not add prediction, fantasy,
betting, ranking, selection, matchup advice, or recommendation behavior.

## Tests Added Or Updated

- Reds default board excludes clear starters.
- Reds default board excludes inactive pitchers.
- Inactive toggle exposes stale bullpen-relevant pitchers with explicit
  inactive-context labeling.
- League-wide filtering works on a non-Reds team.
- Bullpen Board counts and context metrics exclude filtered starters.
- Broader team pitcher overview still shows the wider pitcher population.
- Limited relief-usage eligibility is surfaced with limitations.
- League-wide dashboard bullpen counts exclude clear starters.
- Frontend board cards render the inactive-context label.

## Remaining Limitations

- The current data model still does not store authoritative IL, optioned,
  active-roster, probable-starter, or transaction state.
- Eligibility is inferred from stored roster position and workload shape.
- Generic `P` roster positions require conservative usage inference.
- Edge cases such as openers, bulk relievers, rehab appearances, and recent role
  changes may still require better upstream roster or game-context data.

## Not Reds-Only

The implementation is a reusable bullpen eligibility filter shared by the team
board, comparison path, dashboard bullpen context, and landscape path. The Reds
case was the reproduction starting point, not a special-case branch.
