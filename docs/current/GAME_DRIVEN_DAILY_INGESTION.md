# Game-Driven Daily Appearance Ingestion (Foundation 3C)

Canonical reference for the daily publication-critical appearance lane: how the
work plan is built, how games are fetched and reconciled, how the durable
checkpoint resumes an interrupted run, how corrections are rediscovered, and
how publication completeness is proven.

Related: [`SYNC_PIPELINE.md`](SYNC_PIPELINE.md) (execution order and trust
gates) · [`DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md`](DAILY_SYNC_PUBLICATION_CRITICAL_CONTRACT.md)
(publication-critical vs best-effort) ·
[`PITCHER_SEASON_LEDGER_COVERAGE.md`](PITCHER_SEASON_LEDGER_COVERAGE.md).

## Why the pipeline changed

A read-only production diagnostic (reference date 2026-07-29, run against the
live database with `SET TRANSACTION READ ONLY`, an active write probe, and
before/after table fingerprints) measured the daily lane and found the cost was
structural, not incidental:

| Measurement | Value |
|---|---|
| `Pitcher.active` rows selected daily | 854 |
| Classified publication-critical by roster code | 419 |
| Active starters with **zero** relief appearances in the lookback | 139 of 139 |
| Active-roster **non-pitchers** selected | 13 |
| Mixed/unknown-role rows without a recent relief appearance | 24 of 36 |
| Full-season splits returned across 60 sampled requests | 1,080 |
| Splits actually inside the governed window | 70 |
| Median relevant ratio | 4.44% |
| Sampled requests that were no-change work | 60 of 60 (100%) |
| Share of measured time spent on the external request | 1.626952s of 1.629795s |

Local parsing, filtering, and comparison together accounted for 0.002053s. The
bottleneck was never the code — it was **the unit of work**. Asking "what did
every active pitcher do all season?" is the wrong question when the thing that
actually changed is "which games went final since the last run?"

## Old pipeline (retired from the critical path)

```
Pitcher.query.filter_by(active=True).all()      854 rows
        |
        v
for each pitcher: GET /people/{id}/stats?stats=gameLog&season=…    854 requests
        |                                                          ~94% waste
        v
filter locally to the 7-day window
        |
        v
compare locally against stored rows                    100% no-change, typical
        |
        v
budget exhausted  ->  dead-letter the remaining tail
        |
        v
next run restarts from the first pitcher
```

## New pipeline

```
                schedule + finality authority
                 (scheduled_games, services/game_finality.py)
                             |
                             v
                    discover candidate games
                             |
                             v
              classify candidate reason (explicit)
      newly_final · finality_changed · corrected_final
      incomplete_prior_attempt · explicit_repair · backfill
                             |
                             v
                  deterministic work plan (ordered)
                             |
                             v
              fetch canonical game evidence ONCE
                (existing MLB client, existing boxscore path)
                             |
                             v
                extract pitcher appearances
              (services/game_appearance_extraction.py)
                             |
                             v
           classify relief vs start PER APPEARANCE
              (official per-game gamesStarted signal)
                             |
                             v
          reconcile canonical GameLog rows (idempotent)
                             |
                             v
                 verify game completeness
             (expected rows == reconciled rows)
                             |
                             v
        mark game work complete  ──┐ same transaction
        advance the checkpoint   ──┘
                             |
                             v
            evaluate publication completeness
          (services/game_ingestion_completeness.py)
                             |
                             v
                    publish or withhold
```

Cost now scales with **games that changed** (~15/day in season), not with the
pitcher universe.

## Work-planning contract

`services/game_ingestion_planner.py::plan_game_work(reference_date)`.

The plan is derived from `scheduled_games` plus the canonical finality
authority. It **never** reads `Pitcher.query.filter_by(active=True)` — enforced
structurally by a test that parses the planner's AST and asserts the Pitcher
model is not imported.

Each work item carries: `game_pk`, `represented_date`, `game_date`,
`game_datetime`, `home_team_id`, `away_team_id`, `game_type`, `finality_state`,
`candidate_reason`, `criticality`, `source_authority`, `prior_status`,
`prior_source_revision`, `attempt_count`, and a deterministic `ordering_key`.

