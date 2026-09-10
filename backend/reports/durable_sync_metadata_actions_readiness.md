# Durable Sync Metadata GitHub Actions Readiness

## Scope

This audit reviews the scheduled sync workflow and its interaction with durable
sync metadata.

Workflow reviewed:

```text
.github/workflows/baseballos-sync.yml
```

## Workflow Summary

The workflow:

- Runs daily at `0 10 * * *`.
- Allows manual `workflow_dispatch`.
- Uses a concurrency group named `baseballos-sync`.
- Posts to `BASEBALLOS_SYNC_URL`.
- Authenticates with `BASEBALLOS_ADMIN_API_TOKEN`.
- Sends:

```json
{"days_back": 7, "source": "github_actions"}
```

## Compatibility Findings

| Check | Finding |
| --- | --- |
| Protected endpoint | The workflow still calls the existing protected sync endpoint. |
| Secret requirements | Required secrets remain documented in the workflow comments. |
| Source attribution | The request now identifies the source as `github_actions`, which the backend stores in `sync_runs.source`. |
| Retry behavior | Existing `curl --retry 2 --max-time 600` behavior is preserved. |
| Failure visibility | Non-2xx responses still fail the workflow. |
| Migration responsibility | The workflow does not run database migrations. Deployment must apply migrations separately. |

## Backend Interaction

The sync endpoint records:

- sync start
- successful completion
- failed completion
- latest game date
- latest workload date
- latest fatigue calculation timestamp
- processed/update counts

Failed sync attempts are recorded without hiding the previous successful sync.
`/api/bullpen/sync/status` exposes both the latest attempt and
`last_successful_sync`.

## Deployment Requirement

The first scheduled or manual workflow run after deploy should happen after the
database migration has been applied. If the workflow runs before migration,
sync data may still process, but durable run metadata may be unavailable and a
backend warning should be expected.

## Recommended Post-Deploy Check

Run the workflow manually after deployment and verify:

```text
GET /api/bullpen/sync/status
```

Expected fields:

```text
status: success
last_sync: non-null
last_successful_sync: non-null
sync.source: github_actions
data.latest_game_date: non-null when game logs exist
data.latest_workload_date: non-null when workload data exists
```

## Readiness Verdict

```text
PASS_WITH_OPERATIONAL_ACTION
```

Required action:

```text
Run migrations before the first post-deploy scheduled or manual sync.
```
