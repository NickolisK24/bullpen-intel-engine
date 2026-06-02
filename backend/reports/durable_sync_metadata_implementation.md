# Durable Sync Metadata Implementation

## Root Cause

The public backend had valid workload data through May 31, 2026 and fatigue
rows calculated during the successful June 1 sync window, but
`/api/bullpen/sync/status` reported:

```json
{
  "last_sync": null,
  "status": "never"
}
```

The sync timestamp was stored only in `backend/logs/sync_status.json`, which is
runtime-local state. It can disappear across restarts and deployments, while
database-backed game logs and fatigue scores remain current.

## Implementation Summary

- Added a database-backed `sync_runs` model/table for durable sync metadata.
- Added `services/sync_metadata.py` to record sync start, completion, failure,
  and data/fatigue coverage metadata.
- Updated manual sync and scheduled sync paths to write durable metadata.
- Updated the GitHub Actions sync body to identify its source as
  `github_actions`.
- Updated `/api/bullpen/sync/status` to prefer durable metadata while preserving
  legacy fields.
- Updated the dashboard sync pill to separately display sync timestamp and data
  coverage.
- Added backend and frontend regression tests for successful, failed, missing,
  and no-data metadata states.

## Persistence Design

Migration:

```text
backend/migrations/versions/41f4f9a8d6c2_add_sync_runs.py
```

Table:

```text
sync_runs
```

Fields:

| Field | Purpose |
| --- | --- |
| `id` | Primary key |
| `started_at` | Sync attempt start timestamp |
| `completed_at` | Sync attempt completion timestamp |
| `status` | `running`, `success`, or `failed` |
| `source` | Sync source such as `manual` or `scheduled` |
| `latest_game_date` | Latest baseball game-log date after sync |
| `latest_workload_date` | Latest workload date after sync |
| `latest_fatigue_calculated_at` | Latest fatigue score calculation timestamp after sync |
| `records_processed` | Records processed by the sync run |
| `new_logs_added` | New game logs inserted |
| `pitchers_updated` | Pitchers with recalculated fatigue scores |
| `errors` | Error count for the run |
| `error_message` | Failure or limitation text |
| `created_at` | Row creation timestamp |

Indexes:

- `ix_sync_runs_started_at`
- `ix_sync_runs_status_completed`

## API Shape

`GET /api/bullpen/sync/status` now returns durable metadata:

```json
{
  "status": "success",
  "last_sync": "2026-06-01T21:39:12",
  "last_successful_sync": "2026-06-01T21:39:56",
  "pitchers_updated": 428,
  "new_logs_added": 120,
  "errors": 0,
  "message": "",
  "finished_at": "2026-06-01T21:39:56",
  "data": {
    "game_logs": 35768,
    "latest_game_date": "2026-05-31",
    "latest_workload_date": "2026-05-31",
    "latest_fatigue_calculated_at": "2026-06-01T21:39:55"
  },
  "freshness": {
    "is_current": true,
    "label": "Current baseball data through 2026-05-31.",
    "limitations": []
  },
  "sync": {
    "id": 1,
    "status": "success",
    "source": "github_actions"
  }
}
```

Backward-compatible fields retained:

- `status`
- `last_sync`
- `pitchers_updated`
- `new_logs_added`
- `errors`
- `message`
- `finished_at`
- `data.latest_game_date`
- `data.game_logs`

## UI Behavior

When sync metadata and data coverage are both available, the dashboard shows:

```text
Synced: June 1, 2026
Data Through: May 31, 2026
```

When game logs exist but sync metadata is unavailable:

```text
Sync metadata: Unavailable
Data Through: May 31, 2026
```

When the latest sync attempt failed:

```text
Last sync failed: June 2, 2026
Data Through: May 31, 2026
```

When no metadata or game logs exist:

```text
No data loaded
```

## Fallback Behavior

- Durable `sync_runs` metadata is authoritative when available.
- Legacy `backend/logs/sync_status.json` remains a fallback for existing local
  deployments and backward-compatible fields.
- If durable metadata is temporarily unavailable, `/sync/status` still reports
  data coverage from game logs and adds a freshness limitation instead of
  implying that baseball data is missing.

## Tests Run

- `python -m pytest tests\test_sync_status.py`
- `python -m compileall api services models tests`
- `python -m pytest`
- `python -m compileall api services scripts models migrations tests`
- `npm test`
- `npm run build`
- `git diff --check`

Full backend and frontend validation were run before commit.

## Remaining Limitations

- Existing deployments will not have durable sync metadata until the migration
  is applied and a new sync run completes.
- Historical sync timestamps cannot be reconstructed perfectly from game logs;
  if no durable run exists, the API reports sync metadata as unavailable.
- `latest_workload_date` currently matches the latest MLB game-log date because
  workload V1 derives from game logs.
