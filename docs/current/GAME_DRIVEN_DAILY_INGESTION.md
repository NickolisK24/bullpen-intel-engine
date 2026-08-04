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

`services/game_ingestion_completeness.py::build_game_ingestion_completeness(D,
lane_mode=...)` produces ONE canonical per-game classification
(`classify_game_ingestion_scope`) and projects it into TWO explicitly separate
views. Both come from the same classification, so they cannot drift into
disagreeing about a game.

### Why the views are separate

A read-only production audit of current state found **105** expected final
games, **42** with completed work items, and **63** counted as unresolved final
games. All 63 carried official-final evidence, final stored schedule authority,
and stored appearance rows, and **none** was a true baseball deficit. Their only
defect was the absence of a durable `GameIngestionWorkItem` — which the lane
does not create, because it runs in `shadow`.

The daily sync was folding that number into `publication_critical_unresolved`.
That is a publication-scope defect: **shadow OBSERVATION incompleteness
represented as PUBLICATION-BLOCKING incompleteness.** The governing invariant
is now:

    observation backlog != publication blocker

unless game-driven publication authority has been explicitly activated.

### The two views

`observation` — what the lane has and has not persisted for its own staged
rollout: `expected_final_games`, `completed_work_item_games`,
`unresolved_game_count`, `retryable_work_item_count`,
`terminal_work_item_count`, `complete`, `reason_codes`.

`publication_gate` — what may withhold the public snapshot under the lane's
CURRENT authority: `authority_effect`, `complete`,
`blocking_unresolved_game_count`, `blocking_terminal_failure_count`,
`blocking_retryable_work_item_count`, `blocking_scope_game_count`,
`blocking_completed_game_count`, `finality_conflict_count`,
`schedule_authority_missing_count`, `correction_pending_count`,
`appearance_rows_expected`, `appearance_rows_reconciled`,
`observation_only_game_count`, `reason_codes`.

`authority_effect` is a closed vocabulary: `observational_only`,
`non_authoritative_write`, `authoritative`, `unavailable`.

| Lane mode | `authority_effect` | Work-item evidence blocks? |
|---|---|---|
| `shadow` | `observational_only` | no |
| `write` | `non_authoritative_write` | no |
| `authoritative` | `authoritative` | **yes** |
| `off` / unknown | `unavailable` | gate is never `complete` |

**Work-item evidence — missing, retryable, or terminal — blocks only under
`authoritative`.** Evidence about BASEBALL rather than about the lane's own
bookkeeping blocks in EVERY mode: canonical finality conflicts, missing
required schedule authority, an expected-versus-reconciled appearance-row
shortfall, and a material correction conflict.

### Fields

Publication truth: `publication_complete` (= `publication_gate.complete`),
`decision_reasons` (= `publication_gate.reason_codes`),
`publication_blocking_unresolved_final_games`,
`publication_blocking_terminal_failure_games`, plus `lane_mode` and
`publication_authoritative`.

Retained legacy fields are **OBSERVATIONAL**, kept under their original names so
existing telemetry readers do not break, and listed in `observational_fields`:
`expected_final_games`, `completed_final_games`, `unresolved_final_games`,
`terminal_failure_games`. A reader that treats `unresolved_final_games` as a
publication blocker is reading observation telemetry as authority — the
`publication_blocking_*` fields are the gate.

Mode-independent baseball evidence keeps its existing names:
`correction_pending_games`, `corrected_games_reconciled`,
`critical_appearance_rows_expected`, `critical_appearance_rows_reconciled`,
`finality_conflicts`, `schedule_authority_missing`,
`best_effort_games_planned`.

Reason codes: `unresolved_final_games`, `critical_game_failure_unresolved`,
`terminal_critical_game_failure`, `finality_conflict_unresolved`,
`schedule_authority_missing`, `critical_appearance_rows_unreconciled`,
`material_correction_pending`, `game_ingestion_complete`,
`game_lane_not_publication_authoritative`, `game_lane_authority_unavailable`,
and the non-blocking `shadow_observation_unresolved_games`. The last two
informational codes are appended to the gate only AFTER completeness has been
decided, so a non-blocking observation signal can never turn into a withholding
one.

### Membership

