# Decision: Team Board Recently Used Arms

- **Date:** August 21, 2026
- **Owner:** Team Board public read model
- **Contract:** `team_board_recently_used_arms_v1`

## Decision

The Bullpen Summary publishes **Recently Used Arms** as the number of pitchers
in the represented Team Board's current default-visible active bullpen who
made at least one governed relief appearance during the three calendar days
through the represented date.

The inclusive window is `[D-2, D]`. The reader-facing window label is
`Last 3 days`.

## Why three days

No existing public concept answered the headline question exactly. Rest Status
owns worked-yesterday semantics. Public workload windows own 7-day and 14-day
team relief totals, not the current active-arm count. The older Bullpen
Stability read uses a 14-day churn-oriented definition and does not own the
current Team Board appearance-team contract.

Three days is the narrowest existing product-recognized recency horizon that
is distinct from yesterday and materially narrower than the 7-day workload
window. It is an orientation count, not a workload score or availability
classification.

## Authority

The population is the already-governed Team Board current active bullpen:
`current_scored_bullpen_eligible_pitchers` after default-visibility filtering.

The appearance source is the existing Recent Relief Work chronology:
`official_recent_team_relief_appearance_rows`. That owner already enforces
official `GameLog.appearance_team_id` ownership, excludes credited starts, and
anchors rows to the represented data-through date. The Team Board composer
only intersects pitcher identities; it makes no query and does not
reclassify an appearance.

One pitcher counts at most once regardless of appearances. An off-active or
otherwise non-default-visible pitcher does not count. An appearance on `D`
or `D-2` counts; one on `D-3` does not. Future-dated appearances invalidate
the read.

## Fail-closed behavior

An authoritative empty window publishes zero. Missing or mismatched reference
dates, unavailable current-population authority, malformed relief rows,
unavailable in-window groups, or unresolved appearance-team attribution
withhold only Recently Used Arms. They never become zero and do not suppress
Recent Usage, Rest Status, or another Team Board section.

## Boundaries

This decision changes no Team State, Arm Read, workload, Rest Status,
Performance, Roles and Deployment, Rotation Impact, roster, What Changed,
publication, or historical reconstruction behavior. The frontend renders the
backend-owned count and window label without filtering or arithmetic.
