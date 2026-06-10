# Durable Sync Write Integration Fix

## Symptom

Production had the `sync_runs` table created, Alembic at `41f4f9a8d6c2`, and a
successful manual sync — yet:

```json
"source": "legacy_status_file",
"id": null
```

```sql
SELECT COUNT(*) FROM sync_runs;  -- 0
```

The sync wrote the legacy cache file but **no durable row**.

## Root cause

Both real sync paths (`POST /api/bullpen/sync` and the APScheduler
`run_daily_sync`) already call `start_sync_run()` then `finish_sync_run()`. The
defect was in how failures were handled, not whether the calls existed:

1. **`start_sync_run()` swallowed errors and returned `None`.** Any failure of
   the start insert (e.g. a poisoned/aborted transaction earlier in the request —
   the classic Postgres *"current transaction is aborted, commands ignored until
   end of transaction block"*) was caught, logged only at `warning`, and turned
   into `None`.
2. **`finish_sync_run(None, …)` was a no-op.** When the start id was `None`, the
   finish call returned immediately and wrote nothing — so the sync produced
   **zero** durable rows.
3. The failure was **invisible**: the sync still wrote `sync_status.json` and
   otherwise "succeeded," so `/api/bullpen/sync/status` permanently fell back to
   the legacy file (`source: legacy_status_file`, `id: null`).

In short: a single hiccup on the start insert meant the durable table was never
written, and nothing surfaced the problem.

## Fix

Durable writes are now robust, self-healing, observable, and never gated by the
cache file. No routes, UX, recommendation logic, or bullpen calculations changed.

- **`start_sync_run()`** (`services/sync_metadata.py`): rolls back any poisoned
  transaction *before* the insert (fixes the aborted-transaction trap), and logs
  a failure at `error` instead of `warning`.
- **`finish_sync_run()`** is now **self-healing**: if the start id is missing or
  the row can't be found, it **creates** the durable row with the final status
  (it also accepts `source` / `started_at` for that case). This guarantees that
  every completed or failed sync leaves at least one durable row, even if the
  start insert hiccuped.
- **`POST /api/bullpen/sync`** (`api/bullpen.py`): passes `source`/`started_at`
  into both finish calls and returns the **persisted** row id plus
  `sync_run_persisted: bool`. The durable write happens before the best-effort
  cache write.
- **`run_daily_sync`** (`services/sync.py`): passes `source`/`started_at` into
  both finish calls (self-heal context).
- **`write_status()`** (`services/sync.py`): the directory create + file write
  are both inside the guard, so a read-only filesystem can never raise into — or
  precede — the durable write. The cache file is never the only write path.
- **`build_sync_status_payload()`**: adds an explicit, unambiguous
  `metadata_source` field — `"sync_runs"` (durable), `"legacy_status_file"`
  (cache), or `"none"` — so the active source is observable directly.

### Fallback order (unchanged, now guaranteed to be reachable)

1. Durable `sync_runs` (authoritative).
2. `sync_status.json` cache (only when no durable row exists).
3. Generated `never` / `metadata_unavailable` fallback.

## Tests

`backend/tests/test_durable_sync_write_integration.py` (MLB pull + fatigue
recompute mocked; in-memory SQLite):

1. Manual sync endpoint writes a `sync_runs` row (`sync_run_persisted: true`,
   non-null id).
2. Successful sync populates status, started_at, completed_at, latest_game_date,
   latest_workload_date, latest_fatigue_calculated_at, records_processed,
   new_logs_added, pitchers_updated, errors.
3. Failed sync still writes a durable failed row (status + error_message +
   completed_at).
4. **Self-heal:** with `start_sync_run` forced to return `None` (the exact prod
   symptom), a durable row is still written and `/sync/status` reports
   `metadata_source: "sync_runs"`, non-null `sync.id`.
5. Cache-file write failure does not prevent the durable row.
6. `/sync/status` prefers `sync_runs` over a conflicting legacy file.
7. No regression to dashboard freshness after a sync.

Backend: 478 passed. Frontend: 191 passed (unchanged — backend-only fix).

## Production verification plan

After deploying and running one sync (manual `POST /api/bullpen/sync`, or the
GitHub Actions "Daily Bullpen Sync" workflow):

```sql
SELECT COUNT(*) FROM sync_runs;            -- expect >= 1

SELECT id, status, started_at, completed_at, source,
       latest_game_date, latest_workload_date, error_message
FROM sync_runs
ORDER BY started_at DESC
LIMIT 5;                                   -- expect the latest sync as a row
```

Endpoint:

```text
GET /api/bullpen/sync/status
```

Expect:

```json
"metadata_source": "sync_runs",
"sync": { "id": <non-null>, "source": "github_actions" | "manual" | "scheduled" }
```

(`metadata_source: "sync_runs"` with a non-null `sync.id` is the post-fix signal
— it replaces the previous `source: "legacy_status_file"`, `id: null`.)

The `POST /api/bullpen/sync` response also now returns `sync_run_persisted: true`
and a non-null `sync_run_id` on success.

## Remaining risks / operational notes

- The fix guarantees a durable row whenever a sync **reaches** `finish_sync_run`.
  A hard process crash between start and finish (when start also failed to
  persist) could still leave no row — an extreme edge, not the observed symptom.
- If durable writes still fail in production after this, the cause is now **loud**
  (`logger.error('Could not persist sync … metadata: …')`) — check the backend
  logs; it indicates a real DB/connection problem (permissions, search_path, or
  connectivity), not a silent code fallback.
- The database must remain persistent across deploys; an ephemeral/reset DB would
  wipe `sync_runs` regardless of this fix.
- The legacy `sync_status.json` is intentionally retained as a cache and was not
  removed.
