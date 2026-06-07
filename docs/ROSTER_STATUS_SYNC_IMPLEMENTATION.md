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
MLB team roster endpoints
    -> roster evidence merge by MLB player id
    -> roster status normalization
    -> pitchers.roster_status persistence
    -> board roster-status classification
    -> bullpen filtering and UI trust labels
```

Roster sync runs in three places:

- Manual `POST /api/bullpen/sync`
- Scheduled `run_daily_sync`
- The database seeder after pitcher rows are loaded

## Normalization Rules

The sync persists these statuses when authority exists:

- `ACTIVE`
- `IL_10`
- `IL_15`
- `IL_60`
- `MINORS`
- `OPTIONED`
- `DFA`
- `NON_ROSTER`
- `40_MAN_ONLY`

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
- 40-man-only context

The inactive/context toggle can surface those pitchers as context, but their
cards remain labelled by roster status and are forced to `Unavailable` for active
planning availability.

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
- Existing local rows only receive status after seed or sync runs.
- Transaction feeds are not yet consumed. They remain a future enhancement for
  explaining why a status changed between roster snapshots.

## Future Enhancements

- Add transaction-feed ingestion for status-change provenance.
- Add roster-status freshness metadata to the sync status endpoint.
- Add a roster-status-only admin refresh endpoint if operational workflows need
  it separate from workload sync.
