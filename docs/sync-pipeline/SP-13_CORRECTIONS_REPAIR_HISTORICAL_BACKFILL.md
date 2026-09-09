# SP-13 — Corrections, Repair & Historical Backfill

## 1. Objective

SP-13 provides one durable orchestration path for targeted repair, bounded historical
backfill, full reconciliation, and explicit method/rule replay. It routes work to the
authoritative SP-04 through SP-12 services. It does not directly update canonical
baseball facts, derived intelligence, publications, or closure truth.

The governing correction path is:

source observation V1 → official source change → source observation V2 → owner-package
canonical reconciliation → SP-09 impact → SP-10 cohort → SP-11 publication → SP-12
closure re-evaluation.

## 2. Existing Repair Infrastructure Reused

Repository audit and disposition:

| Existing component | Disposition | SP-13 use |
| --- | --- | --- |
| `intraday_repair.py` and `run_intraday_repair.py` | MIGRATE LATER | Existing manual current-day compatibility path remains intact. |
| `source_correction_policies.py` | REUSE AS-IS | Existing model-specific replace/version/forbid policies remain canonical. |
| SP-01 `targeted_repair`, `backfill`, `full_reconciliation` runs | REUSE AS-IS | Root execution and correlation identity. |
| SP-02 queue, dedupe, leases, fencing | REUSE AS-IS | Planners, checkers, chunks, and owner work. |
| SP-03 observation lineage | REUSE AS-IS | All reacquisition happens through owner fetch paths. |
| SP-04 schedule worker | WRAP | Schedule/date repair jobs. |
| SP-05 roster and transaction workers | WRAP | Exact-date roster and one-day transaction chunks. |
| SP-06 pregame worker | MIGRATE LATER | Current context can be refreshed; historical announcement timing is not recreated. |
| SP-07 final-game worker | WRAP | Current and historical official final-game repair. |
| SP-08 live observations | DO NOT RECONSTRUCT | Historical live timing remains an explicit gap. |
| SP-09 impact plans | EXTEND | Explicit replay plans may exist without a fake source mutation. |
| SP-10 derived cohorts | EXTEND | Explicit method-version manifest overrides and historical non-publication mode. |
| SP-11 atomic publication | REUSE AS-IS | Current-state repair may publish only through its normal worker. |
| SP-12 closure ledger | WRAP | Previously closed affected dates are rechecked through SP-12. |
| Direct SQL and one-off data scripts | DEPRECATE LATER | Not part of the normal SP-13 runtime contract. |

Legacy repair and scheduled jobs are not removed or activated by this package.

## 3. Operational Modes

Controlled request modes are:

* `targeted_repair`: one baseball date and a small explicit game/team/source scope.
* `historical_backfill`: an explicit inclusive date range split into daily chunks.
* `full_reconciliation`: an explicitly bounded universe routed across existing owners.
* `method_replay`: unchanged canonical facts, explicit impact plans, and explicit method versions.
* `rule_replay`: unchanged canonical facts, explicit impact plans, and an explicit SP-09 rule version.

Replay is distinct from source backfill. It never creates a synthetic source observation
or source mutation.

## 4. Repair Request Contract

`repair_requests` contains the immutable requested scope and audit fields:

* UUID request key, deterministic request fingerprint, schema and plan versions;
* mode, status, scope type/JSON, inclusive baseball-date bounds, source domain;
* reason, requested by, trigger type, dry-run flag;
* requested impact-rule or per-domain method versions;
* correlation, root run/job, checker job;
* plan fingerprint/material, estimates, outcome, failure reason, lifecycle timestamps.

Statuses are `planned`, `running`, `blocked`, `completed`, `completed_partial`,
`failed`, and `cancelled`. A partial unique index collapses the same active request.
Once terminal, a deliberate repeat creates a new audit request while owner jobs remain
idempotent.

The service never edits the original scope, reason, bounds, or requested versions.
A materially different scope is a new request.

## 5. Repair Plan

`repair-plan-v1` is fingerprinted from the request fingerprint, exact date list,
owner package, scope, and dry-run state. It records closure status/version/fingerprint
at planning time and estimates:

* source fetches;
* dates/chunks;
* games and teams;
* likely impact plans, cohorts, and closure dates.

No broad owner work is dispatched before this plan exists.

## 6. Dry Run

Dry-run is the CLI default. It persists the request, deterministic plan, daily chunks,
scope estimates, and a zero-mutation outcome. It does not enqueue owner work, mutate
canonical data, create cohorts/publications, switch the current pointer, or alter
closure state.

