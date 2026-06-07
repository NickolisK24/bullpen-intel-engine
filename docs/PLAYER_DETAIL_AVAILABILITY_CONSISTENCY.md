# Player Detail Availability Consistency

## Bug Summary

The Tonight's Bullpen Board used roster-adjusted availability, while the Player
Detail panel used raw workload availability from the pitcher fatigue endpoint.
That created a trust-critical contradiction for pitchers with authoritative
inactive roster statuses.

Examples:

- Graham Ashcraft could appear on the board as `Unavailable` due to `IL-60`,
  while Player Detail still presented workload-only `Available`.
- Emilio Pagan could appear on the board as `Unavailable` due to `IL-15`, while
  Player Detail still presented workload-only `Monitor`.
- Pierce Johnson had the same IL-15 risk.

## Final Availability vs Workload Signal

Player Detail now treats these as separate concepts:

- `Final Availability`: roster-adjusted availability used for bullpen planning.
- `Roster Status`: authoritative roster context such as `Active MLB`, `IL-60`,
  `IL-15`, `Minors`, or `40-Man Only`.
- `Workload Signal`: workload-only availability before roster-status
  adjustment.

For inactive roster statuses, final availability is `Unavailable` even when the
workload signal is light or moderate.

Current roster-status labels include `Active MLB`, `IL-15`, `IL-60`, `Minors`,
`40-Man Only`, `Optioned`, `DFA`, `Non-Roster`, and `Roster Unknown`.
Released/no-organization and unresolved ownership states clear stale team
assignment fail-closed before team-scoped bullpen planning views are assembled.

Example:

```text
Roster Status: IL-60
Workload Signal: Available
Final Availability: Unavailable
Reason: Roster status: IL-60.
Limitation: Unavailable due to roster status; not available for bullpen planning.
```

## Implementation

`GET /api/bullpen/fatigue/<pitcher_id>` now returns:

- `availability`: final roster-adjusted availability, matching board semantics.
- `workload_signal`: raw workload-only availability.
- `roster_status`: the roster-status classification used for the override.

The Player Detail summary renders `Final Availability`, `Roster Status`, and
`Workload Signal` as distinct labels. Workload/fatigue evidence remains visible,
but it is no longer presented as the final bullpen-planning state when roster
status overrides it.

## Tests Added

- Backend API regression coverage for Graham Ashcraft, Emilio Pagan, Pierce
  Johnson, and Brock Burke.
- Frontend rendering coverage for IL-60 and IL-15 detail summaries.
- Frontend source guard confirming `PitcherDetail` passes `workload_signal` and
  `roster_status` into the final availability summary.

## Trust Impact

Player Detail and the Bullpen Board now agree on final availability. Inactive
roster statuses cannot present workload-only `Available` or `Monitor` as the
primary detail state. The workload signal remains visible as context, but final
availability remains the roster-adjusted planning status.
