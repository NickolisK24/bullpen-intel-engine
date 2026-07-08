# BASEBALLOS SYNC RELIABILITY AUDIT — READ ONLY

Date: 2026-07-08 · Trigger: Samy Natera Jr. (LAA) missing July 4 appearance vs BOS · Scope: full sync pipeline
Status: **Root cause identified with direct production evidence. No code changed by this audit.**

---

## 1. Result Up Front

The July 4 appearance is missing because **both ingestion lanes failed simultaneously, and the system has no recovery lane and no integrity gate that would have noticed**:

1. **Acute trigger** — the three overnight GitHub Actions passes that would have ingested the *late* July 4 games crashed with a SQLAlchemy mapper-registration error (`ComposedReadEvidenceCitation` → `'EvidenceObject' failed to locate a name`) before fetching a single game. The 23:01 ET July 4 pass succeeded but found only **8 completed games** on the July 4 slate; every game that went final after ~23:01 ET was never postgame-processed. The bug was introduced by the phase-0e composed-read model work merged the night of July 4–5 and fixed at 12:43 ET July 5 (`6c7297f`), but the postgame job only ever inspects **one schedule date** — from July 5 evening onward it looked at July 5+, and the July 4 slate was never revisited.

2. **Systemic root cause (still live today)** — the daily sync is the designed 7-day backfill/correction safety net, but commit `552fcb8` ("fix: preserve unknown pitch counts and gate non-final logs", **July 3, 22:20 ET**) added `if not is_completed_game(game_info)` to `_ingest_game_log_split` (`backend/services/sync.py:1999`). `game_info` is the `game` object of an MLB **gameLog** split, and the repo's own test (`test_daily_ingestion_excludes_ambiguous_statusless_split`, `backend/tests/test_unknown_safe_ingestion.py:255-263`) codifies that a statusless split is *silently skipped*. Production behavior since the gate: **every daily sync from July 4 through July 8 reports `new_logs_added: 0, logs_corrected: 0`** — including July 6/7/8 runs whose 7-day window covered the known July 4 hole. The daily gameLog lane ingests and corrects **nothing**. The backfill net that should have healed the July 4 outage within 24 hours is dead.

3. **No integrity gate** — the publish-time slate-coverage check (`backend/services/slate_coverage.py`) validates **only the `data_through` slate** (the single most recent date with any game-log row). Once July 5 games were ingested, `data_through` advanced past July 4 and the hole became permanently invisible to every guard. Snapshots 162→183 published normally on top of incomplete July 4 data.

Blast radius: every appearance in every game that went final after ~23:01 ET on July 4 (~half the holiday slate; the four games processed at 23:01 averaged ~9 pitching lines each, so plausibly **50–70 missing appearance rows across ~a dozen teams**), plus **all MLB stat corrections league-wide since July 4** (the correction lane is the same dead daily lane), plus derived workload/availability/fatigue/stories built on the missing rows. Missing appearances bias availability **toward "more rested / more available"** — the worst direction for trust.

---

## 2. Concrete Discrepancy: Samy Natera Jr.

