# Data Freshness Source Trace

Audit date: 2026-06-02 UTC

## Purpose

Trace dashboard freshness values from source to UI and distinguish sync
timestamps from baseball data snapshot dates.

## Freshness Values

| Value | Source of truth | Backend path | API field | UI consumer |
| --- | --- | --- | --- | --- |
| Sync timestamp | Runtime status file written after sync | `backend/logs/sync_status.json` via `services.sync.write_status()` | `/api/bullpen/sync/status` -> `last_sync` | `frontend/src/components/dashboard/SyncStatus.jsx` |
| Sync status | Runtime status file written after sync | `services.sync.read_status()` | `/api/bullpen/sync/status` -> `status` | `SyncStatus.jsx` |
| Snapshot date | Latest game-log date represented by snapshot-mode records | `services.availability_snapshot.availability_mode_metadata()` | `/api/bullpen/fatigue/snapshot` -> `meta.snapshot_date` | Admin/validation only |
| Latest game date | Database max game-log date | `db.func.max(GameLog.game_date)` in `api/bullpen.py` | `/api/bullpen/sync/status` -> `data.latest_game_date`; `/api/bullpen/fatigue` -> `meta.latest_game_date` | `SyncStatus.jsx`; `Dashboard.jsx`; bullpen empty-state metadata |
| Latest workload date | Per-pitcher max game-log date | `services.availability_snapshot.latest_game_date_for()` and availability inputs | `availability.inputs.latest_game_date` | Bullpen availability detail and explanations |
| Latest fatigue calculation | Fatigue score row timestamp | `FatigueScore.calculated_at` | Fatigue row `calculated_at` | Not directly used by dashboard freshness label |

## Source Details

- `POST /api/bullpen/sync` and `services.sync.run_daily_sync()` write sync status
  with `last_sync`, `finished_at`, `status`, `pitchers_updated`,
  `new_logs_added`, and `errors`.
- `GET /api/bullpen/sync/status` reads that runtime status and enriches it with
  database-derived `data.game_logs` and `data.latest_game_date`.
- If the runtime status file is absent, `services.sync.read_status()` returns
  `last_sync: null`, `status: never`, and `message: No sync has run yet.`
- `backend/logs/` is ignored by git, so `sync_status.json` is runtime state,
  not a repository artifact.

## Current Evidence

| Environment | Sync timestamp | Status | Latest game date | Game logs | Latest fatigue calculation |
| --- | --- | --- | --- | --- | --- |
| Local checkout | 2026-05-02T04:50:13.539462 | ok | 2026-05-01 | 32,881 | 2026-06-01T20:49:02.095927 |
| Public API | null | never | 2026-05-31 | 35,768 | 2026-06-01T21:39:55.153933 |

## Trace Conclusion

The dashboard "Snapshot through May 31, 2026" label comes from
`data.latest_game_date`, not from a sync timestamp. The latest public data is
available through May 31, while the public sync timestamp is missing from
`/api/bullpen/sync/status`.
