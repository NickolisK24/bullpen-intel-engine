# Transaction Event Code Authority

Date: 2026-08-22
Status: Accepted

## Decision

The structured MLB transaction codes `CU`, `DES`, and `SE` are governed as
one-to-one aliases of existing canonical BaseballOS transaction categories:

- `CU` to `recall`
- `DES` to `dfa`
- `SE` to `contract_selection`

The MLB transaction source identifies these codes respectively as `Recalled`,
`Designated for Assignment`, and `Selected`. Ingestion normalizes the structured
code directly; transaction description text is not parsed and the public reader
does not carry raw-code aliases.

Existing backend-authored public labels and descriptions remain authoritative.
No public category or response field is added.

## Persistence and correction

`PlayerTransaction.normalized_category` remains the persisted event authority.
Natural transaction resync applies the deterministic mapping through the
existing source-correction policy, which may correct a current-window row that
was previously stored as `unknown`. This decision authorizes no bespoke
backfill, replay, or request-time reconstruction.

Transaction date, transaction key, participant qualification, canonical
pitcher linkage, `from_team_id`, `to_team_id`, roster alignment, and source
window semantics are unchanged.

## Fail-closed boundary

`SC`, `ASG`, `CLW`, and `SFA` remain unresolved. `SC` is heterogeneous, while
the other codes require separate public-taxonomy or materiality decisions.
Malformed, ambiguous, and all other unknown structured codes also remain
`unknown`; no generic fallback category is introduced.

## Scope

This decision changes transaction event-category authority only. It does not
change transaction participant qualification, historical team attribution,
Roster Context, Off-Active Count, active bullpen membership, Team State, Rest
Status, workload, Rotation Impact, Performance, Recent Relief Work, or frontend
presentation.