| Question | Finding | Evidence |
|---|---|---|
| MLB player ID | **696519** | BaseballOS's own export `artifacts/todays_story_editorial_review_E2C5A.md:398-403` ("Samy Natera Jr.", `player_id: 696519`, LAA monitor list). Consistent with an MLB Stats person id. *Not re-verified against statsapi.mlb.com — outbound network to MLB is blocked in this audit environment.* |
| July 4 LAA vs BOS in fetched schedule? | Yes at the schedule level — the July 4 daily run ingested 262 scheduled games into `scheduled_games` (run 28703608573 log: `games_ingested: 262`, ±10-day window). The game exists as ScheduledGame rows. | Run log 28703608573 |
| Game feed/boxscore fetched? | **No.** The only successful postgame passes over the July 4 slate ran at 18:44 ET and 23:01 ET on July 4 and together processed 8 games (game_pks 824499, 824171, 824415, 824092 at 23:01 + 4 earlier). LAA@BOS was not among the completed set by 23:01 ET; the 01:17 ET and 03:02 ET passes that would have caught it crashed with `games_found: 0`. | Run logs 28722065598 (success), 28727638803 (`Found 8 completed game(s)`), 28730472698 + 28732771422 (mapper crash, `status: failed`) |
| Sync processed that game? | No postgame marker was ever written for it (crashes happened before game discovery), and no later run ever looked at 2026-07-04 again (`postgame_schedule_date` resolves exactly one date, `sync.py:130-142`; stored-final fallback is also single-date, `sync.py:178-211`). | Code + run logs |
| Appearance row written? | **No** (inference from the above: neither lane executed for this game). Cannot query prod DB from this environment — see §13. |
| Row later overwritten/deleted? | **No delete path exists.** `game_logs` has unique `(pitcher_id, mlb_game_pk)` (`models/game_log.py:46`); the only DELETE anywhere is a one-time dedup migration (`migrations/versions/9f3c1a7b2d4e`). The row was never written, not removed. |
| Aggregation includes it? | No — aggregations read `game_logs`; the row is absent. His board card/availability is computed from July 2 back ("2 appearances in 5 days" style), overstating rest. |
| Snapshot includes it? | No — snapshots 162–183 were built from the same DB. `data_through` advanced to July 5+ via other games, so no guard flagged the hole. |
| Frontend returns it? | No — Pitcher Detail (`GET /api/bullpen/fatigue/<id>` + `/pitchers/<id>/recent-work`) and Team Board read **live** GameLog (`api/bullpen.py:502-548, 1551-1698`); they faithfully show the DB, which ends July 2 for him. This is a **backend data hole, not a frontend cache issue**. |

**Verdict: the appearance was never acquired.** Everything downstream is consistent with the DB.

---

## 3. Pipeline Map

```
GitHub Actions (.github/workflows/baseballos-sync.yml)
├─ cron 0 10 * * * UTC  → run_daily_sync.py --days-back 7 --public-only   [20m timeout]
├─ cron 0 2,4,6 * * * UTC → run_postgame_refresh.py --public-only          [20m timeout]
├─ then run_tonight_refresh.py (schedule ±10d ingest + Tonight warm)
├─ internal-enrichment job (continue-on-error: true — failures don't block anything)
└─ static-team-story-preview job → commits frontend/public/team/* to main

DAILY LANE  (services/sync.py:3585 run_daily_sync)
  writer guard → SyncRun row → team assignments → roster statuses → transactions
  → sync_recent_logs (sync.py:1799):
       population = Pitcher.query.filter_by(active=True)          ← existing rows only
       per pitcher: GET /people/{id}/stats?stats=gameLog&group=pitching&season=YYYY
       per split: skip if no gamePk/date → SKIP if not is_completed_game(game.status) ← DEAD GATE
                  skip if date < today-7 → upsert on (pitcher_id, mlb_game_pk)
       one commit for the whole batch (sync.py:1948)
  → recalculate_all_fatigue (active=True only, skips unresolved-fetch pitchers)
  → complete_sync_run_with_snapshot: finish run + build/publish dashboard snapshot, atomic commit
     status partial (dead-letters) still publishes; SUCCESSFUL_STATUSES = (success, partial)

POSTGAME LANE  (services/sync.py:3128 run_postgame_refresh)
  schedule_date = ET-today (or yesterday before 6 AM ET)          ← SINGLE DATE ONLY
  completed = schedule API finals + stored ScheduledGame finals (same date)
  skip games with marker fully_processed or failed(attempts≥3)     ← NEVER RE-EXAMINED
  per game: fetch boxscore → extract pitching lines → resolve/create Pitcher
            → upsert GameLog per line → marker fully_processed/incomplete/failed
  → play-by-play foundation → completed-game contexts → fatigue → snapshot publish (if logs changed)

PUBLISH   dashboard_snapshots: insert pending row → publish flips is_published in one txn
          withheld only if slate coverage for data_through slate incomplete
          data_through = MAX(game_date) over all game_logs         ← not a completeness claim

FRONTEND  Pitcher Detail + Team Board = live DB reads (no HTTP cache, no client cache)
          League dashboard = published snapshot payload
          frontend/public/team/*.html = daily-committed static OG pages (meta text only)
```

---

## 4. Evidence Collected

**Production run history** (GitHub Actions, workflow `baseballos-sync.yml`):

