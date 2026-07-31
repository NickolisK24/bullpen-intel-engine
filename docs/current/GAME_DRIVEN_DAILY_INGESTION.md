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

## R1 validation from a phone

Stage R1 replays the five games the first controlled write already reconciled.
It is the gate that proves the canonical-innings repair holds in production,
and it can be run with no computer.

**Workflow:** `.github/workflows/foundation-3c-r1-shadow-validation.yml`,
displayed as **Foundation 3C R1 Shadow Validation**. Manual dispatch only — no
schedule, no push, no pull-request trigger.

Everything is hard-coded, so there is nothing to type and nothing to
misconfigure from a phone:

| | |
|---|---|
| games | 823518, 824735, 823761, 824083, 824327 |
| reference date | 2026-07-29 |
| mode | `shadow` (exclusive scope via `--only-game-pk`) |
| permissions | `contents: read` only |
| `GAME_DRIVEN_INGESTION_MODE` | `off` (defense in depth) |

It writes no baseball data. It runs the merged Foundation 3C shadow path,
which is logically read-only before any transaction handling, and adds no
compensating write, cleanup, or write-and-roll-back of its own. It does not
call the daily or postgame sync, does not publish a snapshot, and does not
deploy anything.

### Running it

1. Open the repository in the GitHub mobile app or a mobile browser.
2. Open **Actions**.
3. Select **Foundation 3C R1 Shadow Validation**.
4. Tap **Run workflow**, choose `main` if a branch selector appears, and
   confirm.
5. Open the finished run and read the job summary.
6. Download the `foundation-3c-r1-shadow-validation` artifact if you want the
   full report.

### Production result — PASS

R1 ran against production and passed:

```
Scope        requested 5, planned 5, exact match yes
Games        completed 5, failed 0
Rows         expected 38, inserted 0, updated 0, unchanged 38, blocked 0
Innings      decimal-only differences safely ignored 14
             canonical outs corrections 0
             statistical corrections 0
Writes       none
```

The five-game write that previously replayed as 14 "official corrections" now
replays to zero mutations. The 14 differences are recognised as derived
decimal-companion representation drift and ignored. D-008 holds in production.

