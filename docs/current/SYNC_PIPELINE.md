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
| Run workflow → `mode: intraday` | manual only | audit-only intraday reconciliation (Phase 1 — no writes) |

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

## Intraday reconciliation (audit-only, Phase 1)

**Canonical reference: [`INTRADAY_RECONCILIATION.md`](INTRADAY_RECONCILIATION.md)**
— the four-mode architecture, motivating incident, output contract and status
meanings, locking/overlap behavior, required validation period, and future
phases. The summary below is the pipeline-level view; that document is
authoritative.

A real production gap on 2026-07-16 — the Phillies recalled Seth Johnson after
the morning daily sync, and BaseballOS kept treating him as outside the active
roster until the next full sync — motivated a fourth mode, `intraday`: a
lightweight, delta-aware reconciliation throughout the baseball day. This branch
ships **Phase 1 of that mode only, and it is AUDIT-ONLY: manual, read-only, and
non-publishing.** It proves change detection is accurate before any write
behavior is authorized.

- **Trigger:** manual only (`Run workflow → mode: intraday`). There is **no
  cron** for it and it must never become an hourly full sync. It runs in the
  isolated `intraday-audit` job, so it never touches the publish lane (no snapshot
  publish/withhold, no appearance-ledger gate, no dashboard-cache verification).
- **What it does:** fetches current authoritative source state through the same
  MLB client, retry policy, product-date authority, and read-only source helpers
  the daily/postgame syncs already own (`build_team_roster_status_index` /
  `classify_roster_evidence`, `get_transactions` + `is_non_player_transaction`,
  `get_schedule` + `classify_status` + `resolve_scheduled_game_finality`),
  compares it with stored state, and reports the differences.
- **What it never does:** no canonical baseball-data writes, no roster/status/
  transaction/dead-letter mutation, no snapshot publication, no fatigue
  recalculation, no story generation, no public cache warming, and it never
  acquires the sync writer guard. The service self-certifies this with a
  `write_guard` check that fails closed if the ORM session ever holds a pending
  write.
