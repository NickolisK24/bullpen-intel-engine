# SP-12 Morning Reconciliation and Nightly Historical Closure

## 1. Objective

SP-12 adds a dormant, bounded safety net around the incremental Sync Pipeline. Morning planning proves the official 30-club denominator and records durable work for existing owner packages. Nightly checking decides whether one official baseball date is historically complete, records structured blockers, and preserves every close/reopen transition. It performs no acquisition, canonical mutation, derived intelligence, or publication itself.

## 2. Existing Orchestration Reused

The existing daily, postgame, and morning `run_due_sync.py` lanes remain production authority. SP-12 reuses SP-01 runs, SP-02 queue dedupe/fencing, SP-04 schedule state, SP-05 roster/transaction workers, SP-06 pregame planning, SP-07 final versions, SP-09 impact plans, SP-10 cohorts, and SP-11 publications. CU obligations and legacy snapshots remain unchanged.

Reuse map: existing workers and models are **REUSE AS-IS**; missing-obligation detection is **WRAP**; the legacy scheduled coordinators are **DO NOT TOUCH**; activation and retirement are **DEFER TO SP-14**; arbitrary repair/backfill is **DEFER TO SP-13**.

## 3. Morning Reconciliation Contract

`plan_morning_reconciliation()` obtains `/teams?sportId=1`, requires exactly 30 unique MLB team IDs, creates one `morning_reconciliation` SyncRun with league plus 30 team scopes, and enqueues:

* one date-grain `fetch_schedule`;
* 30 existing `fetch_roster` jobs (each SP-05 job obtains both active and 40-man authority);
* one bounded `fetch_transactions` job for D-2 through D;
* missing SP-07 final reconciliations in the 14-day correction lookback;
* SP-06 pregame work already due for D;
* missing SP-09, SP-10, or SP-11 handoffs whose durable upstream facts already exist.
* a prior-date closure check plus checks for existing closure records in the 14-day correction lookback.

It then exits. Child execution is never inline.

## 4. Nightly Closure Contract

`check_baseball_date_closure(D)` evaluates one date under a date-scoped PostgreSQL advisory lock. Closure requires every discovered game resolved, every Final backed by the current complete-core SP-07 version, a successful transaction window covering D, and every existing final mutation carried through required SP-09, SP-10, and SP-11 stages. Missing stages become structured blockers and targeted owner jobs.

## 5. Daily Closure Model

`baseball_date_closures` is the current projection. It stores game/roster/transaction/job counts, publication, source data-through, next check, current fingerprint/version, metrics, and lifecycle timestamps. `baseball_date_closure_versions` is append-only close/reopen history. `baseball_date_closure_blockers` is the queryable current blocker set.

No migration backfills or guesses historical closure.

## 6. Closure/Reopen Lifecycle

Statuses are `open`, `checking`, `blocked`, `closed`, `reopened`, and `failed`. The service atomically evaluates then persists one state. A first complete decision appends a `closed` version. If a closed date's authoritative fingerprint changes, the next check appends `reopened` even if the replacement evidence is otherwise complete; a subsequent check appends a new `closed` version. Predecessor links preserve V1 closed -> V2 reopened -> V3 closed.

## 7. Game-State Resolution Matrix

| SP-04 operational state | Closure result |
| --- | --- |
| `final` | Resolved only with current SP-07 complete-core authority |
| `postponed` | Resolved non-final disposition |
| `cancelled` | Resolved non-final disposition |
| `scheduled`, `pregame`, `live`, `delayed`, `suspended`, `unknown` | Blocking |

Official shortened finals are accepted through SP-07; inning count is not a closure rule. Suspended games block and receive the slow recheck. Doubleheaders remain separate by gamePk. A complete zero-game date is closable.

## 8. Roster/Transaction Requirements

Morning always schedules all 30 team roster authorities. Nightly records the distinct dated roster snapshot coverage without claiming unavailable intraday precision. A latest transaction sync window spanning D must be `success`; `partial` (including the SP-05 1000-row truncation signal), `failed`, or absent blocks closure. A targeted bounded transaction retry is enqueued.

## 9. Final Reconciliation Requirements

Every schedule-Final game needs one current `final_game_versions` row whose core completeness is `complete`. Missing authority blocks and enqueues the established `reconcile_final_game` job. Optional PBP that is partial/unknown/failed is recorded as `optional_enrichment_outstanding` but does not falsify or block valid core closure.

## 10. Downstream SP-09/10/11 Requirements

Each existing final mutation must have an SP-09 mutation reference. A plan with derived domains must have a complete SP-10 cohort and published SP-11 publication. Zero-domain plans need no manufactured cohort/publication. Missing steps block closure and are re-enqueued through `process_canonical_impact`, `process_derived_intelligence`, or `publish_derived_cohort` with their established versioned payloads and dedupe keys.

