# GitHub Actions Freshness Audit

Audit date: 2026-06-02 UTC

## Workflow Reviewed

Workflow file: `.github/workflows/baseballos-sync.yml`

The workflow runs daily at `0 10 * * *` UTC and can also be triggered manually
with `workflow_dispatch`. It calls the protected backend sync endpoint with:

- `BASEBALLOS_SYNC_URL`
- `BASEBALLOS_ADMIN_API_TOKEN`
- `POST {"days_back": 7}`
- `X-Admin-Token`

## Latest Successful Run

Public GitHub Actions API evidence:

| Field | Value |
| --- | --- |
| Workflow | Daily Bullpen Sync |
| Run ID | 26765763862 |
| Event | workflow_dispatch |
| Branch | main |
| Run status | completed |
| Run conclusion | success |
| Run created at | 2026-06-01T15:49:18Z |
| Job started at | 2026-06-01T21:39:12Z |
| Job completed at | 2026-06-01T21:39:56Z |
| Trigger step conclusion | success |
| Run URL | https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/26765763862 |

Public workflow logs were not available without GitHub authentication. The job
metadata confirms that the protected sync trigger step completed successfully.

## Backend Corroboration

The public fatigue API reports rows calculated during the same window:

| Field | Value |
| --- | --- |
| Latest fatigue `calculated_at` sampled | 2026-06-01T21:39:55.153933 |
| Latest game date in fatigue metadata | 2026-05-31 |
| Total scored pitchers | 679 |
| Total game logs | 35,768 |

This strongly corroborates that the June 1 workflow reached the backend and
updated database-backed workload/fatigue data.

## Metadata Written After Sync

The backend code writes sync status after both manual and scheduled sync paths:

- `api/bullpen.py` -> `sync_recent_logs()` writes status after `POST /sync`
- `services/sync.py` -> `run_daily_sync()` writes status after scheduled sync
- both use `services.sync.write_status()`

However, the dashboard-readable public endpoint currently reports:

```json
{
  "last_sync": null,
  "status": "never",
  "message": "No sync has run yet.",
  "data": {
    "game_logs": 35768,
    "latest_game_date": "2026-05-31"
  }
}
```

## Audit Conclusion

The latest GitHub Actions sync succeeded on June 1, 2026. Database-backed
workload data reflects that run, but dashboard-readable sync metadata is not
present in the public `/sync/status` response.