| Run | UTC time | Mode | Result | Key numbers |
|---|---|---|---|---|
| 28656006110 | Jul 3 10:55 | daily (pre-gate) | success | `new_logs_added: 0` (postgame had covered the slate); summary JSON has **no `logs_corrected` key** — the field shipped with the gate commit |
| 28703608573 | Jul 4 10:40 | daily (**first post-gate**) | success | `new_logs_added: 0, logs_corrected: 0` |
| 28722065598 | Jul 4 22:44 | postgame (manual) | success | processed first 4 July 4 finals |
| 28727638803 | Jul 5 03:01 | postgame (sched 2026-07-04) | success | `Found 8 completed game(s); 4 fully processed... 4 pending`; `logs_added: 35, pitchers_created: 2`; snapshot 162 |
| 28730472698 | Jul 5 05:17 | postgame (sched 2026-07-04) | **failed** | `InvalidRequestError ... 'EvidenceObject' failed to locate a name` at `acquire_sync_writer_guard` → `games_found: 0` |
| 28732771422 | Jul 5 07:02 | postgame (sched 2026-07-04) | **failed** | same mapper error |
| 28738129441 | Jul 5 10:44 | daily | **failed** | same mapper error; `new_logs_added: 0` |
| 28727+ (Jul 5 16:46–23:38) | — | 10 manual runs | mostly failed | operator fighting the incident; fix `6c7297f` ("register evidence object mapper for sync runtime") landed 12:43 ET |
| 28788509290 | Jul 6 11:33 | daily | partial | `new_logs_added: 0, logs_corrected: 0` — window covered Jul 4; **no backfill happened** |
| 28914254767 | Jul 8 03:00 | postgame (sched 2026-07-07) | success | `Found 13; processed 13; logs_added: 116` — postgame lane healthy for current slates |
| 28936592919 | Jul 8 10:43 | daily | partial (published snapshot 183) | `new_logs_added: 0, logs_corrected: 0` |

**Code evidence** (file:line):
- Dead gate: `services/sync.py:1999-2000`; introduced by `552fcb8` (2026-07-03 22:20 ET); `is_completed_game` → `has_safe_final_status` (`sync.py:145-147`, `game_finality.py:210-212`) returns False for a game dict with no/unknown `status` (missing status → `UNKNOWN`, `game_finality.py:191-196`).
- Author-codified statusless skip: `tests/test_unknown_safe_ingestion.py:255-263` asserts a split whose `game` = `{'gamePk', 'gameType'}` (no `status`) yields `new_logs_added == 0`. The gameLog fetch (`mlb_api.py:448-463`) sends **no hydrate that would attach status**.
- Daily population: `Pitcher.query.filter_by(active=True)` (`sync.py:1848`) — pitchers not yet in the table (call-ups) are only ever created by the postgame boxscore lane (`sync.py:925-947`); `team_assignment_sync._apply_assignment` (`team_assignment_sync.py:314-338`) can set `active=False` fail-closed, excluding a pitcher from the daily fetch entirely.
- Postgame single-date window: `postgame_schedule_date` (`sync.py:130-142`); stored-final fallback also single-date (`sync.py:178-211`).
- Marker no-retry: `fully_processed` markers are permanently skipped (`sync.py:1241-1265`); `incomplete` retries max 3 then permanent `failed` (`sync.py:86, 1104-1109`); finality-pending games are still processed and marked (only an INFO log, `sync.py:1302-1308`).
- Dead letters have **no replay mechanism** — they auto-resolve only if the same entity later succeeds through the normal loop (`dead_letter.py:110-147`; `resolve()` has no production callers).
- Publish gate scope: coverage validates one `slate_date` = `data_through` (`slate_coverage.py:164-167, 618-638`); `data_through` = global `MAX(game_date)` (`sync_metadata.py:484-496`, `board_freshness.py:42`); **no trailing-window completeness check exists**.
- Partial publishes: `STATUS_PARTIAL if records_failed else SUCCESS` (`sync.py:3759-3762`); `SUCCESSFUL_STATUSES = (success, partial)` (`sync_metadata.py:45`).
- No destructive paths: unique `(pitcher_id, mlb_game_pk)` (`models/game_log.py:46`); zero production deletes of GameLog/Pitcher (repo-wide grep); unsafe corrections fail closed (`sync.py:578-595`).
- Frontend reads live DB for pitcher/team surfaces (`api/bullpen.py:482-548, 1551-1698`; `public_recent_work.py:56-77`); no HTTP cache headers; no client-side payload caching (`frontend/src/utils/api.js`, `hooks/useFetch.js`).

