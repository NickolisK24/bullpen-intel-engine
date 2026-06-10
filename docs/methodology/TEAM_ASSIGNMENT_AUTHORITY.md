# Team Assignment Authority

BaseballOS stores pitcher organization ownership on `Pitcher.team_id`,
`Pitcher.team_name`, and `Pitcher.team_abbreviation`. Those fields drive
team-scoped bullpen boards, dashboard landscape grouping, game context, and
team filters.

## Root Cause

Before this change, ownership was written during seeding from MLB 40-man roster
data and was not refreshed as current team authority. Roster-status sync checked
only the team already stored on each pitcher row. When a pitcher moved to
another organization, the old team roster no longer contained that player, so
the row could be marked `roster_sync:unavailable` while still retaining the
stale `team_id`. That allowed stale-team records to remain eligible for
team-scoped views.

Examples that exposed this risk include Joel Kuhnel, Connor Seabold, Simeon
Woods Richardson, Craig Kimbrel, Trevor Richards, Justin Lawrence, Ryan
Borucki, Matt Pushard, Yeondrys Gomez, and Cionel Perez. These names are
regression fixtures only; synchronization is keyed by MLB player id and
authoritative MLB ownership evidence.

## Authority Source

The authority chain is:

1. MLB Stats API team roster endpoints across all MLB organizations:
   `active`, `40Man`, `fullRoster`, and `nonRosterInvitees`.
2. MLB Stats API player lookup via `people/{player_id}` when team roster
   evidence is absent.
3. Explicit fail-closed `UNKNOWN` ownership when neither source can resolve a
   confident assignment.

Roster endpoint precedence is `active`, then `40Man`, then `fullRoster`, then
`nonRosterInvitees`. If a player appears on exactly one team in the highest
available roster tier, that team becomes the local assignment. If the evidence
is ambiguous, the row is not left on the stale team.

## Sync Behavior

The sync flow is now:

```text
MLB authority source
-> current team resolution
-> team assignment sync
-> Pitcher.team_id update or fail-closed clearing
-> roster status sync
-> game log/workload sync
-> fatigue and availability calculation
-> team-scoped views
```

`services.team_assignment_sync.sync_team_assignments()` runs before
`sync_roster_statuses()` in both manual and scheduled syncs. It updates:

- `Pitcher.team_id`
- `Pitcher.team_name`
- `Pitcher.team_abbreviation`
- `Pitcher.active`
- `Pitcher.team_assignment_status`
- `Pitcher.team_assignment_source`
- `Pitcher.team_assignment_updated_at`

If a pitcher appears on another organization roster, the local row is reassigned
to that organization before roster status is refreshed. Team boards and the
dashboard then consume the corrected ownership naturally through existing
`team_id` filters and grouping.

## Released And Free-Agent Handling

When player lookup reports a released, free-agent, unsigned, or equivalent
no-organization status, BaseballOS stores:

- `team_assignment_status = NO_ORGANIZATION`
- `team_id = NULL`
- `team_name = NULL`
- `team_abbreviation = NULL`
- `active = false`

The row remains in the database for historical game logs and fatigue history,
but it no longer appears as part of a stale team bullpen.

## Unknown Ownership

When ownership cannot be resolved, BaseballOS stores:

- `team_assignment_status = UNKNOWN`
- `team_id = NULL`
- `team_name = NULL`
- `team_abbreviation = NULL`
- `active = false`

This is intentionally fail-closed. Unknown ownership is tracked explicitly
instead of silently preserving an old organization. The row can become active
again on the next sync if roster or player lookup authority later resolves a
current team.

## Trust Impact

This correction protects team-scoped bullpen surfaces from stale ownership:

- old-team bullpen boards stop showing reassigned, released, or unknown players
- new-team boards receive reassigned players before roster status refresh
- dashboard landscape grouping uses corrected team ownership
- sync payloads expose reassigned, no-organization, unknown, and error counts
- released, no-organization, or unresolved ownership clears stale team
  assignment fail-closed before bullpen planning views are assembled

## Remaining Limitations

The current implementation uses team roster endpoints and player lookup. It
does not yet store transaction-event lineage, claim dates, signing dates, or
release dates from the transaction feed. If MLB roster and player lookup data
are both unavailable or contradictory, BaseballOS clears the stale team and
marks ownership `UNKNOWN` until a later sync resolves it.

This means BaseballOS can explain the current authoritative ownership state but
not yet the full transaction history that caused the state change.
