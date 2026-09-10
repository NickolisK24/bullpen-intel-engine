# Durable Sync Metadata Deployment Runbook

## Purpose

This runbook defines the operational steps for deploying durable sync metadata
without losing freshness transparency on the dashboard.

## Pre-Deployment Checks

Run the validation suite:

```powershell
cd backend
$env:TMP="$PWD\.tmp"; $env:TEMP="$PWD\.tmp"
python -m pytest
python -m compileall api services scripts models migrations tests

cd ..\frontend
npm test
npm run build

cd ..
git diff --check
```

Review the worktree before staging:

```powershell
git status --short
```

Do not stage unrelated dependency artifacts such as `frontend/node_modules` or
unrelated lockfile drift.

## Deployment Steps

1. Deploy the durable sync metadata code.
2. Apply the Alembic migration to head using the deployment platform's database
   migration command.
3. Confirm the `sync_runs` table exists.
4. Trigger a manual sync through GitHub Actions or the protected admin sync
   endpoint.
5. Verify `/api/bullpen/sync/status`.
6. Verify the dashboard displays both sync timestamp and data coverage when both
   are available.

## Expected API Verification

Request:

```text
GET /api/bullpen/sync/status
```

Expected successful shape:

```json
{
  "status": "success",
  "last_sync": "2026-06-01T21:39:12",
  "last_successful_sync": "2026-06-01T21:39:56",
  "data": {
    "latest_game_date": "2026-05-31",
    "latest_workload_date": "2026-05-31",
    "latest_fatigue_calculated_at": "2026-06-01T21:39:55"
  },
  "freshness": {
    "is_current": true,
    "limitations": []
  },
  "sync": {
    "source": "github_actions"
  }
}
```

## Expected Dashboard Verification

When both sync and data coverage are available:

```text
Synced: June 1, 2026
Data Through: May 31, 2026
```

When data exists but sync metadata is unavailable:

```text
Sync metadata: Unavailable
Data Through: May 31, 2026
```

When the latest sync attempt fails:

```text
Last sync failed: June 2, 2026
Data Through: May 31, 2026
```

## Rollback Notes

If the code deployment is rolled back before the migration is rolled back:

- The unused `sync_runs` table can remain in place temporarily.
- Existing game logs and fatigue scores are unaffected.
- Legacy status-file behavior remains available to older code.

If the migration must be rolled back:

- Only `sync_runs` metadata history is removed.
- Baseball workload and fatigue data are not removed by this migration.

## Monitoring Notes

Monitor backend logs for durable metadata warnings:

```text
Could not read durable sync metadata
Could not start durable sync metadata run
Could not finish durable sync metadata run
```

Warnings immediately before migration may be expected. Warnings after migration
and after a successful sync should be investigated.

## Deployment Decision

Proceed only after the migration command and post-deploy sync verification are
explicitly assigned to the deployment checklist.