`unresolved_final_game_membership(D)` retains its **observation** meaning and
reports `membership_view: 'observation'`.
`publication_blocking_game_membership(D, lane_mode=...)` is the single blocker
projection; it also reports `observation_only_game_pks`, so games withheld from
the gate are named rather than silently dropped. Both are derived from
`classify_game_ingestion_scope`.

`critical_appearance_rows_reconciled` credits only rows that are **both** proven
by the work item **and** still present in the appearance ledger, so a work item
cannot claim completeness for rows that later disappeared.

This remains an additional, more precise input to the same publication-critical
contract — no existing gate (finality, appearance ledger, freshness,
provenance, slate coverage) is weakened. The 63 games remain observable and are
not erased, repaired, backfilled, or reclassified as complete.

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

## Cycle integration points

The lane is reached through **one service call per sync cycle**. It is never
invoked as a second, parallel ingestion command, and `scripts/game_driven_ingestion.py`
is an operator tool, not part of any automated cycle.

| Cycle | Integration point | Writing modes | Ordering |
|---|---|---|---|
| daily sync | `services/sync.py::run_daily_sync` | supported | **before** the pitcher loop |
| postgame refresh | `services/sync.py::run_postgame_refresh` | **refused** | **after** the postgame sweep |
| morning schedule-only refresh | none | — | — |
| Tonight refresh | none | — | — |
| explicit backfill | **shares the postgame point** | **refused** | after the sweep |
| intraday audit | none | — | — |

> **Backfill shares the postgame entry point.** The workflow's explicit backfill
> step runs `run_postgame_refresh.py --date`, which is the same function as the
> scheduled postgame refresh. Adding the lane to that function therefore put it
> on the backfill path too. This is inert while the lane is `off`, and writing
> modes are refused on that cycle regardless — but **any activation must set
> `GAME_DRIVEN_INGESTION_MODE: 'off'` explicitly on the backfill step**, because
> backfill will not inherit `off` merely by being a different workflow step.
> `test_explicit_backfill_shares_the_postgame_entry_point` pins this so the
> requirement cannot be forgotten silently.

### The postgame integration point

Foundation 3C wired the lane into the daily sync only. The postgame refresh —
the cycle that actually ingests completed games overnight, and therefore the
cycle that produces most of the lane's candidates — had **no integration point
at all**. It was added afterwards, off by default, as a prerequisite for any
automated shadow activation: without it, a postgame shadow cycle would have
produced an artifact describing a lane that never ran.

Two properties make it safe there.

**It runs after the legacy sweep, not before it.** The postgame sweep is that
cycle's writer and it commits per game. A lane placed ahead of it would project
every one of those rows as an insert the sweep is about to perform anyway —
noise, not evidence, and a projection that could never satisfy a clean-cycle
contract. Reading after the writer asks the question worth asking overnight:
*given what the current path just wrote, what would the game-driven lane do?*
The daily sync's ordering is deliberately the opposite, because there the game
lane is the one that becomes authoritative and the pitcher loop is demoted
behind it.

**Writing modes are refused on the postgame cycle.** The daily sync can host a
writing game lane because it has an explicit conflict-prevention mechanism —
`skip_game_pks`, so the demoted pitcher loop never rewrites a game the lane just
reconciled. The postgame sweep has no equivalent. Rather than allow two writers
to reach the same canonical rows, `write` and `authoritative` are refused on
that cycle, **before any MLB request and before any write**, with the reason
`write_mode_unsupported_for_cycle`. A refused lane is also forced
non-authoritative, so it can never take over a publication gate it never ran.
Lifting that refusal requires building postgame conflict prevention first, in
its own reviewed change.

### Postgame lane budget

The postgame refresh has never had a total-process runtime budget; its stages
are bounded by the number of unprocessed completed games. The game-driven lane
is different — it plans from the schedule ledger and can discover an arbitrarily
large correction window — so it is given an explicit bounded slice,
`POSTGAME_REFRESH_INGESTION_BUDGET_SECONDS` (default **600s**), further reduced
by `GAME_DRIVEN_INGESTION_BUDGET_SHARE` while the lane is not authoritative.

This is a safety bound, not a performance tuning knob. Reaching it is a clean,
resumable, reported stop; running past the 20-minute postgame command timeout
would kill the entire postgame refresh. The lane reports both its allocated
budget and its remaining headroom so the right value can be chosen from observed
production behaviour rather than guessed.

### What the cycle reports

