# Durable Sync Metadata Migration Readiness

## Scope

This audit reviews the deployment readiness of the durable sync metadata
migration introduced by the durable sync metadata feature.

Migration reviewed:

```text
backend/migrations/versions/41f4f9a8d6c2_add_sync_runs.py
```

## Migration Summary

The migration adds one new table:

```text
sync_runs
```

Columns:

| Column | Nullable | Purpose |
| --- | --- | --- |
| `id` | no | Primary key |
| `started_at` | no | Sync attempt start timestamp |
| `completed_at` | yes | Completion timestamp for completed attempts |
| `status` | no | `running`, `success`, or `failed` |
| `source` | no | Sync source such as `manual`, `scheduled`, or `github_actions` |
| `latest_game_date` | yes | Latest MLB game-log date after the sync attempt |
| `latest_workload_date` | yes | Latest workload date after the sync attempt |
| `latest_fatigue_calculated_at` | yes | Latest fatigue calculation timestamp after the sync attempt |
| `records_processed` | yes | Records processed by the sync run |
| `new_logs_added` | yes | New game logs inserted |
| `pitchers_updated` | yes | Pitchers with recalculated fatigue scores |
| `errors` | yes | Error count |
| `error_message` | yes | Failure or limitation detail |
| `created_at` | no | Row creation timestamp |

Indexes:

```text
ix_sync_runs_started_at
ix_sync_runs_status_completed
```

## Safety Findings

| Check | Finding |
| --- | --- |
| Existing table mutation | No existing tables are altered. |
| Existing data mutation | No existing rows are updated or deleted. |
| Nullable fields | Metadata fields are nullable, which supports running, failed, and pre-data sync states. |
| Required fields | `started_at`, `status`, `source`, and `created_at` are required, which keeps run records traceable. |
| Indexes | Indexes support latest-run and latest-successful-run lookup patterns. |
| Downgrade behavior | Downgrade drops only the new indexes and `sync_runs` table. Existing workload data is not affected. |

## Rollout Requirements

The migration must be applied before expecting durable sync metadata to be
authoritative in production.

Expected deployment sequence:

1. Deploy code containing the model, service, API, and dashboard fallback logic.
2. Run the database migration to head.
3. Trigger or wait for the next sync.
4. Verify `/api/bullpen/sync/status` reports a non-null `last_successful_sync`.

## Risk Assessment

The migration is low risk because it is additive and isolated to a new table.
The main deployment risk is operational: if the migration is not applied, the
application will fall back to legacy metadata and data coverage, but durable sync
history will not be available until the table exists.

## Readiness Verdict

```text
PASS_WITH_OPERATIONAL_ACTION
```

Required action:

```text
Run the migration before relying on durable sync metadata in production.
```
