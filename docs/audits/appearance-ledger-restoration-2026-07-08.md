# BASEBALLOS APPEARANCE LEDGER RESTORATION

Date: 2026-07-08 · Branch: `claude/baseballos-sync-audit-qvnw0s` · Follow-up to: `sync-reliability-audit-2026-07-08.md`

## Executive Summary

The missed-appearance trust incident (Samy Natera Jr., LAA, July 4 vs BOS) had three
stacked causes: a dead daily gameLog lane, a postgame job with no lookback, and a
publish gate blind to anything behind the newest data date. All three are fixed,
fail-closed, and covered by regression tests. Two new operator tools — an
appearance-ledger audit and a per-player sync trace — make the ledger provable on
demand, and the dashboard snapshot publisher now refuses to publish any window with
an unproven appearance ledger.

## Root Cause Fixed

1. **Daily lane** (`services/sync.py:_ingest_game_log_split`): statusless gameLog
   splits — the production shape of `people/{id}/stats?stats=gameLog` — were skipped
   as non-final since commit `552fcb8` (Jul 3). Finality is now resolved from the
   `scheduled_games` ledger: final → ingest; determinately non-final → retry-later
   skip; unknown → dead-letter (`game_log_unresolved_finality`) counted into
   `records_failed`. Nothing is ever silently dropped.
2. **Postgame recovery** (`services/sync.py:run_postgame_refresh`): now sweeps the
   primary slate date plus `POSTGAME_LOOKBACK_DAYS` (default 2) trailing dates,
   oldest first. Fully-processed markers make re-sweeps nearly free. A crashed
   overnight run self-heals on the next scheduled pass. Explicit `--date` still
   restricts the sweep for manual replays.
3. **Publish gate** (`services/appearance_ledger.py` +
   `services/dashboard_snapshot.py:publish_dashboard_snapshot`): before any publish,
   the appearance ledger over a trailing window (default 10 days,
   `APPEARANCE_LEDGER_WINDOW_DAYS`) is reconciled: scheduled finals vs stored
   `game_logs` rows vs postgame markers. Any deficit — a final game with zero rows,
   a game with fewer rows than pitching lines its ingest saw, or an
   incomplete/failed marker — withholds publication (`error_message =
   dashboard_snapshot_appearance_ledger_incomplete`), keeps the previous trusted
   snapshot serving, and logs the exact game_pks. An uncomputable ledger also
   blocks. Kill switch: `APPEARANCE_LEDGER_GATE_ENABLED` (explicit, logged).

## Files Changed

| File | Change |
|---|---|
| `backend/services/sync.py` | Statusless-split finality resolution via `scheduled_games` (+cache); skip-reason counters; lane-health canary; unresolved-finality dead-letters; postgame trailing-date sweep with per-game slate dates |
| `backend/services/appearance_ledger.py` | NEW — ledger reconciliation service + fail-closed publish block |
| `backend/services/dashboard_snapshot.py` | Ledger gate wired into `publish_dashboard_snapshot`; new withheld reason surfaced to readers |
| `backend/scripts/appearance_ledger_audit.py` | NEW — audit command with publish-eligible verdict, `--deep` player-level mismatch inspection, `--json` |
| `backend/scripts/sync_trace.py` | NEW — per-player/date pipeline trace, PASS/FAIL per stage |
| `backend/tests/test_statusless_split_finality.py` | NEW — 9 tests incl. Samy Natera reproduction and correction-lane regression |
| `backend/tests/test_postgame_lookback.py` | NEW — 5 tests: missed-slate replay, cheap re-sweep, explicit-date restriction, date resolution |
| `backend/tests/test_appearance_ledger.py` | NEW — 12 tests: reconciliation + gate block/pass/fail-closed/kill-switch |
| `backend/tests/test_mapper_registry_smoke.py` | NEW — 3 tests configuring the full mapper registry along each sync entrypoint import path (July 5 crash class) |
| `backend/tests/test_unknown_safe_ingestion.py` | Statusless-split expectation updated: dead-lettered + counted instead of silently dropped |
| `backend/tests/test_dashboard_snapshot.py` | Publish-expecting stale-slate test now seeds an appearance row (final games must hold rows to pass the gate) |
| `backend/tests/test_snapshot_trust_freeze.py`, `backend/tests/test_public_team_relief_work.py` | `sync.py`/`dashboard_snapshot.py` removed from the phase-0e diff freezes (documented in-file); behavior now pinned by the dedicated suites above |

Why each was necessary: (1) the daily lane is the designed 7-day backfill and
correction net — dead since Jul 3, it turned every other failure permanent;
(2) single-date postgame scope is what made one crashed night unrecoverable;
(3) without a trailing-window gate, holes behind `data_through` publish as current
forever; (4–5) the tools make the ledger provable and single incidents debuggable;
(6–12) regression coverage and deliberate freeze amendments, no coverage removed.

## Implementation Details

### Daily Lane Restoration
`resolve_scheduled_game_finality(game_pk)` consults `scheduled_games` (ingested
±10 days daily): any-row-final → FINAL; suspended/unresolved resumed linkage →
NOT_FINAL (fail-closed, retried later); no rows → UNKNOWN → dead-letter. Splits
carrying their own status keep the existing trust-the-status behavior. The cutoff
check now runs before finality so season-long responses cost at most one schedule
lookup per in-window game per run (shared cache). `sync_recent_logs` reports
`splits_seen`, `splits_skipped{missing_key,not_completed,before_cutoff}`,
`logs_unchanged`, `unresolved_finality`, and `lane_health`; if every in-window
split drops at the finality gate the run records a `daily_game_log_lane`
dead-letter and goes partial — a dead lane can never look green again.

