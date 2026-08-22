# Canonical Transaction Pitcher Acquisition

Date: 2026-08-22
Status: Accepted

## Decision

Transaction ingestion may acquire a missing canonical `Pitcher` only when the
participant has a positive MLB person ID and the existing deduplicated MLB
`/people` response explicitly proves pitcher or two-way `primaryPosition`
authority. A complete authoritative `fullName` is also required. Transaction
copy, event code, endpoints, current team assignment, and absence of another
player type cannot authorize creation.

Missing, malformed, conflicting, non-pitcher, or ambiguous MLB person evidence
remains unresolved. Two-way players remain pitcher-relevant.

## Canonical identity and current-state boundary

The acquisition reuses the D-009 minimal canonical identity contract. The MLB
person ID is the unique key. The new row contains only canonical name, explicit
pitcher/two-way position, `active=False`, and governed unknown roster status.
It carries no `team_id`, team name, team abbreviation, assignment status, or
assignment provenance. Persisted transaction-time `from_team_id` and
`to_team_id` remain the only historical team authority.

The initial canonical prefetch is followed by one conflict-safe bulk insert and
one bounded refresh query. The unique MLB ID conflict rule reuses a canonical
row that appears concurrently or on a repeated sync. Multiple transactions for
one participant produce one candidate and one canonical identity. No public
reader lookup, network request, per-row query, or per-row commit is introduced.

## Transaction completeness

Acquisition supplies only canonical identity. Event taxonomy, exact
transaction-date roster alignment, participant evidence, historical team
attribution, and source-window authority remain independent fail-closed gates.
An acquired `SFA` participant therefore remains event-blocked. A governed CLW,
SE, or OPT row without exact event-date roster authority remains roster-blocked.
Natural transaction resync may correct `pitcher_id` and downstream alignment
under the existing source-correction policy; no bespoke backfill is authorized.

The Team Board and Recent Transactions public response shapes do not change.

## Scope

This decision does not change `SC`, `SFA`, generic `ASG`, waiver-claim
semantics, rehab materiality, roster authority, Roster Context, Off-Active
Count, active bullpen membership, Team State, Rest Status, workload, Rotation
Impact, Performance, or frontend behavior.