Deterministic order (never database default row order):

1. incomplete prior critical work
2. publication-critical before best-effort
3. oldest unresolved represented date
4. game start time (unknown start times sort last, stably)
5. game identifier

### Horizons

| Horizon | Default | Env override | Why |
|---|---|---|---|
| Ingestion | 7 days | `GAME_INGESTION_HORIZON_DAYS` | Exactly the `--days-back 7` window the retired pitcher loop covered — equal coverage, not reduced. |
| Correction | 7 days | `GAME_INGESTION_CORRECTION_HORIZON_DAYS` | The pitcher loop re-read its whole 7-day window every day, so re-checking final games for 7 days is the same correction reach at a fraction of the cost. |

Unresolved work has **no horizon**. An incomplete work item of any age is
always re-planned first, so a game interrupted mid-run can never be permanently
skipped because the window moved past it.

## Game eligibility

A game enters the publication-critical lane when it is inside the horizon, is
final by canonical authority, and is either not yet reconciled at its current
source revision or carries an incomplete prior attempt.

| Source state | Handling |
|---|---|
| Final (both sides agree) | planned |
| Final after suspension, linkage resolved | planned at its **original** product date |
| Suspended, or unresolved resumed linkage | excluded, retried later — never partially completed |
| Postponed | excluded, counted explicitly |
| Cancelled / other terminal non-final | excluded, counted explicitly |
| Scheduled / in progress | excluded, counted explicitly |
| Doubleheader | two independent `game_pk` work items |
| One side final, the other not | **finality conflict — fails closed and withholds** |
| No schedule rows for unresolved critical work | **schedule authority missing — fails closed and withholds** |

Every discovered game is accounted for exactly once: planned, or excluded with
a named reason. A test asserts that reconciliation.

## Appearance extraction

`services/game_appearance_extraction.py`. One final game payload in, a
deterministic appearance set out. It owns the appearance shape and the
game-level role decision; it does **not** own box-score parsing or MLB
transport — the single existing parser
(`services.sync._extract_pitching_lines_from_boxscore`) and the single existing
MLB client are reused unchanged.

Each record carries: `game_pk`, `pitcher_mlb_id`, `team_id`,
`opponent_team_id`, `game_date`, `appearance_role`, `is_starter`,
`is_reliever`, `games_started`, `outs_recorded`, `innings_pitched`,
`earned_runs`, `runs_allowed`, `hits_allowed`, `walks`, `strikeouts`,
`home_runs_allowed`, `batters_faced`, `pitches_thrown`, `source_authority`.

### Where game-level role overrides season-level role

Role is decided **per appearance** from the official per-game `gamesStarted`
signal (with the existing "first pitcher listed for this side" fallback):

* `games_started == 1` → this appearance is a **start**
* otherwise → this appearance is **relief**

Season role and roster role are never consulted. A pitcher whose season role is
SP is a reliever for the appearance he entered in relief, and a pitcher whose
roster role is RP is a starter for the appearance he started. This is the same
signal Role Authority V1 is built on (`GameLog.games_started`), so no second
role heuristic is introduced. An **opener** is officially credited with the
start and therefore records a start appearance; the bulk arm behind him records
a relief appearance.

Extraction fails closed — a duplicate pitching line for one pitcher, an
unidentifiable pitcher, an unparsable innings value, or a final game with no
pitching appearances at all raises a classified error and the game is not
completed.

## Publication-critical scope change

The old contract classified work by the pitcher's **roster code**. Production
showed what that cost: 139 active starters with zero relief appearances, 13
active-roster non-pitchers, and 24 mixed/unknown-role rows were all called
publication-critical and were each given a full-season request.

Criticality is now a property of the **game**:

* a governed final game inside the represented-date horizon is
  publication-critical — its appearances *are* the bullpen evidence;
* everything older is best-effort backfill;
* a game whose represented date cannot be established fails closed to unknown;
* unresolved work that was critical stays critical; work that was best-effort
  to begin with stays best-effort and can never withhold publication.