Both cycles attach the lane result at `sync.game_driven_ingestion` in the sync
status. It is one object, not a competing report, and it carries the identity
(`mode`, `job_name`, `writes_enabled`, `publication_authoritative`), the plan
and execution counts, **every mutation target**, the control-state counts, the
five version constants, the run fingerprint, and the budget allocation and
headroom.

The fingerprint recorded there is **evidence identity only**. It has never been,
and can never become, authorization for a write.

Nothing in the reported object may carry credentials, connection strings,
headers, raw payloads, filesystem paths, or exception text. Failures are
reported by safe class name.

### Failure isolation

In `shadow` the lane is an observer, and a defect in an observer must not cost
the production run its data. A shadow planning, fetch, extraction, or unexpected
failure is caught, classified, and surfaced at `sync.game_driven_ingestion`, and
it does **not**:

* change the legacy sync status;
* change `publication_critical`;
* withhold a snapshot the current authority would publish;
* create a `SyncFailure` or a game-driven dead letter;
* create or update a `GameIngestionWorkItem`;
* advance a checkpoint;
* change the runner exit code.

`publication_critical` is only computed from the game lane when the lane is
**authoritative**. In `off`, `shadow`, and `write` the established authority is
unchanged.

## Automated shadow activation

The lane runs automatically in `shadow` on the daily and postgame production
cycles. It plans, fetches, extracts, and projects. **It writes nothing**, and
the existing sync and publication path remains authoritative throughout.

`GAME_DRIVEN_INGESTION_MODE: 'shadow'` is set on the two runner steps in
`.github/workflows/baseballos-sync.yml` and nowhere else. It is a reviewed
literal in the workflow source — there is no workflow input and no repository
variable that could move it to a writing mode without a code review.

| Cycle | Mode | Evidence |
|---|---|---|
| scheduled daily (`0 10 * * *`) | `shadow` | realization proof |
| manual `mode=daily` | `shadow` | realization proof |
| scheduled postgame (`0 2,4,6 * * *`) | `shadow` | convergence proof |
| manual `mode=postgame` | `shadow` | convergence proof |
| explicit backfill | **`off`** (explicit) | none |
| morning schedule-only (`0 14 * * *`) | off | none |
| Tonight refresh | off | none |
| intraday audit | off | none |

### The two cycles are not one rule

This is the single most important thing to understand about the evidence.

**Daily runs before its writer.** When newly final or corrected games exist the
projection legitimately reports inserts, updates, appearance-team changes,
minimal identity creations, and statistical corrections. Those are **projected
reconciliation actions**, not database writes performed by shadow. A daily cycle
that fails merely because the plan found work would fail on every day the lane
is useful.

**Postgame runs after its writer.** By then the canonical rows should already be
correct, so a healthy postgame cycle projects **nothing at all**. A nonzero
postgame projection means the postgame writer left canonical work behind, and
that is an activation-health failure.

A projected insert is never reported as a shadow database write. The two are
counted separately and named differently, everywhere.

### Daily realization proof

After the legacy daily writer finishes, the cycle asks the only question that
means anything about a projection taken beforehand: *did that writer actually
put the canonical rows into the projected state?*

Each plan row carries the fields it intends to determine (`target_fields`) and a
digest of the values it intends them to hold (`target_state_digest`), both owned
by `game_log_reconciliation`. After the writer, the stored row is read and the
**same encoder** digests the **same field names**. Equal digests mean the writer
realized the projected target.

It does not call MLB, does not re-plan, does not re-run ingestion, and does not
write. It consumes the plan the lane already produced.

Only field names, governed identifiers, classifications, and digests are
reported. The intended values never leave the process, so no raw row and no
before/after value can travel in the proof.

A daily cycle **fails** when a projected row is missing afterwards, the stored
state differs from the projected target, a source revision changed against a
recorded checkpoint, a duplicate canonical identity exists, the writer applied
only part of the plan, an unsupported identity action was projected, or the
proof could not be built at all. A missing proof and a passing proof never look
alike.

**Identity actions.** D-009 already reduced the vocabulary to `unchanged`,
`create_minimal_identity`, and `blocked`. A clean daily projection may contain
the first two. A `blocked` action, or anything outside that vocabulary, fails
the cycle. A current-state mutation refusal is D-009 working correctly and is
counted, not penalised.

### Postgame convergence proof

