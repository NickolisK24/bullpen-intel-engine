# Dashboard Freshness Label Audit

Audit date: 2026-06-02 UTC

## Components Reviewed

- `frontend/src/components/dashboard/SyncStatus.jsx`
- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/src/utils/api.js`

## Sync Pill Logic

`SyncStatus.jsx` renders four states:

| Condition | Label |
| --- | --- |
| `status === "error"` | `Last sync failed` |
| `last_sync` exists | `Last synced: <formatted timestamp>` |
| no `last_sync`, `data.game_logs > 0`, and `data.latest_game_date` exists | `Snapshot · through <latest_game_date>` |
| no sync and no data | `No data loaded` |

## Risk Distribution Through Label

`Dashboard.jsx` also appends:

```jsx
through {fmtThroughDate(sync.data.data.latest_game_date)}
```

when `sync.data.data.latest_game_date` exists. This is a baseball data-through
date, not a sync timestamp.

## What "Snapshot through May 31, 2026" Represents

It represents option B:

**Baseball data snapshot date.**

It does not represent the June 1 sync timestamp. The date comes from
`/api/bullpen/sync/status` -> `data.latest_game_date`, which is computed from
`max(GameLog.game_date)` in the database.

## Why It Appears Now

The public `/sync/status` endpoint currently reports:

- `last_sync: null`
- `status: never`
- `data.latest_game_date: 2026-05-31`
- `data.game_logs: 35768`

Because `last_sync` is absent but data exists, `SyncStatus.jsx` correctly
selects the historical snapshot branch.

## UI Label Audit Conclusion

The UI is rendering according to its current contract. The label is not showing
snapshot metadata from `/fatigue/snapshot`; it is showing the database latest
game date from `/sync/status`. The trust issue is that the missing sync
timestamp makes recently synced data look like a historical seeded snapshot.