It may inspect existing database authority. This v1 does not make speculative network
requests during dry-run; source diffs remain an owner-worker responsibility during an
explicit applied request.

## 7. Owner-Package Routing

| Repair domain | Owner path |
| --- | --- |
| `schedule` | SP-04 `FETCH_SCHEDULE` |
| `roster` | SP-05 `FETCH_ROSTER`; explicit team IDs are required |
| `transactions` | SP-05 `FETCH_TRANSACTIONS`, one baseball date per chunk |
| `pregame` | SP-06 for current supported context; historical announcement timing is withheld |
| `final_game` | SP-07 `RECONCILE_FINAL_GAME` for authoritative Final gamePk values |
| historical `live` | SP-07 final authority plus an explicit unsupported-live-history blocker |
| method/rule replay | SP-09 replay impact plan → SP-10 `PROCESS_DERIVED_INTELLIGENCE` |
| closed date | SP-12 `CHECK_BASEBALL_DATE_CLOSURE` after owner/downstream work |

SP-13 never issues runtime `UPDATE` statements against GameLog, roster membership,
Team State, snapshots, the current publication pointer, or closure fingerprints.

## 8. Source Reacquisition

Source repair jobs call the existing SP-03-aware owner workers. Existing matching
observations are reused by SP-03 fingerprint identity; changed official content creates
a linked source version. Failed or unavailable acquisition creates no fake empty
observation and cannot clear known-good authority.

## 9. Correction Flow

For a corrected Final game, SP-13 enqueues SP-07 with the exact gamePk and baseball
date. SP-07 revalidates Final, records boxscore/PBP observations, versions only changed
canonical facts, emits mutations, and hands them to SP-09. Descendant queue work is
included in repair progress so a request is not complete merely because SP-07 finished.

A no-change repair is successful: it may read source evidence but creates no canonical
mutation or forced downstream replay.

## 10. Historical Backfill

Every historical request requires explicit start and end dates. Targeted repair is
exactly one date. Standard backfill is limited to 31 inclusive days. A caller must set
the broad-scope confirmation flag beyond 31 days, and the absolute v1 limit is 366 days.
There is no unbounded default and no automatic season execution.

## 11. Chunking / Resumability

`repair_request_chunks` stores one daily chunk with deterministic key/order, owner,
scope, status, child job IDs, outcome, and lifecycle timestamps. Successful chunks are
not re-dispatched after interruption. Failed children do not cause successful chunks to
rerun. SP-02 job dedupe and owner game/team locks make overlapping repairs converge.

## 12. Roster / Transaction Backfill

Historical roster repair uses SP-05 exact-date official roster acquisition and requires
explicit team IDs; it never uses current `Pitcher.team_id` as historical membership.
Transactions use one-day windows so a large range cannot silently rely on a single
1000-row response. SP-05 retains its truncation-is-partial contract.

## 13. Final Game Backfill

Final-game chunks enumerate distinct ScheduledGame gamePk values and enqueue SP-07.
Only authoritative Final games qualify. GamePk identity keeps doubleheaders independent.
GameLog alone is never backfilled as authoritative history.

## 14. Pregame / Live Historical Limitations

Past probable-starter announcement timing generally cannot be reconstructed. A past
official game record cannot prove what BaseballOS would have observed at a particular
pregame time. Historical live timing is likewise observational evidence and is not
manufactured from final PBP. These requests end `completed_partial` with structured
`unsupported_historical_context` evidence where owner final authority can still run.

Unavailable source history remains unavailable, incomplete, or unsupported—never
filled from current values.

## 15. Method-Version Replay

A method replay clones the exact entity/domain/source-observation scope of explicitly
named SP-09 plans, links `repair_request_id` and `replay_from_plan_id`, and stores a
per-domain method-version override. SP-10 incorporates the override into its method
manifest and deterministic cohort fingerprint. The former cohort remains immutable.

## 16. Rule-Version Replay

Rule replay uses the same explicit plan scope and records the requested rules version.
It is an operator decision, not an automatic response to a code constant change. No
source mutation is fabricated.

## 17. Closed-Date Reopen

The repair plan freezes the pre-repair SP-12 closure identity. After all owner and
descendant work succeeds, SP-13 enqueues a closure check for every previously closed
date. SP-12 alone compares authoritative fingerprints, appends a `reopened` version
when truth changed, dispatches missing downstream obligations, and appends a later
`closed` version. SP-13 never edits closure evidence directly.

