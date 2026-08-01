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

## Shadow/write parity — why it is mandatory

A projection that can disagree with the writer is worse than no projection: it
authorizes a rollout stage on evidence that does not describe what will happen.

That is not hypothetical. A controlled Stage C production run on 2026-07-29
found it:

| | shadow projected | write applied |
|---|---|---|
| games | 5 | 5 |
| appearance rows | 38 | 38 |
| inserts | 0 | 0 |
| **updates** | **0** | **14** |
| unchanged | 38 | 24 |

Per game, the writer applied 4, 2, 4, 2, and 2 updates that shadow had reported
as unchanged. The writes were transactionally clean and all 38 rows reconciled
— the defect was in the *prediction*, not the write.

**Root cause.** Shadow owned its own comparator: eight fields
(`innings_pitched_outs`, `earned_runs`, `runs_allowed`, `hits_allowed`,
`walks`, `strikeouts`, `home_runs_allowed`, `games_started`) drawn from the
*extracted appearance* vocabulary. The canonical writer reconciles the far
broader *governed record* built by `sync._game_log_values_from_stats`, and
additionally reconciles team-at-appearance authority outside that field loop.
Every field in the gap could produce a write the projection could not see:

`game_date`, `game_type`, `innings_pitched`, `pitches_thrown`, `strikes`,
`opponent`, `opponent_abbreviation`, `batters_faced`, `balls`,
`games_finished`, `inherited_runners`, `inherited_runners_scored`,
`save_situation`, `hold`, `blown_save`, `win`, `loss`, `save`,
`leverage_index`, and the four `appearance_team_*` columns.

Two further gaps compounded it: shadow skipped a field whenever the extracted
record carried `None`, while the writer compares a computed value (a missing
optional stat becomes `0`, so a stored `NULL` *is* a change); and shadow never
evaluated correction safety at all, so an ungoverned correction projected as a
safe update instead of a blocked one.

## Canonical reconciliation plan

Adding the missing fields to the projection would have preserved two
authorities and let them drift again. There is now exactly one.

```
official game evidence
        |
        v
canonical extracted appearances
        |
        v
services/game_log_reconciliation.py::plan_row      <-- THE decision
        |
   +----+----+
   |         |
 shadow    write
 reports   applies
 the plan  the plan
```

`plan_row` is pure: it reads the stored row and the governed values and returns
a deterministic, serializable plan. It performs no writes and mutates nothing.
Applying a plan happens in exactly one place —
`sync._upsert_game_log_from_authoritative_values`.

Each plan entry carries `game_pk`, `pitcher_mlb_id`, `local_pitcher_id`, the
natural key, the `action`, `changed_fields`, `field_changes` (safe
before/after for governed baseball fields only), `mutation_categories`,
`appearance_team_reason`, `blocked_reason`, `unresolved_reason`,
`pitcher_identity_action`, and the source authority.

**Actions:** `insert`, `update`, `unchanged`, `blocked`.

### What can cause an update

| Category | Fields |
|---|---|
| `official_statistical_correction` | `innings_pitched`, `innings_pitched_outs`, `pitches_thrown`, `strikes`, `hits_allowed`, `runs_allowed`, `earned_runs`, `walks`, `strikeouts`, `home_runs_allowed`, `batters_faced`, `balls`, `games_finished`, `inherited_runners`, `inherited_runners_scored`, `save_situation`, `hold`, `blown_save`, `win`, `loss`, `save`, `leverage_index` |
| `role_or_starter_signal_reconciliation` | `games_started` |
| `game_metadata_reconciliation` | `game_date`, `game_type`, `opponent`, `opponent_abbreviation` |
| `appearance_team_authority_reconciliation` | `appearance_team_id`, `appearance_team_source`, `appearance_team_status`, `appearance_team_reason` |
| `provenance_only_update` | `stat_correction_count`, `last_stat_correction_at`, `last_stat_correction_source`, `last_stat_correction_sync_run_id` |
| `pitcher_identity_reconciliation` | a pitcher the writer would create, reactivate, or re-attribute |
| `unchanged_row` | — |
| `unsafe_or_blocked_mutation` | an ungoverned correction, or an unresolvable pitcher identity |

