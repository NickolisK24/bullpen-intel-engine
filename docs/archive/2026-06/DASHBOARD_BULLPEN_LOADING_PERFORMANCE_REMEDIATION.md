# Dashboard and Bullpen Loading Performance Remediation

## Status

Complete.

## Scope

This remediation improves perceived loading quality for the Dashboard and
Bullpen pages before Recommendation Engine V2 Phase 11 mobile and accessibility
validation.

The work is limited to:

- backend availability evidence loading performance
- V2 bullpen-state API serialization performance
- duplicate Dashboard sync-status request removal
- frontend request de-duplication for concurrent identical GET requests
- regression tests and documentation

## Issue Found

Dashboard loading was slowed by two backend paths:

- `/api/bullpen/stats/overview`
- `/api/recommendations/v2/bullpen-state?limit=750`

Bullpen loading was slowed when fatigue data included broad stale/historical
sets through:

- `/api/bullpen/fatigue?limit=750&include_stale=true&with_meta=true`

The Dashboard also requested sync status twice: once directly for page-level
season and freshness state, and once again through the nested trust-strip
component.

## Root Cause

Availability classification read latest game dates and short workload windows
pitcher by pitcher. For broad bullpen views this created repeated database
queries even though the evidence could be loaded in batches.

The V2 bullpen-state endpoint also serialized the full internal V2 domain
object graph before reshaping it into the public API contract. That internal
serialization carried large nested context blocks that were not needed for the
public response shape.

## Fix Implemented

Backend availability evidence now batches:

- latest game date lookup by pitcher
- availability-window game-log lookup by pitcher
- classification input mapping for multi-pitcher endpoint responses

The public V2 bullpen-state API now builds a lean public serialization input
from the assembled V2 objects instead of requiring full internal context
serialization.

The Dashboard now reuses its existing sync-status request for the visible trust
strip.

The frontend API helper now de-duplicates concurrent identical GET requests.
This only applies while the same request is in flight. It does not cache
completed data and does not affect POST/write endpoints.

## Measured Behavior

Local Flask test-client measurements on the same local dataset:

| Endpoint | Before Avg | After Avg |
| --- | ---: | ---: |
| `/api/bullpen/stats/overview` | 470.4 ms | 42.5 ms |
| `/api/bullpen/fatigue?limit=750&include_stale=true&with_meta=true` | 490.7 ms | 54.1 ms |
| `/api/recommendations/v2/bullpen-state?limit=750` | 1625.1 ms | 419.0 ms |

Dashboard shell rendering is no longer tied to repeated sync-status requests.
Dashboard V2 bullpen intelligence still renders governed loading,
fail-closed, or unavailable states when applicable.

Bullpen filters, header, and table shell continue to render independently from
selected-pitcher detail surfaces. Fatigue-data loading now resolves as quickly
as the batched backend data path allows.

## Governance

No recommendation logic changed.

No fatigue formula changed.

No ranking, selection, prediction, best-pitcher, preferred-pitcher, or
recommended-pitcher UI was added.

Recommendation governance remains:

- `ranking_applied === false`
- `selection_made === false`

Recommendation Engine V1 and V2 behavior is preserved. The remediation changes
how evidence is loaded and serialized, not what the engines decide or display.

## Validation Coverage

Added or updated validation covers:

- batched availability evidence queries
- V2 API route avoiding full internal context serialization
- concurrent identical V2 GET request de-duplication
- Dashboard reuse of the existing sync-status request
- existing V1/V2 governance and forbidden-language checks

## Phase 11 Readiness

Recommendation Engine V2 Phase 11 mobile and accessibility validation may
resume after this remediation is merged.
