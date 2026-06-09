# Freshness Persistence & Deployment Correctness

## TL;DR

The freshness **code is already correct and durable-authoritative.** A code
deploy that wipes the local cache file does **not** override healthy durable
sync metadata. When the banner reverts to a snapshot/stale state after a deploy,
the root cause is **operational** — durable sync metadata is not persisting (or
was never written) — not a code bug. This change adds proof tests and a
deployment checklist; no behavioral code change was made.

## Freshness chain (audited)

```
GitHub Actions (cron)  ──POST /api/bullpen/sync──┐
APScheduler run_daily_sync ──────────────────────┤  both call
                                                  ├─ sync_metadata.start_sync_run()
                                                  └─ sync_metadata.finish_sync_run()
                                                        → writes durable sync_runs row  (AUTHORITATIVE)
                                                        → also writes backend/logs/sync_status.json (cache only)

GET /api/bullpen/sync/status ─┐
GET /api/bullpen/dashboard  ──┴─ both call sync_metadata.build_sync_status_payload(legacy_status=read_status())
                                   → durable sync_runs first
                                   → cache file (sync_status.json) second
                                   → generated "never / metadata_unavailable" fallback last

Frontend SeasonBanner  ← Dashboard derives isLive from the same freshness block
                          (is_current AND sync_status ∈ {success, ok})
```

Both production sync entry points write durable rows; both read endpoints share
one builder. There is a single freshness decision, not several.

## Root cause

`build_sync_status_payload` resolves freshness in strict priority:

1. **Durable `sync_runs`** (`latest_sync_run()` / `latest_successful_sync_run()`).
2. **Cache file** `backend/logs/sync_status.json` (only if no durable row).
3. **Generated fallback** (`never` / `metadata_unavailable`).

`backend/logs/` is **gitignored and ephemeral**, so the cache file disappears on
every deploy/restart. That is harmless *as long as durable `sync_runs` survives*
— the cache is never consulted while a durable row exists.

The post-deploy "snapshot/stale" regression therefore only happens when the
durable layer is unavailable, which has three operational causes:

1. **The `sync_runs` migration is not applied in production.** Then
   `latest_sync_run()` raises and is caught as "no durable metadata," dropping
   to the (now-missing) cache file → snapshot.
2. **The database is not persistent across deploys** (e.g. an ephemeral disk or
   a reset/free-tier instance) — `sync_runs` *and* `game_logs` vanish, so even a
   fresh sync history is lost on redeploy.
3. **No sync is actually running in prod** (missing `BASEBALLOS_SYNC_URL` /
   `BASEBALLOS_ADMIN_API_TOKEN` Actions secrets, or `ADMIN_API_TOKEN` mismatch),
   so no durable rows are ever written and freshness rests entirely on the
   ephemeral cache file.

In all three, the **code did the right thing** (durable-first); the durable
store simply had nothing to offer.

## Authoritative source & fallback order

- **Authoritative:** the `sync_runs` table (durable production storage).
- **Cache only:** `backend/logs/sync_status.json` — used solely when no durable
  row exists; it can never override a healthier durable row.
- **Last resort:** generated `never` / `metadata_unavailable` labels, used only
  when neither durable nor cache data exists.

The `<year> End-of-Season Snapshot` banner label is derived from
`freshness.is_current` (latest **game date** vs the 14-day window) and
`sync_status`. It is honest historical-snapshot wording for old game data — it
is *not* a deploy artifact. Healthy, recent durable data renders "Live".

## Deployment behavior after this work (proven by tests)

| Scenario | Durable | Cache file | Result |
| --- | --- | --- | --- |
| A | healthy success | **missing** | current/healthy on `/sync/status` **and** `/dashboard`; no snapshot |
| B | healthy success | stale / `never` / failed | **durable wins**; stays current |
| C | none | none | honest `never` fallback, `is_current=false`, no crash |
| D | latest run **failed** (earlier success exists) | — | reports `failed`, preserves `last_successful_sync`, surfaces the failure (not hidden behind snapshot) |

Plus: `/dashboard` and `/sync/status` agree on `is_current`, `sync_status`,
`data_through`, and `last_successful_sync`; and **no endpoint reports a snapshot
while durable-healthy metadata exists.**

## Tests added

- `backend/tests/test_freshness_deploy_correctness.py` — Scenarios A–D, shared
  freshness source across endpoints, and the no-snapshot-when-durable-healthy
  invariant (8 tests).
- `frontend/tests/dashboardFreshnessBanner.test.mjs` — the SeasonBanner reflects
  authoritative freshness: healthy → "Live", non-current → snapshot label, and a
  failed durable sync is never painted "Live" (3 tests).

No source files were modified — the existing logic already satisfies the
requirements; these lock the behavior in.

## Operational checklist (production)

The freshness banner reverting after deploy is fixed by ensuring durable metadata
persists. Confirm, in order:

1. **Apply the `sync_runs` migration** on the production database
   (`41f4f9a8d6c2_add_sync_runs`). Without the table, durable reads fail and the
   system silently falls back to the ephemeral cache.
   - Verify: `SELECT count(*) FROM sync_runs;` succeeds.
2. **Confirm the database is persistent** across deploys (managed Postgres on
   Render, not an ephemeral disk / not reset on redeploy). `sync_runs` and
   `game_logs` rows must survive a redeploy.
3. **Confirm the GitHub Actions sync is configured and succeeding:** repository
   secrets `BASEBALLOS_SYNC_URL` and `BASEBALLOS_ADMIN_API_TOKEN` are set, the
   token matches the backend `ADMIN_API_TOKEN`, and recent runs are green (the
   `Daily Bullpen Sync` workflow POSTs the durable `/api/bullpen/sync`).
4. **Confirm sync auth env vars** on the backend (`ADMIN_API_TOKEN`) so the
   protected sync endpoint actually writes durable rows.
5. **Verify after a sync:** `GET /api/bullpen/sync/status` returns
   `status: "success"`, a non-null `last_successful_sync`, and
   `freshness.is_current: true` — and stays that way across a redeploy.

If all five hold, a deploy cannot make healthy data appear stale.

## Remaining risks / requirements

- `backend/logs/sync_status.json` remains a cache only. It is fine for it to be
  absent; it must never be treated as the source of truth (it isn't).
- The hero banner is a coarse **Live vs Snapshot** indicator driven by
  `is_current` + `sync_status`. A *failed* latest sync renders as non-Live
  (snapshot styling) on the hero; the precise failed/degraded state is shown on
  the **Data & Trust** sync pill. If a distinct "degraded/failed" hero state is
  desired later, that is a UI enhancement, not a freshness-correctness fix.
- The data set is a tracked sample; `is_current` correctly reflects game-date
  recency. Genuinely old game data will read as a historical snapshot by design.
