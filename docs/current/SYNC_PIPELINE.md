# BaseballOS Sync Pipeline — Execution Order and Trust Gates

Last updated: 2026-07-11 (runtime governance and finality preflight).
Workflow: `.github/workflows/baseballos-sync.yml` · Incident background:
`docs/audits/sync-reliability-audit-2026-07-08.md` and
`docs/audits/appearance-ledger-restoration-2026-07-08.md`.

## The order, in one line

**schedule finality preflight → sync → publish/withhold → appearance ledger audit → dashboard cache verification**

The foundational rule: if we cannot prove the appearance ledger is complete,
we do not publish. The previous trusted snapshot keeps serving.

## Schedules and modes

| Trigger | When (UTC) | Mode |
|---|---|---|
| cron `0 10 * * *` | ~6 AM ET | daily |
| cron `0 2,4,6 * * *` | overnight passes | postgame |
| Run workflow → `mode: daily` / `postgame` | manual | same as above |
| Run workflow → `mode: backfill` + `backfill_date` | manual only | explicit historical replay |

Historical backfills are **never automatic**. The postgame job self-heals the
trailing `POSTGAME_LOOKBACK_DAYS` (default 2) slate dates as part of normal
operation; anything older requires an operator to dispatch `mode=backfill`
with a concrete `YYYY-MM-DD` slate date.

## public-sync job, step by step

1. **Sync (acquisition + derived state + snapshot build)**
   - daily: `run_daily_sync.py --days-back 7 --public-only` — team
     assignments, roster statuses, transactions, production schedule/finality
     preflight for the gameLog window, the per-pitcher gameLog lane
     (statusless splits resolved against `scheduled_games`; unresolvable
     finality is dead-lettered, never silently skipped), fatigue, then the
     snapshot build.
   - postgame: `run_postgame_refresh.py --public-only` — production
     schedule/finality preflight for stale non-final stored slates, then sweeps
     the primary slate plus the trailing lookback dates, ingests completed-game
     boxscores, fatigue, then the snapshot build.
   - backfill: `run_postgame_refresh.py --date <backfill_date>` — exactly one
     explicitly requested slate.
2. **Snapshot publish/withhold (inside the sync process)** —
   `publish_dashboard_snapshot` enforces, in order: sync-run provenance,
   slate coverage for the newest data date, and the **appearance ledger gate**
   (`services/appearance_ledger.py`, trailing
   `APPEARANCE_LEDGER_WINDOW_DAYS` = 10 days). Any deficit — a final game with
   zero appearance rows, a game holding fewer rows than the pitching lines its
   ingest saw, or an incomplete/failed postgame marker — leaves the new
   snapshot `pending` with reason
   `dashboard_snapshot_appearance_ledger_incomplete`; readers keep receiving
   the previous published snapshot.
3. **Tonight refresh** (daily/postgame modes) — schedule ±10 days re-ingest
   and Tonight cache warm.
4. **Appearance ledger audit (workflow gate)** —
   `appearance_ledger_audit.py --days 10 --deep` re-proves publish
   eligibility from the database and prints the verdict:
   - exit 0 → `::notice` **Publish eligible: YES** — run continues.
   - exit 1 → `::error` **Publish eligible: NO** — the workflow **fails
     loudly**. The report (uploaded as the `appearance-ledger-audit-<run id>`
     artifact) names missing game_pks, dates with holes, and — via `--deep` —
     the affected players and their latest-appearance mismatches. Remediate
     with `mode=backfill` on the flagged slate date.
   - exit 2 / timeout → the audit itself could not run; eligibility is
     UNPROVEN and the workflow fails.
5. **Dashboard snapshot cache verification** — confirms the public dashboard
   endpoint serves a published cache (`served_from=cache`,
   `is_published=true`, `data_through` present).

Downstream jobs (`internal-enrichment`, `static-team-story-preview`) run only
after `public-sync` succeeds, so a failed ledger verdict also stops enrichment
and static page publication from advancing on unproven data.

## Reading a failure

- **Workflow red on "Appearance ledger audit"** → the ledger has a hole; the
  public dashboard is still serving the last trusted snapshot. Read the audit
  artifact, then dispatch `mode=backfill` with the flagged date and re-run.
- **`daily gameLog lane` dead-letter / `game_log_lane_health:
  all_window_splits_dropped` in the sync summary** → the daily lane dropped
  every in-window split at the finality gate — investigate before trusting
  freshness.
- **Snapshot withheld (`error_message` on the pending snapshot row)** → the
  in-process gate fired before the workflow audit; same remediation.

## Runtime budgets and profiling

Every daily sync logs a per-stage timing summary and an MLB API call count
grouped by endpoint template (`Daily sync stage timings (s): ... API calls:
... by endpoint: ...`), and the summary JSON carries `stage_timings`,
`api_calls_by_endpoint`, `elapsed_seconds` / `fetch_seconds` /
`process_seconds` for the gameLog stage, and `budget_exhausted_pitchers`.

The daily command runs under a **whole-process soft budget**
(`DAILY_SYNC_TOTAL_BUDGET_SECONDS`, workflow value 1080s) with explicit reserve
for required final phases (`DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS`, workflow
value 300s). The gameLog ingestion budget is derived from the total remaining
time after that reserve and capped by `DAILY_SYNC_INGESTION_BUDGET_SECONDS`
(workflow value 720s).

When the derived ingestion budget is exceeded, the stage stops cleanly: the
remaining pitchers are dead-lettered in one `daily_game_log_budget` record
(counts + mlb_ids), `records_failed` includes them, the run finishes **partial**
with `lane_health=budget_exhausted`, and the next daily run (or the postgame
lookback) retries them. This is fail-closed by construction — a truncated sweep
is visible and counted, never absorbed — and the Python process keeps enough
headroom to run fatigue, snapshot publish/withhold, durable metadata,
writer-guard release, and cleanup before the 20-minute shell timeout.

Pitcher-season ledger coverage is not recomputed for every full-season target
on every daily run. The daily hot path verifies only the accepted current-window
targets while preserving the same source-vs-stored manifest proof for each
target. Full-season coverage maintenance remains available through the
production maintenance workflow.

## Operator tools

- `python backend/scripts/appearance_ledger_audit.py [--end-date D --days N --deep --json]`
- `python backend/scripts/sync_trace.py --player <mlb_id> --date <YYYY-MM-DD> [--game-pk PK] [--no-network]`
- `python backend/scripts/run_postgame_refresh.py --date <YYYY-MM-DD> --source manual_backfill`
- Kill switch (operators only, logged): `APPEARANCE_LEDGER_GATE_ENABLED=false`
