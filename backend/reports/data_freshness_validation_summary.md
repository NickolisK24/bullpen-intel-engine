# Data Freshness Validation Summary

Audit date: 2026-06-02 UTC

## Executive Summary

The dashboard label "Snapshot through May 31, 2026" is not evidence of data
freshness regression. It reflects the latest baseball game-log date available
to the dashboard. The public backend has data through May 31, 2026 and fatigue
scores calculated during the successful June 1, 2026 sync window.

The issue is that dashboard-readable sync metadata is missing. The public
`/api/bullpen/sync/status` endpoint reports `last_sync: null` and
`status: never`, so the UI falls back to the snapshot label even though the
database contains recently synced workload data.

## Latest Successful Sync

| Source | Value |
| --- | --- |
| GitHub Actions run | 26765763862 |
| Workflow conclusion | success |
| Job completed at | 2026-06-01T21:39:56Z |
| Public fatigue max `calculated_at` | 2026-06-01T21:39:55.153933 |

## Latest Data Snapshot

| Source | Value |
| --- | --- |
| Public `/sync/status.data.latest_game_date` | 2026-05-31 |
| Public `/fatigue.meta.latest_game_date` | 2026-05-31 |
| Public game-log count | 35,768 |

## Latest Workload Date

| Source | Value |
| --- | --- |
| Public fatigue availability inputs | 2026-05-31 |
| Current freshness cutoff | 2026-05-19 |
| Fresh classifications | 428 |
| Stale classifications | 251 |

## Root Cause

`/api/bullpen/sync/status` depends on `backend/logs/sync_status.json` for
`last_sync`. That file is runtime-only and ignored by git. In the public
environment, the status file is missing or unreadable, so `read_status()`
returns the `never` sentinel even though the database has updated game logs and
fatigue scores from the June 1 sync.

## Regression Status

| Area | Status |
| --- | --- |
| Workload data | No regression found |
| GitHub Actions sync | Latest run succeeded |
| API sync metadata | Inconsistent/missing |
| Dashboard label | Correct fallback, ambiguous in this state |
| Snapshot-mode leakage | Not found |

## Recommended Action

Persist sync metadata in durable storage and update the dashboard to display
sync timestamp and data-through date as separate trust signals:

```text
Synced: June 1, 2026
Data Through: May 31, 2026
```

When sync metadata is missing:

```text
Synced: Unavailable
Data Through: May 31, 2026
```

## Final Classification

`METADATA_ISSUE`
