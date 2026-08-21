# Decision: Team Board Active Bullpen WHIP

- **Date:** August 21, 2026
- **Owner:** Nickolis Kacludis
- **Status:** Adopted
- **Scope:** M-002 on the Team Board public Performance read

## Decision

Register M-002 Current Active-Pen WHIP with public name **Active Bullpen WHIP**
and method version `1.0.0`. It inherits the Current Active-Pen Performance
population, current regular-season window, official completed relief-game
selection, represented date, freshness, and `GameLog.appearance_team_id`
ownership. It is approved only for the Team Board.

The formula is:

`(walks + hits_allowed) * 3 / recorded_outs`

All arithmetic uses pooled exact integers. The result is rounded once with
`ROUND_HALF_UP` to two decimal places. Displayed baseball innings and rounded
pitcher values never enter the calculation. Official `baseOnBalls` is the
stored walk input; intentional walks count as ordinary walks for official
record-keeping. Hit batsmen, errors, and fielder's-choice reaches are excluded.

## Completeness

Hits, walks, and recorded outs are required on every qualifying relief line.
The source extraction and official-line reconciliation already retain and
validate these fields. The canonical writer now preserves an omitted hit or
walk as null instead of assigning zero, and the ORM supplies no client-side
default for either column. A missing, malformed, or negative required input
refuses M-002; the line is not dropped and no value is imputed.

This rule is metric-local. A valid M-001 ERA remains public if a WHIP input is
unavailable, and the Performance section reports the WHIP limitation without
suppressing ERA.

## Minimum sample

M-002 independently approves 108 recorded outs (36.0 innings). It does not
inherit D-023 merely because M-001 uses the same number. Both metrics observe
the same active group and current-season innings sample, and both use recorded
outs as their denominator authority. At 108 outs one additional hit or walk
moves exact WHIP by `3 / 108 = 0.027777...`, below 0.03 before display rounding.

Below 108 outs no numeric WHIP is published. The existing backend-authored
**Not Enough Innings Yet** read carries the current and required innings.

## Boundaries

This decision does not authorize K-BB%, HR rate, inherited-runner context,
Team State, Share Artifact performance, historical comparison, rankings,
grades, frontend arithmetic, or any change to workload, rest, role,
deployment, roster, Rotation Impact, or What Changed.