## 11. Publication-at-Closure Contract

The closure references the newest published SP-11 generation required by its final mutation plans. One later coherent publication may satisfy multiple games; closure does not count publications per game. Source data-through is the maximum publication/source-window evidence timestamp, never the closure execution time.

## 12. Blockers

Controlled blocker types are `unresolved_game`, `final_reconciliation_missing`, `source_partial`, `transaction_partial`, `pending_impact`, `pending_derived_cohort`, `pending_publication`, and `failed_required_job`. Each identifies its entity and structured detail. External waiting is `blocked`, not an assertion that the baseball date failed.

## 13. Recheck Policy

`baseball-date-recheck-v1` schedules one future `check_baseball_date_closure` job after 20 minutes for ordinary blockers and after 6 hours for a suspended game. The generation key includes the closure version and due instant, so the currently executing job cannot suppress its successor. No worker busy-waits.

## 14. Correction Lookback

Morning scans only D-14 through D plus explicitly open/reopened date work. It never scans a season. Broader repair/backfill belongs to SP-13.

## 15. Timezone/Baseball Date

Closure identity is `ScheduledGame.game_date`, sourced from MLB official date. Operational timestamps are UTC-naive under the existing backend convention. West Coast completion after Eastern or UTC midnight never moves the game to a different closure date.

## 16. Queue/Dedupe

Top-level types are `run_morning_reconciliation` and `check_baseball_date_closure`, both payload schema v1. Morning dedupe is one active generation per date. Closure rechecks use a date/version/due-time generation. All child work uses existing job types, priorities, payload versions, active partial uniqueness, retry policy, leases, and fencing.

## 17. Concurrency/Fencing

The queue prevents duplicate active orchestrators. Closure additionally takes `pg_advisory_xact_lock(612000000 + YYYYMMDD)` and locks the date row, allowing different dates to proceed concurrently. A lease fence runs immediately before state mutation. Database uniqueness protects one current date row and one version number. The close decision, blockers, metrics, history event, and next job are one transaction.

## 18. Metrics

Current closure evidence includes expected/resolved/final/reconciled games, expected/reconciled teams, transaction completeness, pending/dead jobs, optional enrichment, blocker count, time to closure, reopen count, child repair IDs, publication ID, and source data-through. Morning run outcomes retain all 30 IDs, child job IDs, bounded game count, and lookback policy.

## 19. Legacy Coexistence

No Render or GitHub schedule changes exist. Legacy daily, postgame, and morning lanes remain active and authoritative. SP-12 services and top-level jobs are dormant unless explicitly invoked. Existing CU work, legacy publications, and current readers are not retired or redirected.

## 20. Intended Production Cadence

After SP-14 certification, intended use is one morning plan before the normal usage window and one prior-date nightly check after most games, followed by durable rechecks. Render remains intended primary execution authority and GitHub fallback/verifier. SP-12 grants no activation authority.

## 21. Explicit Non-Goals

No baseball formula or public semantic changes; no frontend/admin dashboard; no new source, endpoint, or acquisition behavior; no direct canonical/derived/publication execution; no full-history scan; no generalized repair/backfill; no scheduler activation; no legacy retirement.

## 22. SP-13/SP-14 Handoffs

SP-13 may consume blocker/date/version evidence for arbitrary historical replay, method-version rebuilds, and deep repairs. SP-14 must certify natural 30-team coverage, closure latency, correction reopen/reclose, scheduler authority, PostgreSQL concurrency/fencing, parity, and legacy retirement readiness before activation.

## 23. Acceptance Checklist

* [x] Morning denominator is exactly 30 official MLB clubs.
* [x] Existing schedule, roster, transaction, final, pregame, impact, cohort, publication, and cache primitives are orchestrated rather than replaced.
* [x] Closure is official-baseball-date and gamePk based.
* [x] Final, postponed, cancelled, suspended, delayed, and zero-game semantics are explicit.
* [x] SP-07 core, transaction completeness, SP-09, SP-10, and SP-11 gates fail closed.
* [x] Optional PBP incompleteness remains visible without becoming fake core failure.
* [x] Closure fingerprint excludes operational queue churn and detects authority changes.
* [x] Closed dates reopen and preserve predecessor history.
* [x] Targeted jobs and bounded rechecks are durable and deduplicated.
* [x] Date-scoped locking, queue leases, and stale-worker fencing protect decisions.
* [x] Migration is additive and performs no guessed backfill.
* [x] Legacy schedules remain active; new orchestration remains dormant.
* [x] No public semantics, frontend, acquisition, scheduler, or main-branch behavior changes.

The key contract is reproducible: a closed date whose current SP-07 version changes receives a new closure fingerprint, becomes reopened, dispatches only missing owner work, references the resulting coherent publication, and closes again without deleting its original close record.