**This proved GameLog convergence only.** Those same rows also carried pitcher
identity actions that write mode would have applied, and R1 did not count them.
See [D-009](#d-009--completed-games-are-not-current-roster-authority). R1 now
additionally requires zero pitcher-identity mutations, zero reactivations, zero
metadata updates, zero identity creations, zero appearance-team mutations, and a
`complete_mutation_count` of zero.

The job summary states the result directly. The artifact contains the raw
shadow report, a structured validation summary, and the same summary in
Markdown, retained 14 days.

### Failure is a stop

A failed validation fails the job. It is never downgraded to a warning
annotation. The summary names the failed invariant with its expected and
observed values, the requested and planned game ids, and nothing else — no
payload, path, credential, or exception text. Artifacts are scanned for
credential-shaped content before upload and the run fails if anything matches.

**R2 must not begin until R1 passes.** `GAME_DRIVEN_INGESTION_MODE` stays
`off` throughout; R1 does not change it and does not enable the automated
lane.

## R2 full-window review from a phone

R1 proved the repair for five games. Stage R2 asks the harder question: does it
hold across the **complete governed window**, and is anything still outstanding
there safe enough for a human to review?

**Workflow:** `.github/workflows/foundation-3c-r2-full-window-shadow.yml`,
displayed as **Foundation 3C R2 Full-Window Shadow Review**. Manual dispatch
only — no schedule, no push, no pull-request trigger, no inputs.

| | |
|---|---|
| scope | the normal governed window — no `--only-game-pk`, no `--max-games` |
| reference date | 2026-07-29 |
| mode | `shadow` |
| permissions | `contents: read` only |
| `GAME_DRIVEN_INGESTION_MODE` | `off` (defense in depth) |

It writes no baseball data, creates no checkpoint, publishes nothing, and
deploys nothing. It runs the merged shadow path and adds no compensating write,
cleanup, or write-and-roll-back of its own.

The counts are deliberately **not** hard-coded. Five games already carry
completed checkpoints and normal production activity moves what is planned, so
the invariant R2 enforces is semantic rather than arithmetic:

> no decimal-only difference may become a planned mutation
> and no completed game may write current pitcher state

### Running it

1. Open the repository in the GitHub mobile app or a mobile browser.
2. Open **Actions**.
3. Select **Foundation 3C R2 Full-Window Shadow Review**.
4. Tap **Run workflow**, keep `main`, and confirm.
5. Open the finished run and read the job summary.
6. Download `foundation-3c-r2-full-window-shadow-review` when the result is
   REVIEW REQUIRED, and send the summary and update manifest for review.

### Three results

| Result | Job | Meaning |
|---|---|---|
| **PASS** | succeeds | the whole governed window already reconciles; zero mutations of EVERY class — GameLog, pitcher identity, appearance team |
| **REVIEW REQUIRED** | succeeds | the run was safe and one or more legitimate official corrections remain outstanding |
| **FAILED** | fails | a foundational invariant broke — rollout stop |

**A green REVIEW REQUIRED run approves nothing.** It means evidence gathering
succeeded, not that a write is authorized. Legitimate corrections are recorded
for a human to read, never applied and never auto-approved, because a
correction that is individually safe can still be wrong in aggregate — and the
only party who can judge that is the person accountable for the published
numbers. R3/R4 stay blocked until the update manifest is reviewed.

A FAILED result is a rollout stop, never a warning. Among the conditions that
fail closed: a projected insert, a blocked or unsafe row, an unknown changed
field, row totals that do not reconcile against the per-row detail,
`innings_pitched` appearing as a semantic change, a derived companion applied
without its authority moving, a game failure, a budget stop, a finality
conflict, missing schedule authority — and, since D-009, **any** current-state
pitcher mutation, any reactivation, any `update_metadata`, any blocked identity,
any unknown identity field, or identity counters that disagree with the rows.

The only identity action a human may be asked to review is a minimal identity
creation. Everything else that would write is a stop.

### Artifacts

Uploaded as `foundation-3c-r2-full-window-shadow-review`, retained 14 days,
uploaded even when the run fails:

| File | What |
|---|---|
| `r2-full-window-shadow.json` | the raw shadow report |
| `r2-validation-summary.json` | structured result, counts, and failed invariant |
| `r2-validation-summary.md` | the same summary as the job summary |
| `r2-update-review.json` | one entry per projected mutation of every class, ordered by target, game, then pitcher |
| `r2-update-review.md` | the manifest as a readable table |

The manifest is written even when it is empty, so a reviewer never has to
wonder whether it was withheld. Every artifact is scanned for
credential-shaped content before upload; a match deletes the file and fails the
job without printing what matched.

**Publication completeness will read `false`, and that is correct.** R2 is
shadow mode, so it creates no completion checkpoints and the games it reads
stay uncheckpointed. The validator checks the completeness object for internal
consistency and for the failures that would matter — terminal failure games,
finality conflicts, missing schedule authority — and never rewrites it to make
R2 look green.

`GAME_DRIVEN_INGESTION_MODE` stays `off` throughout. R2 does not change it and
does not enable the automated lane.

## D-009 — completed games are not current-roster authority

**Permanent rule.**

```
completed-game pitching line
    = authority for APPEARANCE identity and HISTORICAL appearance context

official current roster / assignment sources
    = authority for CURRENT state
```

### What production R1 and R2 actually proved

Both passed on **GameLog reconciliation**. Neither proved complete database
convergence, because neither counted `Pitcher` mutations at all.

The production R2 report reconciled 946 appearance rows to zero GameLog changes
and reported PASS with an empty update manifest. The same report carried:

```
mutation_category_counts:
    pitcher_identity_reconciliation: 942
    unchanged_row:                   946
```

Independently verified from the artifact: 942 rows carried an identity action —
940 `update_metadata` and 2 `reactivate` — across 423 unique pitchers, every one
of them attached to a row whose GameLog action was `unchanged`. The two
projected reactivations were game 823758 / pitcher 621121 and game 822706 /
pitcher 640454. Write mode would have applied all 942.

The five R1 games carried identity activity too. **R1 proved GameLog
convergence; it did not prove complete database convergence.**

### Root cause

GameLog reconciliation was centralised into a pure planner. Pitcher resolution
was not — it stayed a side-effecting path that mutated and flushed `Pitcher`
rows before or alongside the GameLog work. The reconciliation fingerprint
covered only the GameLog decision, the validators used GameLog actions as the
mutation population, and the R2 manifest listed only rows whose GameLog action
was `update`. So hundreds of planned Pitcher writes could coexist with
`rows_updated: 0`, `changed_fields_counts: {}`, an empty manifest, and `pass`.

That is two defects at once: shadow could not see what write would do, and
historical evidence was acting as current-roster authority.

### What a completed game may and may not establish

| May establish | May not establish |
|---|---|
| the MLB person id on that appearance | current active status |
| a name for an identity that does not exist locally | current roster status or its provenance |
| that the person pitched in that game | current team assignment or its provenance |
| historical team-at-appearance (on the GameLog fields) | current organization or assignment timestamps |
| the official pitching line for that game | reactivation of an inactive row |

### Existing row: never mutated

An existing `Pitcher` is used as the identity anchor and left alone. Not
reactivated, not reassigned, not renamed, not restatused, no refreshed
timestamps. Differences between the historical appearance and the current row
are recorded as **suppressed** evidence — visible, counted, reviewable, and
refused.

This is structural rather than source-dependent: the planner has no branch that
can emit a current-state field as a changed field for an existing row, so no
combination of sources or precedence flags can produce one. An unverified
roster status is protected exactly as strongly as an official one.

An inactive or differently assigned pitcher still owns their historical
appearances. A suppressed current-state difference is **not** an unresolved
identity and never blocks the appearance from reconciling.

`update_metadata` and `reactivate` no longer exist as completed-game identity
actions.

### Missing row: minimal creation only

A new appearance cannot be persisted without an identity, so one may be created
— as a separate governed action that enters the reviewed fingerprint. It claims
no current state:

| Written | Left unset |
|---|---|
| `mlb_id` | `team_id`, `team_name`, `team_abbreviation` |
| `full_name` (from the official line) | `team_assignment_status`, `team_assignment_source`, `team_assignment_updated_at` |
| `position` (as the official line recorded it) | `roster_status_updated_at` |
| `active = False` | |
| `roster_status = UNKNOWN` with an appearance-identity source | |

`active` is set explicitly to `False` because the column defaults to `True` —
leaving it unset would make a three-week-old appearance silently assert that the
player is on a roster today. `position` keeps what the official line recorded
rather than being flattened to `P`, so a two-way player's `DH` record is not
turned into a bullpen arm.

Identity safety failures — missing or invalid person id, conflicting
identifiers, invalid team side, a genuinely new identity with no name — still
fail closed exactly as before.

### One complete plan, one fingerprint

Each appearance now carries a single plan combining pitcher identity, GameLog
reconciliation, and appearance-team authority. Shadow and write consume the same
plan, and the fingerprint commits to all of it.

The fingerprint **changes** when any of these change: a GameLog
insert/update/blocked decision, a semantic GameLog changed field, an applied
companion caused by its authority, a minimal identity creation or its values, an
appearance-team mutation, or a blocked identity decision.

It does **not** change for ignored decimal representation drift, suppressed
current-state differences, application-time timestamps, surrogate ids unavailable
during shadow, or row order.

`reconciliation_plan_version` and `parity_contract_version` are now `3`;
`complete_plan_version` is `1`; `identity_plan_version` is `1`.

### A run is only clean when every target is clean

`complete_mutation_count` covers GameLog mutations, identity mutations, and
blocked entries together. R1 and R2 both require it to be zero before the
rollout proceeds — a run may not be described as "no mutations" while any target
would be written.

Suppressed historical differences are reported separately and are never counted
as mutations.

## Post-D-009 production results

Both gates were re-run after D-009 merged and both passed on the complete
mutation contract — every database target, not just GameLog.

**R1 — PASS**

```
Scope        requested 5, planned 5, exact match yes
Rows         expected 38, inserted 0, updated 0, unchanged 38, blocked 0
Innings      decimal-only differences ignored 14, outs corrections 0
Mutations    GameLog 0, pitcher identity 0, appearance team 0, total 0
Identity     reactivations 0, metadata updates 0, creations 0, blocked 0
Suppressed   1 historical current-state difference
Writes       none
```

**R2 — PASS**

```
Window       109 games planned, 109 completed, 0 failed
Rows         expected 946, inserted 0, updated 0, unchanged 946, blocked 0
Innings      decimal-only differences ignored 323, outs corrections 0
Mutations    GameLog 0, pitcher identity 0, appearance team 0, total 0
Identity     reactivations 0, metadata updates 0, creations 0, blocked 0
Suppressed   57 historical current-state differences
Writes       none
```

The 942 identity actions R2 previously carried are gone. The differences that
produced them are still present and still visible — as 57 suppressed
current-state differences, which are refused evidence rather than mutations.

## R3 controlled-sample review from a phone

R1 and R2 proved the whole population is clean. R3 asks the last question
before a write is proposed: is *this specific five-game sample* still
unresolved, still eligible, and provably clean — and what exact plan would a
write have to match?

**Workflow:** `.github/workflows/foundation-3c-r3-controlled-sample-shadow.yml`,
displayed as **Foundation 3C R3 Controlled Sample Shadow**. Manual dispatch
only — no schedule, no push, no pull-request trigger, no inputs.

### The approved sample

The first five unresolved games after the five completed by the first
controlled write, in reviewed order:

| Game | Appearance rows | Ignored decimal differences |
|---|---|---|
| 823110 | 6 | 2 |
| 825055 | 8 | 4 |
| 824004 | 9 | 2 |
| 823438 | 10 | 6 |
| 824408 | 10 | 4 |
| **Total** | **43** | **18** |

| | |
|---|---|
| scope | exclusive — `--only-game-pk` five times, nothing else |
| reference date | 2026-07-29 |
| mode | `shadow` |
| permissions | `contents: read` only |
| `GAME_DRIVEN_INGESTION_MODE` | `off` (defense in depth) |

### How eligibility is actually proven

Not by `candidate_reason`. Under exclusive scope the planner short-circuits
every requested game to `explicit_repair` before it classifies state at all
(`game_ingestion_planner._candidate_decision`, the `if explicit:` branch), so
`newly_final` is unreachable for an R3 run and asserting it would fail every
time while proving nothing.

The load-bearing proof is the **attempt number**. The planner derives it from
the stored work item, so attempt 1 means no work item exists — and no work item
means no completed checkpoint, no prior failed attempt, and no correction
re-check. A game already written by the first controlled write cannot report
attempt 1.

Alongside it R3 requires `retry_count == 0`, `corrected_final_count == 0`,
publication-critical criticality, and the pinned July 29 bootstrap population:

```
expected final games 109, completed 5, unresolved 104,
terminal failures 0, publication complete false
```

A legitimately changed population is reported as a failure, not reinterpreted.
The sample was chosen against this exact state.

### Two results only

There is no `review_required` for R3. This sample is expected to be clean, and
any projected mutation means it is not eligible for the controlled write.

| Result | Job | Meaning |
|---|---|---|
| **PASS** | succeeds | zero mutations on every target; the package may be reviewed |
| **FAILED** | fails | rollout stop; R4 must not be created |

**PASS does not authorize a write.** It produces the reviewed complete
reconciliation fingerprint that a later R4 would have to match, and nothing
more. `write_approved` is structurally `false` — there is no code path that can
set it true — and `r4_status` is always `blocked_pending_founder_review`.

### Artifacts

Uploaded as `foundation-3c-r3-controlled-sample-shadow`, retained 14 days,
uploaded even when the run fails:

| File | What |
|---|---|
| `r3-controlled-five-shadow.json` | the raw shadow report |
| `r3-validation-summary.json` / `.md` | structured result and the job summary |
| `r3-reviewed-authorization.json` / `.md` | the reviewed package, ordered by the approved sample |

The authorization package carries the run-level complete fingerprint, a
per-game fingerprint, each game's source revision, all five version constants,
and the suppressed-difference counts. Every artifact is scanned for
credential-shaped content before upload.

### After the run

Send the job summary, `r3-reviewed-authorization.md`, and the complete
fingerprint for review. **R4 must not be created or run until that fingerprint
is founder-approved.** `GAME_DRIVEN_INGESTION_MODE` stays `off` throughout.

## The complete fingerprint covers pitcher identity by VALUE

`--expected-plan-fingerprint` is the only thing standing between a reviewed plan
and an applied write, so what it covers matters more than almost anything else
in this lane.

**Defect found while preparing R4.** The identity half of the fingerprint read a
nested `pitcher_identity` key on the row. That key exists on the raw planner
plan, but `_safe_row_entries` flattens it away — and `_safe_row_entries` is what
produces both the report's `complete_reconciliation_fingerprint` and the rows
`_authorize_reviewed_plan` compares. So the identity component collapsed to the
same constant on every row:

```
identity component, row A: ('None', 'unchanged', '', '')
identity component, row B: ('None', 'unchanged', '', '')
```

Creating pitcher 111 and creating pitcher 222 therefore fingerprinted
identically. A reviewed fingerprint authorized *an* identity creation, not *the*
reviewed one. A creation was still distinguishable from an unchanged row,
because the identity mutation category leaks into `mutation_categories` — which
is exactly why this survived R3: nothing in that sample created an identity, so
nothing exercised the value half.

**Repair.** `fingerprint_component` now reads the flattened
`pitcher_identity_action`, `pitcher_identity_blocked_reason`, and
`pitcher_identity_mutation_digest` fields, and `plan_row` mirrors them onto the
row. The raw plan and the reported row now fingerprint identically by
construction, so the guard compares the same identity the report published.

Repairing it exposed a second defect: the canonical writer builds its plan
without the identity half and patches it on afterwards, and that patch set only
the action. The write's fingerprint was therefore missing the digest that
shadow carried — a genuine shadow/write divergence, now fixed by patching every
field the fingerprint reads.

Suppressed historical differences remain excluded: they are refused evidence and
must not move a fingerprint that authorizes mutations.

**`parity_contract_version` moved `3` → `4`.** The contract version is hashed
into the fingerprint, so every fingerprint reviewed under contract 3 is stale by
construction and cannot be reproduced under contract 4. That is deliberate: a
stale authorization must fail loudly rather than silently authorize a write
whose identity half was never really reviewed.

## Controlled parity rollout

Production remains **off** until parity validation passes. The next operator
sequence is:

| Stage | What | Requirement |
|---|---|---|
| C1 | Shadow replay of the five already-written games | zero inserts, zero updates, all rows unchanged — proves the prior write left them reconciled |
| C2 | Shadow of the next five unprocessed games | record projected inserts/updates/unchanged, changed fields, categories |
| C3 | Controlled write of those same five | **exact** parity with C2: same actions, same changed fields, same category counts, same totals, zero unexpected mutations, zero failures |
| C4 | Shadow replay of those five | zero inserts, zero updates, all unchanged |

Only after all four pass may the remaining bootstrap window be considered.
Authoritative mode is not part of this sequence.

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
