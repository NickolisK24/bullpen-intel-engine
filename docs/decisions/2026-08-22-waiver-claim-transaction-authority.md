# Waiver Claim Transaction Authority

Date: 2026-08-22
Status: Accepted

## Decision

The structured MLB transaction code `CLW` is governed as a one-to-one mapping
from `CLW` to `waiver_claim`. Across the reliable 2026-03-01 through 2026-08-22
source interval, all 76 `CLW` rows carried MLB clubs as both transaction-time
endpoints and the structured `typeDesc` value `Claimed Off Waivers`.
Human-readable description text is audit validation only and is not parsed by
ingestion or the public reader.

A waiver claim is a public-material organizational transfer for Recent
Transactions. It changes control of the participant from the persisted
`from_team_id` club to the persisted `to_team_id` club. It does not, by itself,
assert active-roster membership, bullpen usage, or future role.

The canonical public category is `waiver_claim`, with the backend-authored
label `Claimed off waivers` and neutral description `{name} was claimed off
waivers.`

## Alignment and persistence

The existing transaction ingestion boundary owns normalization. A claim is
explanatory-eligible only when canonical pitcher identity exists and an exact
transaction-date roster snapshot belongs to either persisted transaction
endpoint. The snapshot may prove source-side or destination-side alignment; it
does not need to show active-roster membership. Missing or conflicting snapshot
authority remains fail-closed.

Natural transaction resync may deterministically correct current-window rows
from `unknown` to `waiver_claim` under the existing source-correction policy.
No bespoke backfill, request-time reconstruction, or historical publication
mutation is authorized.

## Historical ownership and fail-closed boundary

Transaction date, transaction key, participant qualification, canonical
pitcher linkage, and persisted `from_team_id` / `to_team_id` remain unchanged.
Mutable current `Pitcher.team_id` has no role in historical claim ownership.

`SC`, `SFA`, and uncertified `ASG` remain unresolved, as do malformed and all
other unknown structured event codes. Certified pitcher rehab assignments
remain governed non-material under their independent authority. No generic
fallback category is introduced.

## Product scope

This decision changes event-category authority only. It does not change roster
authority, Roster Context, Off-Active Count, active bullpen membership, Team
State, Rest Status, workload, Rotation Impact, Performance, Recent Relief Work,
or frontend layout and derivation.