Because one fetch yields the whole game, every appearance in a governed final
game is reconciled — including an IL, optioned, or forty-man-not-active arm
that actually pitched. Roster movement no longer decides whether an appearance
is ingested; game evidence does.

`services/publication_criticality.py::criticality_for_roster_status` is
**retained**, not deleted. It still orders the best-effort repair lane. What
changed is what it governs: publication completeness is now driven by relevant
game coverage.

## Idempotent persistence

The canonical natural key is unchanged: `(pitcher_id, mlb_game_pk)`, enforced by
`uq_game_logs_pitcher_game`. One pitcher has exactly one pitching line per MLB
game; the extractor rejects a payload that claims otherwise rather than picking
one silently.

| Situation | Result |
|---|---|
| First processing | rows inserted, work item completed |
| Replay of an unchanged completed game | zero duplicates, zero false changes, explicit no-op |
| Corrected game | governed fields reconciled, `correction_count` incremented, work item stays completed |
| Partial write then failure | whole transaction rolls back; the work item is **not** completed |
| Duplicate source rows | rejected as `payload_invalid` |
| Suspended game completed later | reconciled at its original represented date |

Writes go through the existing
`services.sync.process_completed_game_for_postgame_refresh`, so the same
correction-safety checks, the same appearance-team authority (Foundation 1), and
the same integer-outs innings authority apply. That function gained one
parameter — `force` — which bypasses **only** the fully-processed short-circuit,
because this lane owns its own completion contract and must be able to re-read a
game inside the correction horizon. Every write it performs stays idempotent.

## Durable checkpoint and resume

Table: `game_ingestion_work_items` (one row per `mlb_game_pk`).

```
                   ┌──────────┐
      planned ────▶│ in_progress │────▶ completed
         ▲         └──────────┘            │
         │              │                  │ re-planned inside the
         │              │                  │ correction horizon
         │              ▼                  ▼
         │      retryable_failure ──▶ terminal_failure
         │              │              (retry limit reached,
         └──────────────┘               dead-lettered once)
        budget stop leaves
        remaining work `planned`
```

`superseded` exists for a work item whose game was replaced by canonical
authority; it resolves the item without claiming it was reconciled.

Two invariants are enforced **at the database**, not by writer discipline:

* the status, criticality, and candidate-reason vocabularies are closed sets;
* a row may only be `completed` when it carries a completion timestamp, a
  determined `rows_expected`, and `rows_reconciled = rows_expected` — so an
  optimistic or miscounted writer cannot fabricate completeness.

The checkpoint write is in the **same transaction** as the game's appearance
writes. A game whose writes roll back is never marked complete.

On interruption: completed games stay completed, unresolved games stay
resumable, the next run begins with unresolved critical work, and no tail is
dead-lettered merely because the budget was reached.

## Execution budget

Existing production budgets are unchanged (`DAILY_SYNC_TOTAL_BUDGET_SECONDS`
1080, ingestion cap 720, `FINAL_PHASE_RESERVE` 300). Nothing here raises a
timeout.

At the budget threshold the lane stops intake, finishes or rolls back the
current game transaction, persists the remaining work as resumable `planned`
items, marks the run incomplete, and — if critical games remain — withholds
publication.

**Budget exhaustion is not a terminal dead-letter condition. It is an
incomplete, resumable run state.**

Budget split while the lane is not yet publication-authoritative: it runs inside
a bounded share of the ingestion budget (`GAME_DRIVEN_INGESTION_BUDGET_SHARE`,
default 0.25) so Stage B/C production evidence can be gathered without
endangering the loop that is still authoritative. Once authoritative it *is* the
critical lane and may use the whole ingestion budget; whatever it does not use
falls through to the demoted best-effort loop.

## Correction detection

MLB publishes no boxscore revision number, so none is invented. Two real
signals are used:

