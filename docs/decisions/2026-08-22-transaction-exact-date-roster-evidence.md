# Transaction-Triggered Exact-Date Roster Evidence

Date: 2026-08-22
Status: Accepted

## Decision

Transaction ingestion may acquire a missing `RosterStatusSnapshot` immediately
after it canonically resolves a previously missing transaction pitcher. The
acquisition is limited to that ingestion cycle's newly resolved MLB person IDs,
their current transaction rows, each row's exact `transaction_date`, and MLB
clubs explicitly named by persisted `from_team_id` or `to_team_id`.

Every `(transaction_date, MLB team_id)` source request is deduplicated. All four
governed roster views must be readable. The participant must appear explicitly
in an endpoint club's exact-date official roster response. A participant found
on neither endpoint, on conflicting endpoint clubs, or only in another date's
evidence remains without a snapshot and therefore fails closed.

## Roster semantics and persistence

The targeted path reuses the canonical roster evidence merger, status
classifier, snapshot constructor, source provenance, unique pitcher/date key,
and team-conflict dead letter. It persists the roster status supplied by the
official source; transaction type cannot synthesize a desired status.

Snapshot persistence performs one bounded existing-row prefetch and one final
flush. An identical same-team snapshot is retained unchanged. An existing
different-team snapshot is not overwritten. This path does not correct or
replay snapshots for existing canonical pitchers and does not scan historical
dates outside the newly resolved participants' current transaction rows.

## Historical and correction boundaries

Persisted transaction `from_team_id` and `to_team_id` remain the only
transaction-time ownership authority. Mutable `Pitcher.team_id`, current roster
state, transaction prose, endpoint assumptions, and nearest prior or next
snapshots are prohibited inputs.

After the exact-date snapshot is flushed, the existing transaction alignment
reader consumes it. A previously stored transaction that changes from missing
identity or `roster_snapshot_missing` to aligned records the change through the
existing player-transaction correction provenance. No Share Artifact, frozen
Team Board publication, delta sidecar, or public response is rewritten.

## Fail-closed and product scope

Source failure, source omission, malformed evidence, wrong-team evidence, and
endpoint conflict preserve the existing missing or conflicting roster result.
This acquisition supplies only roster evidence. Unknown `SFA`, `SC`, and
uncertified `ASG` event authority remains blocked, and every independent
identity, participant, event, team, lifecycle, or window gate remains intact.

The decision does not change participant qualification, canonical pitcher
creation rules, transaction taxonomy, waiver claims, certified rehab exclusion,
Roster Context, Off-Active Count, active bullpen membership, Team State, Rest
Status, workload, Rotation Impact, Performance, or frontend behavior.