A field that reaches the writer without a category is classified `blocked`, so
a new governed column cannot silently become an unclassified mutation.

The provenance stamp is applied only alongside a genuine field correction, so
in the current writer a *provenance-only* update is unreachable and its count
is legitimately zero. The category exists and is separable so such a mutation
could never be misreported as an official statistical correction.

### How shadow's read-only behaviour is proven

Shadow does not write-and-roll-back. It calls the canonical writer's planning
mode, `process_completed_game_for_postgame_refresh(plan_only=True)`, which is
logically read-only *before* any transaction handling:

* no GameLog is inserted or corrected;
* no pitcher is created, reactivated, or re-attributed —
  `resolve_pitcher_for_authoritative_line(plan_only=True)` runs the identical
  guard chain and reports `would_create` / `would_reactivate` instead;
* no postgame marker is upserted;
* no failure is dead-lettered.

A test asserts this with before/after content fingerprints across `game_logs`,
`pitchers`, `game_ingestion_work_items`, `postgame_processed_games`, and
`scheduled_games` — including correction counters, authority provenance, and
timestamps.

### The parity contract

For a mixed fixture containing an insert, an update, an unchanged row, and a
blocked row, a test generates the shadow plan, runs write from the identical
initial state, and asserts exact equality of actions, natural keys, changed
fields, mutation categories, the four action counts, and the plan fingerprint.
A regression fixture reproduces the production shape — 38 rows across five
games, 14 of which differ only outside the retired comparator — and requires
the projection to predict all 14 updates before any write.

## Canonical innings semantics (D-008 enforcement)

D-008 is a permanent data rule: **integer recorded outs are the semantic
innings authority; decimal innings are derived.** Production validation found
the reconciliation planner violating it.

### What production showed

Full-window shadow, reference date 2026-07-29:

| | |
|---|---|
| games attempted / completed / failed | 109 / 109 / 0 |
| rows expected | 946 |
| rows inserted / updated / unchanged / blocked | 0 / 325 / 621 / 0 |
| changed fields | `innings_pitched` 323, `earned_runs` 4, `hits_allowed` 4 |

And on the five games a controlled write had **already reconciled** — 38 rows,
14 updated, 24 unchanged in that write — a replay still projected **14 updates
and 24 unchanged**, every one of the 14 carrying exactly one changed field:
`innings_pitched`. No outs change, no earned runs, no hits, no authority, no
role, no metadata, nothing blocked.

A write that has been applied must replay to zero changes. This one never
converged: repeating it would re-apply the same non-correction and increment
`stat_correction_count` again, every time.

### Root cause

The planner's correctable-field vocabulary listed `innings_pitched` as an
independently compared field. The comparison was `stored float != freshly
derived float`. Those can differ in representation while describing the same
canonical outs, so the planner classified representation drift as an
`official_statistical_correction`, scheduled provenance, and applied the
derived float — after which the next comparison could differ again.

The stored companion is bounded: `ck_game_logs_innings_pitched_matches_outs`
requires it within 1e-6 of `outs / 3.0`. So the only drift reachable is float
representation — there is no population of materially wrong decimals this path
was usefully "repairing".

### The rule as implemented

Innings is **one semantic field family**:

| | field |
|---|---|
| semantic authority | `innings_pitched_outs` |
| derived companion | `innings_pitched` |

* **Insert** — official notation is parsed once into canonical outs; the
  companion is derived from those outs. A source float is never trusted.
* **Stored outs equal official outs** — any difference in the companion is
  ignored entirely. Not an update, not a changed field, not a statistical
  correction, no provenance stamp, no counter increment, no published-evidence
  flag, no fingerprint change. The companion is not rewritten just to
  normalize its representation.