Zero projected inserts, zero updates, zero blocked rows, every expected row
unchanged, and every mutation target zero — including minimal identity creation.
Anything else fails, and it never triggers an automatic game-driven write.

### Projected actions versus actual execution effects

Every cycle reports both, separately:

* **projected** — what the plan would do, counted from the plan;
* **`execution_effects`** — what the lane actually did to the database, counted
  at the write sites themselves: work items claimed, checkpoints completed,
  commits issued, dead letters recorded, rows persisted.

`execution_effects` is not derived from the mode name. Those counters live where
the writes happen, so in shadow they are unreachable and stay zero — and the same
counters go non-zero in write mode, which is what makes the zero meaningful.

### Artifacts

Per eligible cycle, retained 30 days as
`game-driven-shadow-<run-id>`:

```
artifacts/game-driven-shadow/<cycle>-sync-summary.json
artifacts/game-driven-shadow/<cycle>-activation-summary.json
artifacts/game-driven-shadow/<cycle>-activation-summary.md
```

The sync summary is written by the runner itself through `--output`: the same
object it prints, sorted keys, atomically replaced. Durable evidence is never
produced by parsing a log stream that interleaves stdout with logging.

Artifacts are scanned for credentials, connection strings, tracebacks, and
runner paths **before** upload. A file that matches is deleted and never leaves
the runner; only its filename and a safe category are reported.

### Failure isolation and ordering

A shadow defect is an activation incident, not permission to withhold valid
production data. The workflow order is fixed:

1. the eligible daily or postgame runner;
2. the existing Tonight/schedule follow-up;
3. the existing appearance-ledger audit;
4. the existing publication and dashboard verification;
5. the activation validator;
6. the credential scan;
7. the job-summary append;
8. the artifact upload;
9. the final activation-health gate.

The validator is never a prerequisite for a publication step. Its exit code is
captured rather than allowed to terminate the job, so the evidence is preserved
before anything fails, and the gate runs last.

### Rollback

Change the two runner steps from `GAME_DRIVEN_INGESTION_MODE: 'shadow'` back to
`'off'`, leave backfill off, and merge. **No database cleanup is required,
because shadow performs no writes.** Disabling the whole workflow is an
emergency lever for stopping production synchronization itself, not the normal
way to roll back shadow.

### Observation window

Automated write mode may not be **proposed** until every one of these holds:

* at least one clean scheduled daily PASS;
* at least two clean scheduled postgame PASS cycles;
* at least one clean cycle with `games_planned > 0`;
* at least one daily cycle with projected work and complete realization parity,
  unless no qualifying work occurred in the whole window;
* at least 24 hours of elapsed production observation;
* no activation-health failure, unresolved or divergent daily target, nonzero
  postgame projection, shadow execution write, work-item or checkpoint change,
  game-driven dead letter, schedule-authority gap, finality conflict, budget
  stop, failed or remaining game, unexplained fingerprint instability, or
  publication regression;
* acceptable runtime headroom.

Initial target is **48 hours** maximum when every gate is clean. Manual runs may
supplement the evidence but never replace the scheduled-cycle requirements.

### Promotion evidence package

A future write-mode review requires: qualifying workflow run IDs, repository SHA
per run, trigger classification, cycle kind, reference date, planned game set,
candidate-reason counts, projected row actions, daily realization results,
postgame convergence results, identity actions, correction actions, actual
zero-write effects, source revisions, run and per-game fingerprints, runtime and
budget headroom, sync status, publication proof, artifact names, elapsed
observation time, and an explicit statement that no shadow write occurred.

**That package is evidence, not authorization.** Every activation artifact
records `write_approved: false` and `future_write_authorized: false`, on PASS
and FAILED alike. No shadow fingerprint may be carried into a write command;
a future write requires its own reviewed design.

## First postgame activation cycle — FAILED safely

The first automated postgame shadow cycle failed activation health. Nothing
about production was harmed by it.

| | |
|---|---|
| cycle | postgame, schedule date 2026-07-31 |
| activation result | **FAILED** |
| runner exit code | 0 |
| current sync status | **success** |
| publication | **verified**, snapshot `324` |
| actual shadow writes | **zero on every counter** |

```
games discovered / planned        112 / 112
games attempted / completed        98 /  98
games failed                        0
games remaining                    14
rows expected / unchanged         848 / 847
projected inserts / updates / blocked   0 / 1 / 0
budget stop triggered            true
```