### Postgame Recovery
`postgame_schedule_dates()` = primary date (existing 6 AM ET boundary logic) plus
lookback, oldest first so recovery lands even if a run is cut short. Discovery
unions `completed_games_for_postgame_refresh` per date (schedule API + stored
finals fallback), deduped by game_pk; each game processes under its own slate date
(markers, contexts, play-by-play, dead-letter payloads). Internal enrichment
phases receive the slate dates that actually changed.

### Ledger Integrity Gate
`build_appearance_ledger(end_date, window_days)` returns per-date expected vs
represented games, expected vs stored appearance counts, missing/count-deficit/
incomplete-marker game lists, and a `complete` verdict. The publish gate runs
after the existing slate-coverage check inside `publish_dashboard_snapshot`, in
the same transaction discipline (withheld snapshots stay `pending`, previous
published snapshot keeps serving, readers see the honest withheld reason through
`snapshot_unavailable_reason`).

### Debug Utilities
- `python backend/scripts/appearance_ledger_audit.py [--end-date D --days N --deep --json]`
  — exit 0 = publish eligible, 1 = deficits, 2 = audit unavailable.
- `python backend/scripts/sync_trace.py --player 696519 --date 2026-07-04
  [--game-pk PK] [--no-network]` — stages: pitcher record → schedule discovered →
  game final → boxscore fetched → appearance parsed → database row → postgame
  marker → aggregation → snapshot → frontend endpoint.

## Tests Added
29 new tests across four files (statusless finality ×9, postgame lookback ×5,
appearance ledger ×12, mapper smoke ×3), plus updated expectations in three
existing files. Coverage includes: statusless split ingest/skip/dead-letter, the
Samy Natera July 2→July 4 reproduction, the correction lane through a statusless
split, replay after a missed postgame night, cheap re-sweep of processed slates,
gate blocking incomplete data, gate passing complete data, gate failing closed on
computation error, the explicit kill switch, and the July 5 mapper crash class.

## Regression Results
Full backend suite: **2,92x passed, 0 regressions** (see PR CI for the canonical
run). Ten tests fail identically on clean `origin/main` in a no-`DATABASE_URL`
local container (app-factory/CORS/auth/observation/availability-snapshot-mode +
`test_recommendation_api` collection) — pre-existing environment dependencies
that CI satisfies with its Postgres service.

## Production Verification (local replay evidence + prod runbook)
A scratch-database replay of the incident (real code paths; only the MLB API and
the full dashboard payload builder stubbed) verified end-to-end:
1. Failure state seeded (July 4 final, zero rows) → ledger audit: **Publish
   eligible: NO**, missing game_pk listed → `publish_dashboard_snapshot` withheld
   with `dashboard_snapshot_appearance_ledger_incomplete`.
2. Replay `run_postgame_refresh(schedule_date=2026-07-04)` **with the schedule API
   returning nothing** → stored-final fallback discovered the game, ingested 2
   pitching lines, created the unknown pitcher, wrote the marker; Samy Natera Jr.
   (696519) now shows July 2 **and July 4**.
3. Daily lane: statusless split with a revised stat line → `logs_corrected=1`
   (pitch count 17→21, provenance stamped), `lane_health=ok` — the correction
   lane produces non-zero activity again.
4. Ledger audit: **Publish eligible: YES** → publish allowed.
5. `sync_trace.py --player 696519 --date 2026-07-04` → every stage PASS.

Production runbook (in order):
1. Merge; let CI (Postgres) confirm the suite.
2. `python backend/scripts/appearance_ledger_audit.py --days 10 --deep` against
   prod — expect NO with the July 4 game_pks and affected players named.
3. `python backend/scripts/run_postgame_refresh.py --date 2026-07-04 --source manual_backfill`
   (repeat for July 5 if the audit flags it).
4. Re-run the audit — expect YES; run `sync_trace.py --player 696519 --date 2026-07-04`.
5. Next morning: daily sync summary shows `splits_seen` > 0, nonzero
   `logs_unchanged`/`logs_corrected`, `game_log_lane_health: ok`.
6. Watch one full cron cycle; confirm the first snapshot publish after backfill
   and that the dashboard `data_through` advances normally.

## Remaining Risks
- The ledger gate can only count appearances for games with a postgame marker; a
  game backfilled solely by the daily lane is proven present but not count-proven
  (a debut pitcher missing from that game would be invisible until its marker
  exists). The postgame lookback makes this window small.
- A `failed` postgame marker (3 attempts exhausted) now blocks publishing until an
  operator intervenes — intended fail-closed behavior, but it makes marker re-arm
  tooling (dead-letter replay) the next priority.
- Until the July 4 backfill runs in production, the gate will (correctly) withhold
  new publishes; the dashboard keeps serving the previous snapshot. Run the
  backfill promptly after deploy.
- `expected_appearances` counts all pitching lines (starters included); the label
  says so. Reliever-only refinement would need role joins and adds no safety.

## Recommendation
Merge after CI, run the production backfill immediately (step 3 above), and
schedule `appearance_ledger_audit.py --deep` as a daily post-sync CI step so the
publish-eligibility verdict is visible in every run log. Then prioritize
dead-letter replay / marker re-arm tooling as the follow-up.