* **Stored outs differ from official outs** — one semantic correction on
  `innings_pitched_outs`, the companion re-derived from the corrected outs,
  both applied in one row update, one provenance event, and the replay is
  unchanged.

A plan therefore distinguishes:

```
semantic_changed_fields    what the official record says changed
applied_changed_fields     what the writer actually writes
derived_companion_fields   companions written because their authority moved
derived_companion_differences_ignored
                           representation drift that is NOT a change
```

`changed_fields` — the field the reports and the fingerprint use — is the
**semantic** set. `innings_pitched` never appears in it.

Legitimate corrections are untouched: earned runs, runs, hits, walks,
strikeouts, home runs, pitches, strikes, batters faced, role signal,
appearance-team authority, and game metadata all behave exactly as before. A
row with equal outs but changed earned runs is still updated; a row with both
changed produces one update and one provenance event.

### Fingerprint semantics

The reconciliation-plan fingerprint covers action, natural key, semantic
changed fields, mutation categories, and a **mutation digest** of the values
the plan would write. That last part matters: without it, an insert of one
earned run and an insert of seven fingerprint identically, and a reviewed
fingerprint would authorize a different mutation than the one reviewed.

Excluded from the digest, deliberately: derived companions (so representation
cannot move the fingerprint), provenance columns (stamped by the act of
correcting, not reviewed as evidence), and the local `pitcher_id` surrogate (a
projection cannot know the key a not-yet-created pitcher will receive).

Nothing unstable — no timestamps, object ids, exception text, or runtime
ordering — is in the fingerprint.

### Innings accounting in the report

`canonical_outs_corrections`, `derived_companion_fields_applied`,
`derived_companion_differences_ignored`, `decimal_only_updates_suppressed`,
and `innings_semantics_version`. Ignored differences are counted **once per
row**, so a row that both drifted and changed for a real reason is never
double-counted.

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
`rows_expected`, `rows_inserted`, `rows_updated`, `rows_unchanged`,
`rows_blocked`, `changed_fields_counts`, `mutation_category_counts`,
`statistical_corrections`, `authority_reconciliations`,
`provenance_only_updates`, `games_completed`, `games_remaining`,
`critical_games_unresolved`, `best_effort_games_deferred`,
`budget_stop_triggered`, `failure_classes`, `parity_contract_version`,
`reconciliation_plan_version`, `reconciliation_plan_fingerprint`, plus the
completeness proof's `publication_complete` and `decision_reasons`.

Per game additionally: `blocked`, `changed_fields_counts`,
`mutation_category_counts`, `statistical_corrections`,
`authority_reconciliations`, `provenance_only_updates`,
`reconciliation_plan_fingerprint`, and `rows` — one structured entry per
appearance carrying its action, changed field names, categories, and safety
decision. Output ordering is deterministic (by game, then pitcher), so a shadow
report and a write report can be compared directly.

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

## Execution scope: additive vs exclusive

An operator asking for five specific games got all 109. `--game-pk` means
"**also** plan these", not "plan **only** these" — it adds explicit repair
games to the governed date window. That behaviour is retained and is now
documented honestly, because other callers rely on it.

`--only-game-pk` is the exclusive option. It means *exactly these games and no
others*:

* only the requested games are queried, so nothing else can enter the plan;
* no other newly final game, no retry, no correction-horizon re-check, no
  best-effort backlog, no unresolved work from outside the set;
* a requested game is classified `explicit_repair`;
* normal finality, schedule-authority, and safety rules still apply.

### Exact-set preflight

Before **any** MLB request and before any write, the run asserts
`requested_unique_ids == planned_ids` — recomputed from the items the run will
actually execute, not from the planner's own self-report, because a guard that
believes the component it guards cannot catch that component being wrong.

The report exposes `execution_scope_mode`, `requested_game_pks`,
`requested_game_count`, `duplicate_requested_count`, `planned_game_pks`,
`planned_game_count`, `unexpected_planned_game_pks`,
`missing_requested_game_pks`, and `execution_scope_exact_match`.