### Why it failed: scope, not speed

The lane was handed a reference date and no scope, so the canonical planner did
exactly what it is built to do for a **daily** cycle and swept the whole rolling
correction horizon — 112 games, of which 87 were *corrected final* from earlier
dates. The postgame refresh had already resolved the only set that cycle
governs, and the lane was not using it.

98 games in 144 seconds of projection is not slow. It is the wrong 112 games.

### The exact-cycle scope contract

The postgame lane now runs with **exclusive scope** over the games that
postgame cycle actually governs, resolved from state the cycle already holds:

* the scope is the cycle's own completed games, de-duplicated and ordered;
* it is resolved **after** the writer, because eligibility depends on what that
  writer finished;
* a game is in scope only when its postgame marker is **fully processed** —
  a game the writer has not finished cannot be expected to project zero;
* every excluded game carries a named reason: `incomplete_after_writer`,
  `failed_marker`, or `no_processing_marker`;
* it costs **no MLB request** and runs **no second planning pass**;
* it reaches the lane through the exclusive-scope mechanism Foundation 3C
  already built, which refuses before any fetch when the plan is not the exact
  requested set.

The report carries `scope_source`, `cycle_game_count`, `requested_game_pks`,
`requested_game_count`, `excluded_game_pks` with reasons, `excluded_reason_counts`,
and the cycle's slate dates, alongside the planner's own exact-scope fields.

**Daily is unchanged** and keeps its rolling correction-horizon behaviour. The
seven-day observation still happens — under daily, where it belongs.

### Safe difference diagnostics

The failed cycle reported "1 projected statistical update" and nothing about
which row, so the discrepancy could not be investigated from the artifact at
all. Every non-unchanged projected row is now named:

```
game_pk · pitcher_mlb_id · action · changed_fields
difference_classifications · blocked_reason · pitcher_identity_action
source_revision · reconciliation_plan_fingerprint
target_state_digest · stored_state_digest
```

Classifications come from a closed vocabulary of existing repository
classifications: `statistical_correction`, `canonical_outs_correction`,
`appearance_team_correction`, `role_or_starter_signal_correction`,
`game_metadata_correction`, `provenance_only`, `decimal_companion_difference`,
`identity_creation`, `identity_blocked`, `blocked_mutation`,
`missing_appearance_row`.

They are derived from the canonical plan's own decision. There is no second
comparator and no second opinion about what changed.

**Field names and digests travel; the values behind them never do.** A reviewer
learns that a row differs and in what way, without the artifact carrying
baseball data, payloads, paths, credentials, or exception text.

### Game 824488 — diagnosed to a class, not yet to a cause

The one projected update was in game `824488`, `newly_final`, represented date
2026-07-30, 9 appearances extracted, 8 unchanged, 1 updated.

What the evidence proves: it was a **GameLog update on one appearance whose
changed fields include a statistical field**. It was *not* a canonical-outs
correction (`canonical_outs_corrections: 0`), not appearance-team, not identity,
not provenance-only, and not decimal representation drift — every one of those
counters was zero.

What the evidence does **not** contain: the pitcher, the field, or the values.
The artifact predates the diagnostic above.

**No repair is included, because no cause is proven.** Both the postgame writer
and the shadow projection reach the *same* canonical `plan_row`, so this is not
a second-comparator defect. The leading unproven hypothesis is a genuine
mid-cycle official revision: the writer fetched the box score, wrote, and the
lane fetched it again moments later. A newly-final game is exactly where MLB
revisions land. The next cycle's diagnostic will name the pitcher, the field,
and the source revision, which distinguishes that from a writer omission.

Guessing a repair here would risk mutating real baseball data to match a
projection whose authority has not been established.

If the same class appears again, the artifact now identifies it: the validator
**refuses to pass any nonzero projection that cannot be attributed**, requiring
one safe diagnostic per projected non-unchanged row carrying `game_pk`,
`pitcher_mlb_id`, `action`, `changed_fields`, `difference_classifications`,
`source_revision`, the fingerprint, and both digests — and failing if any of
them carries `before`, `after`, `field_changes`, or `values`.

### Postgame shadow reactivated on exact-cycle scope

