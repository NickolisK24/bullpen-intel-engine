# Durable Sync Metadata Boot Safety

## Scope

This audit verifies that the backend can boot and serve freshness metadata during
the transition from legacy runtime metadata to durable database metadata.

## States Reviewed

| State | Expected Behavior | Result |
| --- | --- | --- |
| `sync_runs` table exists | Read durable latest run and latest successful run. | Covered by backend tests. |
| `sync_runs` table missing | Catch durable metadata read errors and fall back to legacy status plus data coverage. | Verified locally. |
| Legacy `sync_status.json` exists | Preserve backward-compatible sync fields. | Verified locally. |
| No sync metadata exists | Return a clear no-data or metadata-unavailable state instead of crashing. | Covered by backend and frontend tests. |

## Local Pre-Migration Verification

A local `/api/bullpen/sync/status` request was executed against a database where
the durable `sync_runs` table had not yet been applied. The backend logged a
durable metadata read warning and still returned HTTP 200.

Representative response values:

```text
status: success
last_sync: 2026-05-02T04:50:13.539462
last_successful_sync: 2026-05-02T04:52:44.384894
data.latest_game_date: 2026-05-01
data.latest_workload_date: 2026-05-01
data.latest_fatigue_calculated_at: 2026-06-01T20:49:02.095927
```

This confirms that missing durable metadata does not block the dashboard status
endpoint from reporting available baseball data coverage.

## Code Paths Reviewed

| File | Boot-Safety Role |
| --- | --- |
| `backend/services/sync_metadata.py` | Catches durable metadata write/read failures and preserves fallback payloads. |
| `backend/api/bullpen.py` | Wraps `/sync/status` payload generation in a defensive error response path. |
| `backend/services/sync.py` | Records scheduled sync metadata without removing legacy status-file writes. |
| `backend/tests/test_sync_status.py` | Covers metadata unavailable, no data, success, failure, and persistence behavior. |

## Failure Mode Behavior

If the durable table is unavailable:

- `/api/bullpen/sync/status` should continue returning HTTP 200.
- Existing data coverage should still be exposed from game logs and fatigue rows.
- Freshness limitations should disclose that sync metadata is unavailable.
- Logs should contain a warning for the durable metadata read/write problem.

## Operational Monitoring

After deploy, monitor backend logs for:

```text
Could not read durable sync metadata
Could not start durable sync metadata run
Could not finish durable sync metadata run
```

These warnings are acceptable during a pre-migration transition, but should not
continue after the migration is applied and a sync has completed.

## Readiness Verdict

```text
PASS_WITH_MONITORING
```

No boot blocker was found.
