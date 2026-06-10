# Bullpen Board Roster Wording

## Reason For The Change

The Bullpen Board now has authoritative roster-status data and roster-aware
filtering. The old wording exposed internal product terminology instead of
plain baseball language.

The old inactive/context wording was especially unclear because it could read
as injury status, minor-league status, stale workload data, uncertain bullpen
role, or unknown roster status.

## New Wording

- `Bullpen Arms`
- `Unavailable Pitchers`
- `Unavailable due to roster status`
- `Not available for bullpen planning`
- `40-Man Only`

## Why This Is Clearer

`Unavailable Pitchers` tells users that these pitchers are shown for roster
awareness but are not active bullpen planning options. The card still carries
the specific roster reason, such as `IL-60`, `IL-15`, `Minors`, `Optioned`,
`DFA`, `Non-Roster`, or `40-Man Only`.

`Bullpen Arms` identifies active bullpen-relevant pitchers without requiring
users to understand internal eligibility states.

## Current Board Behavior

The default board shows active bullpen-relevant arms. Clear starters are
excluded from default bullpen planning. Unavailable pitchers are separated from
bullpen arms and carry roster reasons, including IL, minors, optioned, DFA,
non-roster, 40-man-only, released/no-organization, or unknown ownership when
applicable.

## Scope

This is a UI wording and clarity change. It does not intentionally change
roster-status ingestion, roster-status normalization, default board filtering,
or inactive/unavailable toggle behavior.
