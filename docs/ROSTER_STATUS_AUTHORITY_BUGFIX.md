# Roster Status Authority Bugfix

## Problem Summary

The previous bullpen eligibility bugfix removed clear starter patterns from
default bullpen boards, but it did not solve roster-status authority. BaseballOS
could still show pitcher cards as workload Available, Monitor, or Limited based
on stored usage while having no authoritative way to know whether those pitchers
were active MLB bullpen options, on an injured list, in the minors, optioned,
DFA, non-roster, or only present as 40-man-only roster status.

The key distinction:

- Usage freshness answers whether stored workload data is current.
- Bullpen eligibility answers whether the pitcher is bullpen-relevant.
- Roster status answers whether the pitcher is currently an active MLB roster
  option.

Default bullpen boards must not treat recent usage, stale usage, or the legacy
`Pitcher.active` flag as active MLB roster authority.

## Why The Previous Fix Was Incomplete

The prior fix correctly filtered obvious non-bullpen starters, but it still used
a data model where `Pitcher.active=True` came from broad tracked pitcher storage.
In the current seed path, pitchers are loaded from the MLB `40Man` roster and
stored as active. That field is not equivalent to active MLB availability.

As a result, a pitcher could be bullpen-relevant by usage but still not be an
active planning option because roster status was IL, minors, optioned, DFA,
non-roster, or unknown.

## Cincinnati Reds Reproduction Case

The Reds report exposed the remaining defect:

- Graham Ashcraft was reported as IL-60 but appeared in bullpen context.
- Pierce Johnson was reported as IL-15 but appeared in bullpen context.
- Emilio Pagan was reported as IL-15 and needed roster-status-aware context.
- Connor Phillips and Jose Franco were reported as Minors and needed minors
  context rather than stale workload context.
- Chase Burns, Hunter Greene, Rhett Lowder, Brandon Williamson, Andrew Abbott,
  Nick Lodolo, and Brady Singer remain regression examples for the starter and
  roster-status boundary.

Local database inspection before this bugfix showed those Reds rows only had
`active=True`, `position='P'`, team fields, and game logs. There were no stored
IL, minors, optioned, DFA, non-roster, active-roster, or 40-man-only fields.

## Root Cause

Roster authority did not exist as a separate domain. The board pipeline mixed
three concepts:

- The legacy pitcher row was considered active because it was tracked locally.
- Recent or stale workload determined availability and freshness.
- Bullpen eligibility determined role relevance.

Without a roster-status layer, the UI could not distinguish "stale workload
context" from "not an active MLB roster option."

## Local Roster-Status Authority

Before this change, authoritative roster status did not exist locally. The
committed pitcher schema had no roster-status columns, and the live development
database had the same limitation.

This bugfix adds nullable storage for future authoritative roster status:

- `pitchers.roster_status`
- `pitchers.roster_status_source`
- `pitchers.roster_status_updated_at`

The fields are intentionally nullable. Unknown status must degrade with a clear
limitation instead of being promoted to active MLB status.

## Implementation Details

New backend service:

- `backend/services/roster_status.py`

It normalizes roster statuses including:

- `ACTIVE`
- `IL_10`
- `IL_15`
- `IL_60`
- `MINORS`
- `OPTIONED`
- `DFA`
- `NON_ROSTER`
- `40_MAN_ONLY`
- `UNKNOWN`

Board behavior:

- Default boards exclude known inactive roster statuses.
- The unavailable-pitchers toggle may include unavailable roster-status cards.
- Unavailable roster-status cards are forced to `Unavailable`, never
  `Available`.
- Unknown roster status is allowed only as a limited state with this limitation:
  `Roster status unavailable; bullpen eligibility is based on stored usage and position data.`
- Roster status is exposed separately from freshness, eligibility, role, and
  availability on each board card.
- Top-level board metadata summarizes roster-status authority, known active
  counts, unknown counts, unavailable pitcher counts, and excluded inactive counts.

Frontend behavior:

- Pitcher cards now display roster-status chips such as `Active MLB`, `IL-60`,
  `IL-15`, `Minors`, or `Roster Unknown`.
- The board now shows a roster-status summary banner when roster authority is
  partial, unavailable, or context-only.
- The unavailable-pitchers toggle no longer defines inactive pitchers as "no games in
  the last 14 days."

Ingestion preparation:

- The pitcher model and migration now support nullable roster-status storage.
- The seed path stores a normalized roster status when the MLB roster payload
  provides a status field.

## Tests Added Or Updated

Backend coverage:

- Roster-status normalization and unknown-status limitation.
- IL pitchers excluded from default board counts.
- IL pitchers shown as unavailable pitchers, not Available, when the toggle is included.
- Minors pitchers excluded by default.
- Minors pitchers clearly labelled when context is included.
- Roster status remains distinct from usage freshness.
- Reds fixture coverage for Graham Ashcraft IL-60 and Pierce Johnson IL-15.
- League-wide filtering with non-Reds teams.
- Dashboard and landscape population counts exclude known inactive statuses.

Frontend coverage:

- Roster Unknown renders separately from stale workload copy.
- IL-60 and Minors context labels render on cards.
- Unavailable roster-status cards render as Unavailable, not Available.
- Roster-status summary copy distinguishes roster authority from workload
  freshness.

## Remaining Limitations

- Existing local pitcher rows do not automatically gain authoritative status
  until roster data is refreshed or backfilled.
- Current sync still primarily updates workload logs and fatigue scores; roster
  authority depends on stored roster-status fields being populated.
- Unknown roster status remains data-limited. The board does not claim those
  pitchers are active MLB roster options.
- Official roster statuses can change daily, so roster-status freshness should
  become its own sync/backfill concern before production reliance.

## Trust Impact

This bugfix prevents the most damaging trust failure: presenting IL, minors,
optioned, DFA, non-roster, or 40-man-only status as active bullpen
availability when authoritative status data is present.

It also fails closed when status is unknown by surfacing the limitation instead
of silently calling a pitcher active. Usage freshness, bullpen eligibility,
roster status, role, and availability are now visibly separate.

## League-Wide Scope

The fix is league-wide. Reds players are used only as regression fixtures and
documentation examples. The roster-status service and board filtering apply to
all teams through the shared board, comparison, dashboard, and landscape
assembly paths.