1. **Observed appearance-set fingerprint** — a SHA-256 over the canonical
   extracted fields (`pitcher_mlb_id`, `team_id`, `opponent_team_id`,
   `appearance_role`, `games_started`, `outs_recorded`, `earned_runs`,
   `runs_allowed`, `hits_allowed`, `walks`, `strikeouts`, `home_runs_allowed`,
   `batters_faced`, `pitches_thrown`). Identical official lines fingerprint
   identically; any governed field changing produces a different fingerprint.
   Cosmetic payload churn (display names, ordering, unrelated hydrations)
   deliberately does not.
2. **Bounded correction horizon** — 7 days, matching the retired lane's daily
   re-read window, so correction reach is unchanged.

The season is never re-fetched to detect corrections. Roughly 15 games/day × 7
days ≈ 105 game fetches bound the whole correction sweep, versus 854
full-season pitcher requests.

**Effect on published snapshots:** a correction reconciled inside the horizon
updates canonical `game_logs` and increments the work item's
`correction_count`; the correction provenance columns
(`stat_correction_count`, `last_stat_correction_at`,
`last_stat_correction_source`, `last_stat_correction_sync_run_id`) are written
by the existing governed upsert, so published evidence stays traceable.
Already-published immutable artifacts are not rewritten — the next candidate
snapshot is built from the corrected ledger. A correction that **cannot** be
applied safely becomes a `correction_conflict`, leaves the work item unresolved,
and withholds publication.

## Publication completeness proof

`services/game_ingestion_completeness.py::build_game_ingestion_completeness(D)`
returns explicit proof fields:

`represented_date`, `expected_final_games`, `completed_final_games`,
`unresolved_final_games`, `terminal_failure_games`, `correction_pending_games`,
`corrected_games_reconciled`, `critical_appearance_rows_expected`,
`critical_appearance_rows_reconciled`, `finality_conflicts`,
`schedule_authority_missing`, `best_effort_games_planned`,
`publication_complete`, `decision_reasons`.

`publication_complete` is True only when every listed condition holds. Reason
codes: `unresolved_final_games`, `critical_game_failure_unresolved`,
`terminal_critical_game_failure`, `finality_conflict_unresolved`,
`schedule_authority_missing`, `critical_appearance_rows_unreconciled`,
`material_correction_pending`, or `game_ingestion_complete`.

`critical_appearance_rows_reconciled` credits only rows that are **both** proven
by the work item **and** still present in the appearance ledger, so a work item
cannot claim completeness for rows that later disappeared.

This is an additional, more precise input to the same publication-critical
contract — no existing gate (finality, appearance ledger, freshness,
provenance, slate coverage) is weakened.

## Failure semantics

Every failure declares, in one place
(`services/game_driven_ingestion.py::FAILURE_SEMANTICS`), whether it is
retryable, whether it blocks checkpoint advancement, and whether it blocks
publication. Nothing is reduced to an opaque dead-letter count.

| Class | Retryable | Blocks checkpoint | Blocks publication |
|---|---|---|---|
| `schedule_authority_missing` | yes | yes | yes |
| `finality_unresolved` | yes | yes | yes |
| `game_fetch_failed` | yes | yes | yes |
| `payload_invalid` | yes | yes | yes |
| `starter_identity_unresolved` | yes | yes | yes |
| `appearance_extraction_failed` | yes | yes | yes |
| `persistence_failed` | yes | yes | yes |
| `reconciliation_failed` | yes | yes | yes |
| `correction_conflict` | yes | yes | yes |
| `budget_exhausted` | yes (always) | yes | yes |
| `unexpected_error` | yes | yes | yes |

Retries are bounded at 3 attempts, after which the work item becomes
`terminal_failure` and is dead-lettered **once**, with the safe class and the
game id — never the exception text. `budget_exhausted` is exempt from the retry
limit because it is not a failure of the game.

## Observability

Run-level: `planner_seconds`, `games_discovered`, `newly_final_count`,
`corrected_final_count`, `retry_count`, `games_fetched`, `fetch_seconds`,
`extraction_seconds`, `persistence_seconds`, `checkpoint_seconds`,
`rows_inserted`, `rows_updated`, `rows_unchanged`, `games_completed`,
`games_remaining`, `critical_games_unresolved`, `best_effort_games_deferred`,
`budget_stop_triggered`, `failure_classes`, plus the completeness proof's
`publication_complete` and `decision_reasons`.