Repair completion waits for the closure check and a closed current state. A no-op repair
may retain the same closed version; a correction preserves V1 closed → reopened → V2
closed lineage.

## 18. Historical Publication Behavior

Replay plans set `publication_mode` deterministically:

* current-date replay: `current`; SP-10 may hand an eligible cohort to SP-11;
* prior-date replay: `historical`; SP-10 retains the immutable cohort but does not enqueue
  a current-pointer publication.

Source corrections on previously closed dates use the normal SP-07→SP-11 path and SP-11
remains the only service allowed to advance the current publication pointer.

## 19. Guardrails

* explicit date bounds are mandatory;
* 31-day default and 366-day absolute limits;
* targeted repair is one date;
* roster repair requires explicit teams;
* replay requires explicit impact-plan IDs and version intent;
* dry-run is the CLI default and `--apply` is required to dispatch;
* historical live and pregame timing are withheld rather than inferred;
* no automatic cron, season backfill, public write endpoint, or direct SQL repair path.

## 20. CLI / Operator Entry

The internal command is:

```text
python backend/scripts/run_sync_repair.py targeted --start-date YYYY-MM-DD --domain final_game --game-pk GAME_PK --reason "..."
python backend/scripts/run_sync_repair.py backfill --start-date YYYY-MM-DD --end-date YYYY-MM-DD --domain transactions --reason "..."
python backend/scripts/run_sync_repair.py replay --date YYYY-MM-DD --impact-plan-id PLAN_ID --method-version workload=workload-v2 --reason "..."
```

These commands only plan by default. Add `--apply` to enqueue work. Ranges beyond 31
days also require `--confirm-broad-scope`. The command sets `AUTO_SYNC=false` and exposes
no HTTP trigger.

## 21. Blockers / Partial Completion

Structured blockers are keyed by request, blocker type, entity, and retryability.
Controlled types include `source_unavailable`, `source_partial`,
`unsupported_historical_context`, `child_job_failed`, `closure_blocked`,
`publication_blocked`, `authority_conflict`, `missing_identity`, and `unknown`.

Retryable children keep the request running and schedule a 20-minute checker. Exhausted
required work fails the request. Permanent source limitations yield
`completed_partial`, never `completed`.

## 22. Concurrency / Fencing

The active-request partial unique index and SP-02 active dedupe collapse duplicate
planning and child work. PostgreSQL request-scoped advisory locks serialize checkers
for the same request while leaving unrelated requests independent. Planner/checker
workers heartbeat their SP-02 lease before state-changing phases; a stale token cannot
complete the job. Owner package locks remain authoritative for overlapping game/team
facts.

## 23. Audit / Metrics

Each request retains correlation ID, root SyncRun/job, plan fingerprint, estimates,
chunk/child IDs, blockers, closure baseline, and aggregate terminal counts. SP-01 run
outcomes record dispatched work and dry-run zero mutation. This is the SP-14 evidence
surface for plan size, progress, partial gaps, replay identity, and closure recovery.

## 24. Legacy Coexistence

The existing manual intraday repair and all current daily/nightly schedules remain
unchanged. SP-13 is dormant unless explicitly submitted. SP-14 owns parity certification,
activation decisions, and legacy retirement.

## 25. Explicit Non-Goals

SP-13 does not add baseball semantics, infer missing facts, create live history, perform
request-time repair, expose a frontend/admin API, run an automatic broad backfill,
change schedulers, directly publish, or remove legacy repair code.

## 26. SP-14 Handoff

SP-14 can certify one-game no-op/correction repair, bounded and resumable date backfill,
explicit method/rule replay, stale-worker safety, source limitation reporting, and
closed-date reopen/reclose from the durable request/chunk/blocker and SP-01/02/12 records.

## 27. Acceptance Checklist

* [x] Targeted repair, historical backfill, full reconciliation, and replay are distinct.
* [x] Requests, plans, chunks, blockers, estimates, and outcomes are durable.
* [x] Source/canonical work routes through SP-04 through SP-08 owners.
* [x] Downstream work routes through SP-09 through SP-12.
* [x] Dry-run cannot mutate or publish.
* [x] Backfill is explicitly bounded, chunked, and resumable.
* [x] Replay does not fake source mutations and preserves old cohorts.
* [x] Historical live/pregame timing is never fabricated.
* [x] Closed dates are re-evaluated by SP-12 with prior history preserved.
* [x] Active requests and child work are deduplicated and fenced.
* [x] No scheduler, frontend, production activation, or direct-write repair path changed.