Postgame shadow is **on again**, running over the exact-cycle scope above. The
reactivation gate was met: bounded cycle scope, no seven-day fan-out, every
cycle game either requested or excluded with a named reason, no unexpected
planned game, refusal before fetch on any scope mismatch, zero writes, zero
control-state effects, and a zero-projection convergence contract.

The validator now enforces the scope itself, not merely the projection:
`scope_source`, deterministic and unique requested identifiers, the planner's
`execution_scope_exact_match`, no missing requested game, no unexpected planned
game, planned count never exceeding the request, requested count never exceeding
the cycle, complete request-plus-exclusion accounting, and a named reason on
every exclusion. A fan-out like the first cycle's now fails on
`postgame_scope_fan_out` rather than only on the budget it exhausted.

**Postgame observation restarts from this reactivation.** Cycles observed before
it do not count toward the write-mode gate.

Daily shadow was not disturbed and keeps its correction-horizon behaviour.

### Budget reporting

The first artifact showed a 600-second cap beside a 150-second allocation, which
read as "600 seconds available". Both numbers, and the share relating them, are
now named separately:

```
configured_stage_cap_seconds          600.0
lane_budget_share                     0.25
effective_allocated_budget_seconds    150.0
elapsed_seconds                       observed
remaining_headroom_seconds            observed
budget_stop_triggered                 observed
```

**Neither the cap nor the share was raised.** Raising a budget to make a
mis-scoped cycle finish would hide the defect instead of fixing it.

## GameLog `balls` — field authority RESOLVED (was: unresolved)

A persistent canonical parity discrepancy was isolated precisely and left
deliberately unrepaired while authority was unproven. The read-only audit below
was then run against production and **resolved it**. The original analysis is
kept intact because the repair rests on it; the resolution and the repair
follow, under *Resolution* and *The repair*.

### Production evidence

| | |
|---|---|
| game | `824488` |
| pitcher | `668716` |
| field | `balls` |
| projected action | update |
| classification | `statistical_correction` |
| source revision | `af7729c3f1b4…13549` (matched during realization) |
| plan fingerprint | `74b6778103…921969` |
| stored digest | `3ab06ef31018f9694a6faebac8d595c5` |
| target digest | `939546c2f2c43a9db2a455613fac36ec` |

It recurred across a postgame cycle and a daily cycle at the **same source
revision and the same plan fingerprint**, which makes an incidental
between-request MLB revision unlikely — but does not by itself establish
authority.

The daily cycle around it was healthy: sync `success`, runner exit `0`,
publication verified at snapshot `326`, 97/97 games completed, 814 of 815 rows
unchanged, and **zero shadow writes on every counter**. The daily legacy writer
reported `logs_corrected: 0`. Realization reported 1 divergent and 1 unresolved
row and `all_projected_targets_realized: false` — the activation gate did its
job.

### What the code proves

There is exactly **one** canonical values builder
(`sync._game_log_values_from_stats`) and **one** planner
(`game_log_reconciliation.plan_row`). Both the box-score path and the player
game-log-split path use both. There is no second comparator, and the difference
is not a planner defect.

The mechanism is **source-shape-dependent comparability**:

> `correctable_fields` appends an optional statistic only when the source dict
> carries its key **with a non-null, non-empty value** (`stat_key_present`).

So a lane whose source omits `balls` — or sends it as `null` or `''` — never
compares it and can never correct it. **It is not found equal. It is never
looked at.** The stored value is preserved rather than clobbered, which is
correct behaviour for an absent optional stat, and is exactly why the asymmetry
was invisible.

Compounding it: the postgame writer processes only games without a
fully-processed marker, so it never revisits an already-complete row. Within the
correction horizon the only lane that re-examines an existing appearance is the
daily lane — and the daily lane reads the player game-log split.

### What the code does not prove

* whether the real player game-log split carries `balls` at all;
* whether box-score `balls` and any split `balls` are the same statistic;
* what the stored value is, or which source produced it;
* whether box-score `balls` is authoritative for the GameLog contract.

Those require the two live source payloads and the stored row. **This work had
no access to MLB and no access to production**, so the authority question is
recorded as unresolved rather than guessed.

### Decision at the time: Outcome E — unresolved

No writer changed. No correction vocabulary changed. `balls` was neither added
to nor removed from the governed set. The shadow failure stays active, because
it is reporting something real.