Per game: `game_pk`, `represented_date`, `candidate_reason`, `criticality`,
`attempt_number`, `status`, `source_revision`, `appearances_extracted`,
`relief_appearances`, `inserted`, `updated`, `unchanged`, `elapsed_seconds`,
`error_class`.

Never logged: credentials, connection strings, headers, raw source payloads, or
complete exception messages. Failures are reported by safe class only.

## Best-effort lane

The full-season-per-pitcher loop (`services/sync.py::sync_recent_logs`) is
retained as the governed repair mechanism it is genuinely good at: historical
backfills, full-season pitcher audits, missing roster history, IL and optioned
reconciliation, operator-triggered repair, and corrections older than the
correction horizon.

Once the game lane is authoritative the daily sync calls it with:

* `best_effort_only=True` — every item is reported best-effort, so a shortfall
  defers repair work and can never withhold the public snapshot;
* `skip_game_pks=<games the game lane completed this run>` — the **explicit
  conflict-prevention mechanism** required before two writers may exist. The
  demoted loop never rewrites a game the authoritative lane just reconciled, so
  two writers never touch the same canonical rows.

It runs after the critical lane, inside whatever ingestion budget remains, and
never consumes the critical lane's reserve.

## Rollout

| Stage | `GAME_DRIVEN_INGESTION_MODE` | What it does | Publication authority |
|---|---|---|---|
| — | `off` (deployed default) | nothing | old pitcher loop |
| A | `off` + operator `--plan-only` | plan only, no MLB request, no write | old pitcher loop |
| B | `shadow` | plan, fetch, extract, project insert/update/no-op | old pitcher loop |
| C | `write` | reconcile and checkpoint for real | old pitcher loop |
| D | `authoritative` | as C, and the game-level proof drives publication | **game lane** |
| E | cleanup | remove the temporary diagnostic workflow, retire obsolete critical-path dead-letter behaviour | game lane |

The default is `off`, so merging this changes nothing in production until the
mode is advanced deliberately, one stage at a time, on evidence.

## Operator repair procedure

```bash
# Stage A — shadow plan. No MLB request, no write.
python scripts/game_driven_ingestion.py --plan-only

# Stage B — shadow reconciliation. Fetches games, writes nothing.
python scripts/game_driven_ingestion.py --mode shadow

# Stage C — controlled write, bounded.
python scripts/game_driven_ingestion.py --mode write --max-games 5

# Governed repair of specific games (planned as explicit_repair).
python scripts/game_driven_ingestion.py --mode write --game-pk 776543

# Historical backfill (best effort, never automatic).
python scripts/game_driven_ingestion.py --mode write --include-backfill \
    --time-budget-seconds 300
```

Output is one JSON document containing counts, timings, safe error classes, and
the publication completeness proof. Exit 0 = complete, 1 = incomplete or a game
failed, 2 = the tool itself could not run.

## Migration and rollout seeding

`b9d4e17c3a80_add_game_ingestion_work_items` is forward-only and purely
additive: one new table, no existing table altered, no existing row modified, no
`game_logs` rewritten, no backfill.

**Seeding strategy: none.** An empty table means "no game has been proven
complete by this lane yet", which fails closed — the completeness proof reports
unresolved final games until the lane has actually run. Marking historical
games complete at deploy time would create exactly the false completeness the
proof exists to prevent. The lane earns its checkpoint by doing the work, inside
the correction horizon, on its first authoritative runs.

## Retirement status of the all-pitcher critical loop

| | Status |
|---|---|
| Daily publication-critical path | **Retired** once the mode is `authoritative` |
| Governed best-effort repair | **Retained**, explicitly labelled, bounded, resumable |
| Operator backfill / audit | **Retained** |
| Ability to withhold publication | **Removed** — it reports best-effort only |