---

## 5. Where the Data Disappears

Single point of loss: **acquisition**. The appearance never reaches `game_logs`. There is no overwrite, delete, aggregation filter, snapshot omission, or frontend cache implicated for this incident (aggregation/publish faithfully reflect the missing row — and then *hide* the miss by advancing `data_through`).

The precise loss sequence for a late July 4 game:
1. Game goes final after ~23:01 ET Jul 4 → not in the last successful postgame pass for that slate.
2. 01:17/03:02 ET passes crash pre-discovery (mapper bug) → no marker, no dead-letter *for the game* (crash was above per-game error handling).
3. From Jul 5 evening, postgame inspects only `schedule_date >= 2026-07-05` → game permanently out of scope.
4. Daily lane (designed 7-day net) skips every split as `not_completed` (statusless gameLog `game` object) → no backfill, silently: the skip isn't counted, logged, or dead-lettered.
5. `data_through` advances via July 5+ ingestion → slate-coverage gate never re-examines July 4 → snapshots publish "current".

---

## 6. Failure Modes (ranked)

1. **Daily gameLog lane silently dead** (`sync.py:1999`) — CRITICAL, ongoing. Kills backfill *and* all stat corrections league-wide. Zero observability: skips aren't counted or logged.
2. **Postgame window is one date with no lookback** (`sync.py:130-163`) — CRITICAL enabler. Any missed night (crash, timeout, Actions outage, late West Coast finish before 6 AM cutoff quirks, suspended game resuming days later) is a permanent hole once the calendar advances.
3. **No cross-day integrity gate** — publish validates only the `data_through` slate; historical holes are invisible forever (`slate_coverage.py`).
4. **Import-order/mapper fragility in the sync runtime** — a model added for an unrelated feature (composed reads) crashed *acquisition* jobs. Sync entrypoints don't import the full model registry deterministically; regression can recur.
5. **Marker terminal states without escape** — `fully_processed` written even when finality is pending (`sync.py:1302-1360`: non-final boxscore lines still ingest and mark), and `failed` after 3 attempts is never retried; MLB data arriving late (>3 passes) is permanently lost absent the (dead) daily net.
6. **Fail-closed deactivation feeds fail-open ingestion** — `team_assignment_sync` can set `active=False` on ambiguous roster evidence; the daily lane then never fetches that pitcher's logs; call-ups don't exist until a postgame boxscore creates them. If postgame misses their debut, they're invisible.
7. **Partial = success** — `partial` publishes snapshots and counts as fresh (`sync_metadata.py:45`); dead-letters rot with no replay.
8. **Missing appearances bias availability upward** — rest-days overcount; `data_state` stays `fresh` if any log is within 14 days (`availability.py`); fatigue `score_rest_days(None)=0` (fully rested). The failure direction is the trust-damaging one.
9. **Timeout kills are silent** — `timeout(1)` SIGTERM has no handler; the SyncRun row is reclaimed later as failed, but no alerting distinguishes "timed out mid-ingest" from "failed at start". Internal-enrichment timeouts (Jul 7, Jul 8) already demonstrate the pattern.
10. **Cron/DST assumption** — 10:00 UTC daily is documented; postgame 02/04/06 UTC covers evening games only through ~2 AM ET; a >2 AM ET finish (long extras, resumed game) relies entirely on the (dead) daily net.

## 7. Blast Radius

- **Appearance rows**: all pitching lines in July 4 games finishing after ~23:01 ET — order of 50–70 rows across ~10–14 teams (exact list requires prod DB / MLB API; see ledger audit, §8/§5-audit-command).
- **Stat corrections**: zero corrections applied league-wide since July 4 (`logs_corrected: 0` every run; postgame re-marks games `fully_processed` and never re-reads them). Revised pitch counts/IP from MLB are not flowing.
- **Derived state**: 7-day workloads wrong through July 11, 14-day through July 18 for affected pitchers; availability biased toward Available; fatigue scores computed on incomplete windows; team bullpen state, boards, Tonight cards, stories, what-changed, completed-game contexts and play-by-play foundations missing for the unprocessed games; static OG pages baked from the same data.
- **Pitchers created late**: any MLB debut in the missed games didn't get a Pitcher row until their next postgame-processed appearance.
- **Trust surfaces**: freshness/`data_through` claims "through July 7/8" while July 4 is incomplete — an *incorrect completeness implication*, the exact fail-closed violation the product forbids.

