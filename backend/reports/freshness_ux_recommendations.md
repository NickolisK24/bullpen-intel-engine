# Freshness UX Recommendations

Audit date: 2026-06-02 UTC

## Problem

The current dashboard has to choose between:

- `Last synced: <timestamp>`
- `Snapshot · through <latest_game_date>`

When the sync timestamp is missing but data was actually synced, the dashboard
falls back to the snapshot label. That label is technically tied to the latest
game date, but it can imply that no live sync occurred.

## Recommendation

Separate sync metadata from baseball data coverage in the UI:

```text
Synced:
June 1, 2026 at 5:39 PM

Data Through:
May 31, 2026
```

If sync metadata is unavailable but game logs exist:

```text
Synced:
Unavailable

Data Through:
May 31, 2026

Sync metadata is missing; data coverage is shown from game logs.
```

## Backend Recommendation

Persist sync status in durable storage rather than relying only on
`backend/logs/sync_status.json`.

Suggested durable fields:

- `last_sync_started_at`
- `last_sync_finished_at`
- `last_successful_sync_at`
- `sync_status`
- `new_logs_added`
- `pitchers_updated`
- `errors`
- `latest_game_date_after_sync`
- `latest_fatigue_calculated_at_after_sync`

## Trust Rules

- Do not substitute data-through date for sync timestamp.
- Do not say "never synced" when fatigue rows were calculated after a known
  successful workflow run unless durable sync metadata also proves no sync.
- Keep "Data Through" tied to `max(GameLog.game_date)`.
- Keep "Synced" tied to explicit sync metadata.
- If sync metadata is missing, say it is missing.

## Implementation Scope

No UI changes were implemented in this branch. These recommendations should be
handled in a follow-up fix branch after review.
