# Roster Status Sync Implementation

## Authority Source

BaseballOS uses the existing MLB Stats API team roster endpoint as the roster
status authority:

```text
GET https://statsapi.mlb.com/api/v1/teams/{teamId}/roster
```

The sync compares these roster views:

- `active`
- `40Man`
- `fullRoster`
- `nonRosterInvitees`

This keeps BaseballOS inside its existing MLB Stats API source set. No new data
provider or dependency is introduced.

## Sync Flow

```text
team assignment sync
    -> MLB roster evidence merge by MLB player id
    -> roster status normalization
    -> pitchers.roster_status persistence
    -> game log/workload sync
    -> fatigue and availability calculation
    -> trust/freshness reporting
    -> board and Player Detail final availability
```

Team assignment sync runs before roster-status sync so reassigned, released, or
unresolved players do not remain attached to stale teams while roster status is
being refreshed.

Roster sync runs in three places:

- Manual `POST /api/bullpen/sync`
- Scheduled `run_daily_sync`
- The database seeder after pitcher rows are loaded

## Shared Roster Evidence Within One Run

Team assignment and roster status read the same official roster views for the
same clubs. `services.roster_evidence.RunRosterEvidence` fetches each
`(team_id, roster_type)` view at most once per scheduled run and hands both
consumers the same official response, so the scheduled daily sync issues one
roster pass instead of two.

The evidence owns neither classification. Team assignment still resolves
organization ownership and roster status still resolves roster category, from
their own unchanged rules.

Properties that keep this safe:

- Run scoped. The evidence is created inside `run_daily_sync` and passed
  explicitly to each consumer. Nothing is cached across runs and nothing is
  persisted, so a run never reads another run's roster feeds.
- Fresh. Views are fetched during the run, on first ask. A view no consumer
  needs is never fetched, and a view the shared pass never read is fetched
  fresh rather than treated as an absent roster.
- Fail closed. A failed fetch is remembered as a failure, never as an empty
  roster, so every consumer of that view observes the same failure and neither
  invents authority from a partial fetch.
- Read only. Each read returns a copy, so one consumer cannot alter what the
  other observes.

## Normalization Rules

The sync persists these statuses when authority exists:

- `ACTIVE`
- `IL_15`
- `IL_60`
- `MINORS`
- `OPTIONED`
- `DFA`
- `NON_ROSTER`
- `40_MAN_ONLY`
- `UNKNOWN`

User-facing BaseballOS labels are:

- `Active MLB`
- `IL-15`
- `IL-60`
- `Minors`
- `40-Man Only`
- `Optioned`
- `DFA`
- `Non-Roster`
- `Roster Unknown`

Precedence:

1. Membership in the MLB `active` roster is `ACTIVE`.
2. Explicit MLB status text or code classifies IL, minors, optioned, DFA, and
   related inactive states.
3. Membership in `nonRosterInvitees` is `NON_ROSTER`.
4. Membership in `fullRoster` without active or 40-man membership is `MINORS`.
5. Membership in `40Man` without active status is `40_MAN_ONLY` unless explicit
   status says otherwise.
6. Missing or unclassifiable roster evidence persists as `UNKNOWN`.

## Database Persistence

The existing pitcher roster-status fields are used:

- `pitchers.roster_status`
- `pitchers.roster_status_source`
- `pitchers.roster_status_updated_at`

`roster_status_source` identifies the MLB roster view that supplied the status,
for example:

```text
mlb_stats_api:roster_sync:active
mlb_stats_api:roster_sync:40Man
mlb_stats_api:roster_sync:fullRoster
mlb_stats_api:roster_sync:nonRosterInvitees
mlb_stats_api:roster_sync:unavailable
```

## Trust Behavior

If roster status is known, the board uses it.

If roster status is unknown, BaseballOS keeps the existing fail-closed trust
behavior:

- Status remains `Roster Unknown`.
- The board surfaces the roster-status limitation.
- Unknown is not promoted to active MLB.
- Availability and workload freshness remain separate from roster authority.

## Bullpen Behavior

Default bullpen boards exclude known inactive roster statuses:

- IL statuses
- Minors
- Optioned
- DFA
- Non-roster
- 40-Man Only

The unavailable-pitchers toggle can surface those pitchers for roster awareness,
but their cards remain labelled by roster status and are forced to
`Unavailable` for active planning availability.

Player Detail uses the same final availability semantics as Bullpen Board cards.
The detail view keeps the workload signal visible separately, but final
availability is roster-status-adjusted.

## Validation Fixtures

The Reds examples are covered as regression fixtures only, not hardcoded
implementation rules:

- Graham Ashcraft
- Pierce Johnson
- Emilio Pagan
- Hunter Greene
- Connor Phillips
- Jose Franco
- Chase Burns
- Rhett Lowder
- Brandon Williamson
- Andrew Abbott
- Nick Lodolo
- Brady Singer

The same sync and filtering logic applies league-wide.

## Remaining Limitations

- The MLB roster endpoint can omit detailed status text for some 40-man players;
  BaseballOS classifies those rows as `40_MAN_ONLY` rather than active.
- `fullRoster` membership without active or 40-man membership is treated as
  minors because no stronger active MLB evidence exists.
- Transaction feeds are not yet consumed. They remain a future enhancement for
  explaining why a status changed between roster snapshots.
- Real-world roster changes can occur between syncs before BaseballOS refreshes.
- Bullpen eligibility still uses role and usage evidence where explicit bullpen
  role labels are unavailable.

## Future Enhancements

- Add transaction-feed ingestion for status-change provenance.
- Add roster-status freshness metadata to the sync status endpoint.
- Add a roster-status-only admin refresh endpoint if operational workflows need
  it separate from workload sync.