## 8. Recommended Integrity Gates

1. **Appearance-ledger publish gate (fail-closed)**: before any snapshot publish, for each of the trailing N=10 product dates compute: `scheduled_finals(date)` (non-postponed ScheduledGame finals) vs `postgame fully_processed markers(date)` vs `distinct game_pks in game_logs(date)`. Any date with `finals > processed` or `finals > distinct game_log games` ⇒ publish degraded (serve previous snapshot + explicit "data gap on <date>" freshness flag) and emit a dead-letter per missing game. This one gate would have caught July 4 within hours.
2. **Ingestion-liveness gate**: daily sync must assert `splits_seen > 0` and `(inserted + corrected + unchanged) > 0` during the season; if 100% of splits skip as `not_completed`, fail the run loudly (this is a canary for the dead-lane class of bug).
3. **Latest-appearance reconciliation** (external truth): nightly job compares, per active pitcher, `MAX(game_date)` in `game_logs` vs the pitcher's latest MLB gameLog split date; any mismatch older than 1 day ⇒ report + block "fresh" labeling. (Extends the existing `run_reconciliation_audit.py` scaffolding.)
4. **Skip-reason telemetry**: `sync_recent_logs` returns counts per skip reason (`not_completed`, `before_cutoff`, `missing_key`) in the summary JSON so Actions logs make silent filtering visible.

## 9. Recommended Fix Plan (minimal, ordered)

1. **Fix the daily-lane gate** (one function): in `_ingest_game_log_split`, when the split's `game` object has *no* status block, resolve finality from `scheduled_games` (`status_state == 'final'` for that game_pk) — the table is already ingested ±10 days daily — instead of treating absence as non-final. Keep skipping splits whose *resolved* status is live/postponed/suspended. If unresolvable, dead-letter (`game_log_record`) instead of silent skip. (Alternative considered and rejected as riskier: trusting all statusless splits — reintroduces the live-game ingestion problem `552fcb8` was fixing.)
2. **Postgame lookback**: change postgame refresh to sweep `[schedule_date - 2, schedule_date]` (or all dates in the last 7 with `finals > fully_processed markers`), so a crashed night self-heals on the next pass.
3. **Backfill the hole**: run `python backend/scripts/run_postgame_refresh.py --date 2026-07-04 --source manual_backfill` (the `--date` flag exists) after 1–2 land; verify with the ledger audit. Also sweep Jul 5 for stragglers.
4. **Ledger gate** (§8.1) wired into `publish_dashboard_snapshot`.
5. **Mapper hardening**: sync entrypoints import `models` package wholesale (or call `db.configure_mappers()` at startup) with a smoke test, so a model-registry regression fails CI, not the 2 AM production pass.
6. Later (separate PRs): marker `failed` re-arm policy; skip-reason telemetry; `partial` semantics review.

## 10. Tests Required

1. `test_daily_ingestion_resolves_statusless_split_via_scheduled_game` — statusless split + final ScheduledGame row ⇒ inserted; + live/suspended row ⇒ skipped; + no row ⇒ dead-lettered (replaces the current silent-exclusion expectation in `test_unknown_safe_ingestion.py:255`).
2. `test_daily_sync_fails_loudly_when_all_splits_skip` — in-season run where every split skips ⇒ run status failed/partial with explicit reason.
3. `test_postgame_lookback_recovers_missed_slate` — day D processed 8/15, passes for D crash; pass on D+1 sweeps D and processes the remaining 7.
4. `test_ledger_gate_blocks_publish_on_trailing_hole` — finals(D-3) > game_log games(D-3) ⇒ snapshot withheld, previous snapshot served, freshness flags the gap.
5. `test_ledger_gate_allows_publish_on_postponed_and_suspended` — postponed/suspended/resumed-linkage games don't false-positive the gate.
6. `test_stat_correction_flows_through_daily_lane` — existing row + revised MLB stats in a final statusless split ⇒ `corrected` with provenance bump (regression for the dead correction lane).
7. `test_mapper_registry_smoke` — instantiating each sync entrypoint (`run_daily_sync.py`, `run_postgame_refresh.py`) configures all mappers (`db.configure_mappers()`) without error.
8. Marker lifecycle: `test_failed_marker_rearmed_by_ledger_audit` (once re-arm policy exists).