- **Lanes:**
  1. *Active roster + team assignment* — official **active-roster** evidence for
     every MLB team vs stored pitcher state. The production default fetches one
     active-roster request per team (~30 calls), not the four-roster-type sweep
     (~120), because the intraday question is only whether *active*-roster state
     moved after the morning sync. It still detects entry to / departure from the
     active roster, team-assignment changes, newly discovered active pitchers
     (with their source names preserved), conflicting official team evidence, and
     source rows that cannot be safely matched to an MLB identity (never
     name-matched). Where only a departure is proven, a neutral
     `removed_from_active_roster` change type is used — an exact inactive
     destination (IL / optioned / DFA) is never inferred from active-roster
     absence alone. The specific-destination classification remains available as
     a manual deep-diagnostic sweep (`--deep-roster`).
  2. *Transactions* — recent official transactions vs stored transaction
     evidence, **event-aware, bullpen-relevance-gated, and current-membership-
     aware** (contract 1.2.0). Source components are grouped by their stable MLB
     transaction-event id, so a compound event yields at most one finding. A
     finding is materially actionable only when its participant is proven a
     pitcher / two-way player from the MLB id (a tracked `Pitcher` row, source
     position evidence, or a bounded/deduplicated `/people` lookup — never from
     name or transaction type); proven non-pitchers are informational and
     unresolved roles are review-required. Exact stored-state alignment is
     separated from public active-bullpen membership: a historical option/IL
     effect whose latest applicable event and current roster-lane membership prove
     the pitcher is correctly outside the active bullpen is benign
     (`transaction_detail_mismatch` / `superseded_transaction`), never material;
     only a genuine current mismatch is `public_bullpen_effect_unreflected`.
     **Transaction-record actionability is separate from public materiality**
     (contract 1.3.0, Observation #3): a missing/actionable record is
     transaction-ledger actionable but is NOT public-material unless its type can
     change active membership AND the roster lane confirms a current change —
     organization/ledger records (`SGN`/`SFA`/`ASG`), `effect_direction=none`, and
     unknown types (fail-closed) never publish. Public team impact is scoped to the
     governed MLB clubs — affiliate / minor-league ids stay in evidence
     (`non_mlb_team_ids_observed`) but never in `affected_team_ids` /
     `recalculate_team_reads`. Only **meaningful** findings are serialized; benign
     inventory is counted, bounded-sampled, and reported with a
     `benign_records_suppressed` total.
  3. *Schedule + game finality* — the current and previous slate dates: newly
     final games, postponements/reschedules, in-progress games, and stored
     finality conflicts.
  4. *Impact plan* — a dry-run `would_refresh` projection split into two
     sub-plans: `public_bullpen_state` (roster/current-state-authoritative — teams,
     targeted pitcher logs, completed game_pks, publish/warm) and
     `transaction_ledger` (records to ingest/reconcile). The flat `would_refresh`
     fields derive **only** from `public_bullpen_state`; transaction-ledger-only
     findings never set public teams, targeted workload, snapshot, or warm. Every
     value is a projection; this audit performs none of it. The roster lane owns
     public current-state materiality and overlapping players/teams are deduped to
     one public impact.
- **`changed` vs material.** Top-level `changed` is true when any meaningful
  finding exists (actionable *or* review-required), so a real
  human-review-required finding is never hidden. `material_change_detected` is
  true only when a future authorized write/recompute would actually be required
  (an actionable finding or a newly-final game). Benign inventory sets neither.
  The `summary` block (contract `version` 1.4.0) carries honest, explicitly
  scoped buckets — `records_checked`, `total_meaningful_findings`,
  `total_actionable_findings`, `review_required_findings`, `unresolved_findings`,
  the transaction-ledger axis (`transaction_record_actionable_count`,
  `transaction_ledger_only_findings`,
  `transaction_public_bullpen_material_count`), the public axis
  (`public_roster_change_count`, `schedule_public_change_count`,
  `public_bullpen_change_count`), `informational_records`, and
  `benign_records_suppressed`. Each aggregate has one derivation source, and the
  deduplicated `public_bullpen_change_count` is `> 0` exactly when
  `public_bullpen_change_detected` is true — a meaningful/actionable finding does
  not by itself imply a public bullpen change.
- **Operator command (read-only):**

  ```
  python backend/scripts/run_intraday_reconcile.py --source manual --json [--output PATH] [--lanes roster_assignment,transactions,schedule_finality]
  ```

  Human-readable progress goes to stderr; a single JSON audit artifact goes to
  stdout with `--json`. The workflow uploads it as the
  `intraday-reconciliation-audit-<run id>` artifact.

- **Production configuration.** The intraday job runs `APP_ENV=production`, so
  production Flask initialization requires `DATABASE_URL`, `SECRET_KEY`, and
  `ADMIN_API_TOKEN`. The workflow maps the existing `BASEBALLOS_ADMIN_API_TOKEN`
  repository secret to `ADMIN_API_TOKEN` (the admin token gates operational
  write endpoints; it does not authorize any write — the audit stays read-only).
  Missing configuration is a **bootstrap failure, not a partial source
  verification**: the CLI still emits a valid `failed` JSON artifact
  (`reason_code: application_bootstrap_failed`) and exits 1, and the workflow
  validates the artifact contract before upload. See
  [`INTRADAY_RECONCILIATION.md` §12](INTRADAY_RECONCILIATION.md).

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

## Roster-readiness recovery notes (2026-07-13)

Two production blockers were fixed together after Phase 0I shipped; the
behaviors below are load-bearing for the daily pipeline.

**Batched roster cache-divergence scan.** Roster readiness
(`public_roster_readiness_v1`) checks cache-vs-snapshot divergence on every
Team Board build. The scan is set-based: one query for the active-pitcher
universe plus one window-function query for each pitcher's latest snapshot
(`latest_roster_status_snapshots_by_pitcher_id`), instead of one query per
pitcher. Divergence semantics are unchanged — same pitcher universe, same
latest-snapshot ordering (`snapshot_date desc, updated_at desc, id desc`),
same compared fields — and equivalence plus a query-count bound (≤10 queries
per readiness evaluation, flat as the population grows) are enforced by
`backend/tests/test_roster_divergence_batching.py`. This keeps the static
team-story export (30 boards per run) far inside its 15-minute job timeout;
the export also logs one `Building team board i/N` line per team so a failed
run identifies the last completed team.

**Non-player transaction components.** The MLB transactions feed includes
team-level trade components (cash considerations, players to be named later,
international slot money) that reference no person. Rows whose structured
record carries neither `player_mlb_id` nor `player_full_name` are classified
`non_player_transaction`: counted in the sync summary (`non_player_count`),
logged with their transaction id and type code, never stored as player
transactions, and never dead-lettered. A row that references a person (a name
is present) but lacks a usable id is still a `player_transactions_identity`
dead letter and keeps the run partial — that gate is unchanged.

**Dead-letter reconciliation.** When a source transaction is later stored
successfully or deterministically classified non-player, its exact matching
unresolved `player_transactions_identity` dead letters are marked resolved
(timestamped, idempotent; rows are preserved, never deleted). A failure that
repeats across runs still counts against `records_failed` on every run but no
longer accumulates one duplicate unresolved row per run.

**Verifying roster readiness after a deploy or sync:**

```
curl -s https://<backend-host>/api/bullpen/teams/142/board \
  | jq '.roster_authority.readiness | {readiness_state, claims_available, counts_withheld, reason_codes, coverage}'
```

`claims_available: true` means roster claims are being served; otherwise
`reason_codes` names the exact blocker.

**Roster dead-letter reconciliation.** Public roster readiness fails closed on
ANY unresolved `roster_status_fetch` / `roster_status_snapshot_identity` /
`roster_status_snapshot_conflict` dead letter (reason code
`dead_letters_unresolved`; the gate is league-wide, so one genuine conflict
withholds every team). The daily roster sync now reconciles these against
newer authoritative official roster evidence, and only that:

- *fetch* rows resolve when the same team's roster feeds fetch successfully
  (pre-existing behavior);
- *identity* rows resolve when a later sync enumerates the same team's feeds
  and identifies every entry (a run that records a fresh identity failure for
  the team resolves nothing);
- *conflict* rows resolve when a later sync writes or confirms the same
  pitcher's official snapshot without a team conflict (a pitcher whose upsert
  conflicts in the current run is never self-resolved).

Rows are never deleted — resolution sets `resolved`/`resolved_at` only, is
idempotent, resolves duplicate rows for the same entity together, and genuine
or ambiguous conflicts stay unresolved and keep claims withheld. Inspect the
current blockers (read-only) with:

```
python backend/scripts/roster_readiness_dead_letter_report.py [--json] [--include-resolved]
```

**Confirming the current run's snapshot published (not an older one):** the
sync log line `Dashboard snapshot DB write completed snapshot_id=<id>
status=ready published=True` must show the new id, and
`/api/bullpen/dashboard` must serve that same `snapshot.snapshot_id`. A line
showing `status=pending published=False` means publication was withheld for
this run and the previously trusted snapshot is still serving — the workflow's
cache-verification step alone does not prove the new candidate published.