On mismatch the run exits nonzero with a typed safe reason and makes zero MLB
requests, zero database writes, no work item, no postgame marker, no GameLog,
no pitcher update, no dead letter, and marks no checkpoint attempted. A
requested game that is not final, has no schedule authority, or has a finality
conflict is never silently dropped — it fails the scope.

Incompatible options are refused rather than reinterpreted: `--game-pk` with
`--only-game-pk`, `--max-games` with `--only-game-pk`, `--include-backfill`
with `--only-game-pk`, and an empty exclusive set.

### Reviewed-fingerprint write authorization

An exclusive write requires `--expected-plan-fingerprint`, the fingerprint a
human reviewed from the shadow run. The write recomputes the plan from current
database state and current official evidence, compares it to the reviewed
value, and refuses **before the first mutation** on any difference — whether
the stored rows or the official line moved since review. On exact match it
applies that same plan, from the same fetched box score, so review and
application cannot read different evidence.

The refusal reports only the expected fingerprint, the observed fingerprint,
the requested ids, and a safe reason.

## D-009 — completed games are not current-roster authority

A completed game establishes what happened in that game. It never establishes
who a pitcher is today, what team he is on, or whether he is active. Current
roster and team state belong to the official roster authorities.

The identity planner therefore has exactly three outcomes for a pitching line:

| action | meaning |
|---|---|
| `unchanged` | the pitcher exists; nothing about him is rewritten |
| `create_minimal_identity` | no local pitcher exists; create the minimum needed to attribute the appearance |
| `blocked` | the line cannot be attributed safely; refuse and say why |

`update_metadata`, `reactivate`, and `create` are **retired write actions**. An
existing Pitcher row is never mutated from a completed game.

A difference between what the game implies and what the roster says is
**suppressed evidence**, not a mutation. It stays visible in the report, names
only a protected current-state field, says out loud that it was refused, and
never enters the mutation digest or the fingerprint.

### Why this is structural rather than a source-precedence rule

The original R1 and R2 gates passed on GameLog reconciliation while the same
reports carried 942 pitcher-identity actions — 940 metadata updates and 2
reactivations across 423 pitchers — attached to rows whose GameLog action was
`unchanged`. None of them appeared in the manifest or the fingerprint. A
precedence rule would have re-ranked those writes. Making the mutation
structurally impossible removed them.

## One complete plan, one fingerprint

A row plan is not clean because its GameLog half is clean. The complete plan
covers GameLog, pitcher identity, and appearance-team authority together, and
one fingerprint covers all three.

`parity_contract_version` is **4** and is hashed into the fingerprint, so a
contract change invalidates every prior fingerprint by construction.

### The fingerprint covers identity BY VALUE

Under contract 3 the identity half collapsed to a constant on the reported row:
creating pitcher 111 and creating pitcher 222 fingerprinted identically, so a
reviewed fingerprint authorized *any* identity creation rather than the reviewed
one. Contract 4 fingerprints the identity decision **and the values it would
write**. Repairing it immediately exposed a second defect — the writer patched
only the identity action onto the row, so shadow and write fingerprints diverged
— and both were fixed together.

A run is clean only when **every** target is clean.

## Bootstrap status — complete

**The Foundation 3C bootstrap completed successfully.** All 109 governed final
games are reconciled and checkpointed.

| | |
|---|---|
| expected final games | **109** |
| completed final games | **109** |
| unresolved final games | **0** |
| terminal failures | 0 |
| correction pending | 0 |
| publication complete | **yes** |
| reconciled appearance rows | **946** |

The bootstrap was performed by explicit manual dispatch across six reviewed
increments in July 2026, then **independently verified in production by a final
read-only Stage E replay of all 109 games**: 946 rows unchanged, 323 decimal-only
differences ignored, zero mutations on every target, and zero database drift.