## 11. Production Verification Plan

1. **Quantify the hole (read-only)**: run the ledger audit SQL against prod for Jul 1–8: per date, scheduled finals vs distinct `game_logs.mlb_game_pk` vs `postgame_processed_games` markers. Expect a deficit only on 2026-07-04.
2. **Confirm Natera**: `SELECT * FROM game_logs gl JOIN pitchers p ON p.id = gl.pitcher_id WHERE p.mlb_id = 696519 AND gl.game_date >= '2026-07-01'` — expect July 2 as max; confirm no `sync_failures` row references him.
3. Deploy fixes 1–2, then trigger a manual `workflow_dispatch` postgame with `--date 2026-07-04` (or run the script directly) and re-run the ledger audit — deficit should go to zero; Natera's July 4 row appears; fatigue/availability recompute on the next pass; next snapshot's team boards reflect it.
4. Verify daily lane liveness next morning: summary JSON shows nonzero `unchanged`/`corrected` counts and per-reason skip counts.
5. Spot-check 3 affected pitchers' Pitcher Detail against MLB.com; confirm `last_workload_appearance` matches.
6. Watch one full cron cycle (02/04/06/10 UTC) for green runs and `postgame_retry_exhausted: 0`.

## 12. Branch Plan

- `claude/baseballos-sync-audit-qvnw0s` (this branch): audit report only — no code changes.
- `fix/daily-gamelog-finality-resolution`: fix §9.1 + tests 1, 2, 6 (small, urgent).
- `fix/postgame-lookback-window`: §9.2 + test 3 (small, urgent; independent).
- `feat/appearance-ledger-gate`: §8.1/§9.4 + tests 4, 5 + `scripts/run_appearance_ledger_audit.py` report command (medium).
- `fix/sync-runtime-mapper-smoke`: §9.5 + test 7 (tiny).
- Backfill is an ops action (existing script), not a branch.
- Suggested follow-ups, lower priority: `feat/sync-trace-debug-mode` (`scripts/sync_trace.py --player 696519 --date 2026-07-04`: prints schedule row → finality classification → marker state → boxscore line presence → game_log row → aggregation window membership → snapshot inclusion, one line per hop), dead-letter replay command, marker re-arm policy.

## 13. Open Questions / Blockers (evidence gaps, flagged assumptions)

1. **Cannot reach statsapi.mlb.com or the production API/DB from this audit environment** (network policy 403s). Therefore: (a) player id 696519 is sourced from BaseballOS's own artifact, not re-verified against MLB; (b) the exact July 4 LAA@BOS game_pk, its finish time, and Natera's line in its boxscore are unverified externally; (c) the precise count/list of missed July 4 games needs the §11.1 ledger query. None of these change the mechanism, which is proven from run logs + code.
2. **The real gameLog `game` object lacking `status` is inferred**, not observed from a live API call in this audit. Support: the author's own test encodes statusless splits; four consecutive production dailies post-gate show `new_logs_added: 0, logs_corrected: 0` while a known 7-day-window hole existed; the pre-gate July 3 summary JSON lacks the `logs_corrected` key entirely (field shipped with the gate). A one-line prod check (log one raw split) settles it definitively.
3. Which specific commit introduced the `EvidenceObject` mapper breakage (candidates: composed-read model changes merged between Jul 4 22:56 ET and Jul 5 01:17 ET; fixed by `6c7297f`) — matters only for the CI-smoke-test design, not the remediation.
4. Whether any July 5 games were also missed (Jul 5 16:46–23:38 ET manual runs mostly failed; Jul 6 03:02 pass succeeded for the Jul 5 slate — likely healed, but the ledger query should include Jul 5).
5. `4 record(s) dead-lettered` in the Jul 8 daily (transaction-identity failures) — unrelated to appearances but should be triaged via the dead-letter report since nothing replays them.