Silencing the difference would have made the lane green while leaving a
canonical field permanently uncorrectable by the only writer that revisits it.
Blessing it would have authorized a production write to real baseball data on a
value whose authority is unestablished.

### What was added instead

**`uncomparable_fields`** on every canonical plan, and on every projected
difference in the activation artifact. It names the governed optional fields a
source shape could not evaluate — turning an invisible asymmetry into evidence.
The next daily and postgame artifacts will state, per row, whether the other
lane could even see the field.

**`backend/scripts/inspect_gamelog_field_authority.py`** — a read-only audit
that collects the three values that settle it: the box-score line, the game-log
split, and the stored row, then runs both source shapes through the canonical
planner. It opens a read-only transaction, proves a write is refused,
fingerprints the row before and after, and rolls back. It reports exact values
only for `balls`, `strikes`, and `pitches_thrown` — enough to interpret the
statistic and nothing more.

Run it against production to resolve the authority question:

```bash
python scripts/inspect_gamelog_field_authority.py \
    --game-pk 824488 --pitcher-mlb-id 668716 --field balls \
    --output artifacts/field-authority/balls-824488.json
```

## Resolution — the box score is canonical for `balls`

The audit was run against production and returned the three values that settle
it:

| source | `balls` | `strikes` | pitches |
|---|---|---|---|
| completed-game box score | 19 | 26 | 45 |
| player game-log split | *absent* | 26 | 45 |
| stored row | 20 | 26 | 45 |

19 + 26 = 45. The box score's own accounting is internally coherent. The stored
row's is not: 20 + 26 = 46, against a stored pitch count of 45.

The split did not **contradict** the box score. It had nothing to say — the key
is not in the payload. Running both source shapes through the canonical planner
confirmed it: the box-score shape planned `update` with `changed_fields:
['balls']` and target 19; the split shape planned `unchanged` with
`uncomparable_fields: ['balls']`. The audit performed zero writes, its write
probe was refused, and the row fingerprint was identical before and after.

**Outcome A — the completed-game box score is canonical for `balls`, and the
correction-horizon writer cannot realize the field.** The stored value was
uncorrectable, not disputed: the only lane that revisits an existing appearance
within the horizon is the daily lane, and the daily lane reads the split.

## The repair — `PLAYER_SPLIT_PRIMARY_WITH_BOXSCORE_FALLBACK`

`backend/services/gamelog_source_authority.py` declares field authority in one
place, and the daily lane consults it:

1. A field the split supplies is reconciled from the split, exactly as before.
   **Fallback never overrides evidence that exists.**
2. A field the split omits or nulls is still reported through
   `uncomparable_fields` — absence is never treated as agreement.
3. For a field with an **explicitly approved** fallback rule, and only then, the
   completed-game box score may supply it.

The approved set has exactly one member: `balls`. Widening it is a governance
decision requiring its own production audit, its own semantic rule, and its own
validation — not merely the observation that the split omits a field.

### What `balls` is allowed to come from

| | |
|---|---|
| primary source | `player_game_log_split` |
| fallback source | `completed_game_boxscore` |
| required companions | `strikes`, `numberOfPitches` |
| validation rule | `balls + strikes == numberOfPitches` |

The rule **validates** the official triple; it never derives from it. A line
carrying strikes and pitches but no `balls` supplies nothing — `45 − 26` would
be inventing evidence the source did not state. A line whose accounting does
not add up (the stored 20/26/45 shape) is refused rather than reconciled.

### No second comparator, no second writer

The fallback changes what the lane can **see**, not what it may **do**. An
approved value is merged into a *copy* of the split's stats and then flows
through the same `_game_log_values_from_stats` → `plan_row` →
`_upsert_game_log_from_authoritative_values` path as every other field. There is
no direct assignment to `row.balls` anywhere.

Every safety rule upstream of the fallback stays upstream of it: a non-final
game is skipped before any fetch; a partial source line is still blocked; the
game-driven lane's `skip_game_pks` conflict prevention is unchanged.

### Refusals are named, never silent

`field_not_approved_for_fallback`, `split_supplies_field`, `game_not_final`,
`boxscore_unavailable`, `no_boxscore_pitching_line`, `field_absent_in_boxscore`,
`required_companion_absent`, `boxscore_values_inconsistent`,
`source_revision_missing`, `pitcher_identity_ambiguous`.