**The rollout is closed.** Every temporary Foundation 3C workflow — R1 through
R6 and the Stage E verification — has been retired, and none can be dispatched.
The full rollout history, its production evidence, the fingerprints, and the
hash evidence are preserved in
`docs/archive/2026-07/FOUNDATION_3C_BOOTSTRAP_CLOSEOUT.md`. That record is
historical; this document is the current operating contract.

The fingerprints in that archive are **historical closeout identities**. They
record what the completed bootstrap looked like. They are not authorization and
cannot be supplied to authorize a future write — any later write requires its
own reviewed fingerprint from its own reviewed shadow.

**`GAME_DRIVEN_INGESTION_MODE` remains `off`.**
**Automated activation is a separate decision.**
**Authoritative mode remains unapproved.**

A completed bootstrap is a precondition for considering activation, not an
argument for it. Enabling either lane requires its own reviewed change.

### Next stage

The next controlled step is **automated game-driven ingestion shadow
activation**, handled by a separate reviewed change with its own evidence and
its own production observation. Write and authoritative modes are **not
approved** for automated operation.

`backend/scripts/profile_daily_ingestion_readonly.py` is retained as activation
operations support: a read-only profile for observing universe selection,
runtime, scope, budget handling, and candidate classification while that
activation is watched. It has no workflow and is run deliberately.

Rollback and fail-closed behaviour remain permanent regardless of mode: an
incomplete or unsafe run withholds publication rather than publishing partial
evidence.

### What a completed bootstrap does and does not claim

It claims that 109 governed final games are reconciled, checkpointed, and
replayable with zero mutations, and that no baseball-data row changed while that
happened.

It claims nothing about BaseballOS data quality in general. The 14 false GameLog
provenance events, the first-write Pitcher forensics, and the pre-existing global
dead letters recorded at closeout all remain open and separate.

## Ingestion modes and the activation decision

| `GAME_DRIVEN_INGESTION_MODE` | What the lane does | Publication authority |
|---|---|---|
| `off` | nothing. **This is the current production value.** | old pitcher loop |
| `shadow` | plan, fetch, extract, project insert/update/no-op; writes nothing | old pitcher loop |
| `write` | reconcile and checkpoint for real | old pitcher loop |
| `authoritative` | as `write`, and the game-level proof drives publication | **game lane** |

`--plan-only` builds the work plan and stops: no MLB request, no write. It is
available in any mode.

**Production is `off` and stays `off` until a separate reviewed change moves
it.** The bootstrap was completed by explicit manual dispatch, not by enabling
the lane, and completing it granted no activation authority. Moving to `shadow`,
`write`, or `authoritative` is its own decision with its own evidence.

Authoritative mode is unapproved. It is the only mode that changes who decides
whether a snapshot publishes, so it does not follow automatically from a
successful write mode.

## Operator repair procedure

```bash
# Shadow plan. No MLB request, no write.
python scripts/game_driven_ingestion.py --plan-only

# Full-window shadow reconciliation. Fetches games, writes nothing.
python scripts/game_driven_ingestion.py --mode shadow

# EXCLUSIVE shadow of exactly five games. Nothing else may enter the run.
python scripts/game_driven_ingestion.py --mode shadow \
    --only-game-pk 823518 --only-game-pk 824735 --only-game-pk 823761 \
    --only-game-pk 824083 --only-game-pk 824327

# EXCLUSIVE write of exactly those games, authorized by the fingerprint a
# human reviewed in the shadow run above.
python scripts/game_driven_ingestion.py --mode write \
    --only-game-pk 823518 --only-game-pk 824735 --only-game-pk 823761 \
    --only-game-pk 824083 --only-game-pk 824327 \
    --expected-plan-fingerprint <sha256 from the reviewed shadow run>

# Governed repair ADDED to the normal window. This does NOT bound the run —
# the whole governed window is planned as well.
python scripts/game_driven_ingestion.py --mode write --game-pk 776543

# Read-only forensics on games the lane already wrote.
python scripts/inspect_game_ingestion_writes.py --game-pk 823518 --game-pk 824735

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