Two box-score lines claiming the same pitcher refuse rather than choose: if the
recipient of the correction is not established, writing either would be a guess
about whose appearance it is.

### Cost

One box-score read per **game** per run, cached and shared with the existing
leverage-index backfill — a game already read for leverage index is never read
again for the fallback. A row whose split already carries every approved field
costs nothing. `BOXSCORE_FALLBACK_FETCH_CAP` bounds the worst case; reaching it
is counted and reported, never absorbed. The daily ingestion budget is
unchanged.

### Provenance

A correction whose value came from the fallback records
`last_stat_correction_source = completed_game_boxscore_fallback`, not
`daily_game_log` — recording the lane's own source would credit an endpoint that
never carried the value. A correction the split itself drove keeps
`daily_game_log`, even on a row where the fallback also supplied a value that
turned out to agree.

### Observability

Every daily run reports the fallback, zeros included — an absent key would read
as "not instrumented", which is a different claim from "nothing was eligible":

`boxscore_fallback_eligible_rows`, `_fetches`, `_fetch_failures`,
`_applied_rows`, `_corrected_rows`, `_inserted_rows`, `_unchanged_rows`,
`_refused_rows`, `_fetch_cap_reached`, `_refusal_reasons`, `_records`,
`_records_truncated`.

Each record names game_pk, pitcher_mlb_id, the fields supplied, the difference
classification, the source authority and version, the source revision, the plan
fingerprint, the applied target-state digest, and the outcome. It carries no
source payload.

`uncomparable_fields` is unaffected: when the fallback refuses, the plan still
says the split never looked at the field, so a refused fallback can never read
as agreement.

### Impact planning before any production correction

`backend/scripts/plan_boxscore_balls_fallback_impact.py` enumerates the affected
set across the correction horizon **before** a writer runs, in two narrowing
stages: one box-score fetch per game to find rows the box score would actually
move, then one game-log fetch per *candidate pitcher* to rebuild the appearance
the way the daily lane would and run the real planner over it. It reports the
plan the writer would make, including any `changed_fields` outside the approved
set — which is what would block the repair as scoped.

Read-only and provably so: a read-only transaction, a refused write probe, a
horizon fingerprint before and after, and an explicit rollback. It reports what
it could not confirm rather than quietly narrowing.

```bash
python scripts/plan_boxscore_balls_fallback_impact.py \
    --days-back 7 --output artifacts/fallback-impact/balls-impact.json
```

Exit codes: `0` complete and in scope, `1` incomplete enumeration, `2` unsafe
(the horizon moved, or the session was not read-only), `3` a proposed change
touches a field outside the approved set.

### Contract versions did not move — deliberately

`reconciliation_plan_version` (3), `parity_contract_version` (4),
`innings_semantics_version` (2), `complete_plan_version` (1), and
`identity_plan_version` (1) are all unchanged, and there is no migration.

The planner's decision for a given `(existing, values, stats)` is byte-for-byte
what it was. What changed is what the daily lane *hands* the planner — a source
shape that now carries one more key. Bumping a plan or parity version would
invalidate every reviewed fingerprint on a contract that did not actually
change, which is the opposite of what those versions are for.

Field authority is versioned separately, on its own axis:
`authority_contract = player_split_primary_with_boxscore_fallback`,
`authority_version = 1`. Adding a field to the approved set moves that version
and nothing else.

### Effect on the daily realization proof

The divergent row that kept the activation gate FAILED was `balls` on game
`824488`: the game-driven lane projected it from the box score, and the daily
writer could not realize it from the split. With the fallback in place the daily
writer sees the same evidence the lane projected from, so the row is expected to
converge and the gate is expected to return to PASS on its own — without the
gate being loosened, and without the difference being suppressed.

If it does **not** converge, that is a second, different finding and must be
diagnosed as one. The gate stays exactly as strict as it was.

### Scope of this repair

Daily and postgame shadow modes are unchanged. No production correction was
executed as part of this work. `GAME_DRIVEN_INGESTION_MODE` remains `shadow` for
both cycles, backfill remains `off`, and automated write and authoritative modes
remain unapproved.

Before any production correction: run the impact planner, review its artifact,
confirm `database writes performed: 0`, confirm the affected set is finite and
fully enumerated, and confirm `every_change_is_approved_field_only` is true.

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
