# SP-01 Sync Control Plane

## 1. Objective

SP-01 gives BaseballOS one durable vocabulary and lifecycle for identifying a synchronization operation: what ran, why it ran, the baseball date and entities it owned, its current stage, its causal lineage, its outcome, and its terminal status. It extends the established `sync_runs` and `sync_failures` records and does not change baseball acquisition, canonical baseball facts, publication meaning, or production scheduling.

## 2. Existing Architecture Reused

The implementation converges on existing operational infrastructure instead of adding a parallel orchestration system.

| Existing concept | SP-01 disposition | Reason |
|---|---|---|
| `SyncRun` | EXTEND and WRAP | It is already the durable execution envelope used by daily, postgame, repair, publication, and Continuous Updates paths. |
| `sync_metadata.py` | WRAP | Existing callers keep their compatibility API while lifecycle writes delegate to the canonical control-plane service. |
| `SyncFailure` and dead-letter records | EXTEND | Existing failure history remains; optional classification, stage, domain, and retryability make new failures queryable. |
| `SyncJob` | REUSE AS-IS / DO NOT TOUCH | Its existing `sync_run_id` is the attachment point for SP-02. Claiming, retry, lease, and dead-letter behavior remain SP-02 scope. |
| CU work obligations and execution checkpoints | REUSE AS-IS | They already preserve bounded work and causal evidence. SP-01 only annotates the enclosing run. |
| Game fingerprints and observation state | DO NOT TOUCH | Universal source observations and fingerprints belong to SP-03. |
| Publication snapshot and CU publication identifiers | REUSE AS-IS | They remain the publication authorities. `publication_id` is only a control-plane link. |
| Writer guards and advisory locks | REUSE AS-IS | SP-01 neither changes concurrency authority nor creates queue semantics. |

## 3. Control-Plane Vocabulary

`backend/services/sync_control_plane.py` is the backend source of truth. Values are Python string enums, stored as strings for additive migration safety and serialized using their stable lowercase values. Existing `success`, `partial`, `failed`, and established stage strings remain compatible.

The controlled categories are `RunType`, `TriggerType`, `RunStatus`, `RunStage`, `ScopeType`, `SourceDomain`, and `FailureClass`. Source domains cover identity, schedule, roster, transactions, pregame, game/live feeds, boxscore, play-by-play, Statcast, workload, performance, organizational depth, Team State, read models, publication, operations, and multi-domain runs. The service rejects unknown values before persistence. There are no frontend copies or database-native enums.

## 4. SyncRun Lifecycle

The supported lifecycle is:

`PENDING -> RUNNING -> SUCCESS | PARTIAL | FAILED | CANCELLED`

Creation and start are separate operations, although compatibility paths may create directly in `RUNNING`. `stage` is independent of `status`, so a run can end as `FAILED` while preserving the stage at which it failed. The general stages are `pending`, `started`, `acquire`, `normalize`, `canonicalize`, `impact`, `derive`, `snapshot`, `publish`, `reconcile`, and `complete`. Established BaseballOS stages remain recognized during incremental convergence.

Terminal finalization is idempotent. Once terminal, a repeated completion or failure call returns the existing record and does not replace its status, stage, or completion timestamp. Stage recording remains available to established publication paths whose compatibility lifecycle records publication before subsequent internal enrichment stages finish.

## 5. Run Types

The representational contract supports every planned lane without activating it:

| Class | Run types |
|---|---|
| Production lanes | `schedule_game_state`, `roster_transactions`, `pregame_context`, `live_game`, `final_game_reconciliation`, `incremental_intelligence`, `publication`, `morning_reconciliation`, `nightly_finalization` |
| Operational modes | `targeted_repair`, `backfill`, `full_reconciliation` |

These names identify an execution envelope. They do not imply that the corresponding later-package behavior exists yet.

## 6. Trigger Types

Stable trigger values are `scheduled`, `game_status_change`, `game_final`, `roster_change`, `transaction`, `source_change`, `manual`, `repair`, `backfill`, `reconciliation`, `retry`, and `parent_run`. Existing scheduled and GitHub-scheduled sources normalize to `scheduled`; manual sources normalize to `manual`. A trigger says why a run exists, not what work it performs.

## 7. Scope Model

Queryable entity scope is stored in the small normalized `sync_run_scopes` association table at grain `(sync_run_id, scope_type, scope_key)`. Supported types are league, game, team, pitcher, and source domain. The unique constraint makes repeated scope attachment idempotent, and the `(scope_type, scope_key, sync_run_id)` index answers operational questions such as “which run touched BAL or gamePk 777001?” without JSON scans.

`SyncRun.baseball_date` is a separate nullable, indexed date. Integrated paths use the BaseballOS product/schedule date rather than deriving it from UTC `created_at`; genuinely cross-date or reference operations may leave it null. Scope keys are strings so MLB numeric identifiers and stable future domain keys share one simple representation. Pitcher scope uses MLBAM identity where the integrated path already owns that identity.

League-wide and bounded entity scope can coexist. Outcome counts are summaries and never substitute for entity scope.

## 8. Parent/Child / Correlation Model

`parent_sync_run_id` is a queryable self-reference with `ON DELETE SET NULL`; deleting a parent cannot cascade-delete execution history. Children created through the service must reference an existing parent and inherit its correlation identifier unless explicitly supplied. The service does not expose a parent-update operation, preventing cycles through normal application behavior.

Every new run receives a UUID correlation identifier. This is execution correlation only. It does not replace SP-10 snapshot-cohort identity or any existing publication identity.

## 9. Outcome/Counters

The durable outcome contract includes source reads, source changes, canonical mutations, affected game/team/pitcher counts, downstream work created, warning count, zero-mutation status, publication link, and a compact JSON outcome summary. Counters are non-negative and default to zero. `outcome_json` is for bounded lane-specific summaries, not primary query scope, source payloads, or arbitrary workflow state.

Legacy counters remain intact because current monitoring and public freshness code consume them. SP-01 does not reinterpret those fields.

## 10. Zero-Mutation Semantics

A checked source with no canonical change is successful work:

```text
source_reads > 0
source_changes = 0
canonical_mutations = 0
zero_mutation = true
status = success
```

The explicit `zero_mutation` flag is set whenever canonical mutation count is recorded, including repair and CU no-change paths. Missing acquisition must never be encoded as zero workload or zero mutations merely by default; future integrations must set the flag only after they possess authoritative outcome evidence.

## 11. Partial/Failure Semantics

`partial` is terminal and successful enough for existing freshness behavior, while explicitly distinguishing optional-domain degradation from complete success. `SyncFailure` can now associate a failure with run, stage, source domain, entity, broad class, and optional retryability. Supported classes are source, timeout, rate limit, validation, canonicalization, derivation, publication, database, concurrency, and internal.

This is classification and lineage only. Domain-specific fail-closed/degraded rules remain with their owning packages, and SP-02 owns retry mechanics. The direct service raises persistence and validation errors to its caller. The legacy `sync_metadata` wrapper retains its established best-effort telemetry behavior so an observability write does not replace the original synchronization exception.

## 12. Database Changes

Migration `b5e7c1d9a4f2` is additive and follows `e8a4c2f9b1d6`.

- `sync_runs` gains nullable vocabulary, baseball-date, source-domain, parent, correlation, and publication-link fields; non-null zero-default outcome counters; `zero_mutation`; and compact `outcome_json`.
- `sync_run_scopes` adds normalized queryable scope with a uniqueness constraint and lookup index.
- `sync_failures` gains nullable failure class, stage, source domain, and retryable fields.
- New indexes cover run type/time, trigger, baseball date, correlation, parent, source domain, scope lookup, failure run/stage, and failure class.

Existing rows remain valid with nullable new vocabulary fields and zero-default counters. No data rewrite, destructive change, or database-native enum is introduced. The downgrade removes only SP-01 additions.

## 13. Service Boundary

New SP code should use `sync_control_plane` to create/start a run, mark its stage, add queryable scope, record outcome, associate a failure, and finalize it. Operations participate in the caller's transaction when `commit=False`. Completion is safe to repeat. Invalid vocabulary and negative counters fail explicitly.

Existing code may continue through `sync_metadata.start_sync_run`, `set_sync_stage`, and `finish_sync_run`; those functions now delegate to the same service. New code should not mutate `SyncRun` ad hoc except where an established atomic publication transaction must bind its already-created snapshot before commit.

## 14. Existing Paths Integrated

The bounded proof integrations are:

1. Daily sync opens `full_reconciliation` with scheduled/manual trigger, product baseball date, league/domain scope, and durable outcome counters.
2. Postgame refresh opens `final_game_reconciliation` with its slate baseball date, exact completed-game and participating-team scope, source-domain scope, and publication/outcome linkage.
3. Continuous Updates opens `live_game` for chain modes, records source-change trigger, affected team/pitcher scope, durable downstream-work and publication counts, and zero-mutation success.
4. Intraday roster repair opens `targeted_repair`, records affected team/MLBAM pitcher scope, and now records an ordinary no-change audit as successful zero-mutation work without acquiring the publication writer lock.

All four continue to call their existing baseball services in their existing order.

## 15. Existing Paths Deferred

Later packages should migrate remaining CLI commands, backfills, one-off repairs, roster-only jobs, schedule discovery, pregame operations, standalone publication, nightly/morning closure, and correction tooling as those lanes gain owners. Existing `SyncJob`, `GameIngestionWorkItem`, failure, fingerprint, snapshot, and publication-cohort records remain authoritative in the meantime. A mass rewrite is intentionally deferred.

## 16. Explicit Non-Goals

SP-01 does not add or modify MLB/Statcast acquisition, source observations, fingerprints, canonical baseball schemas, Team State, arm reads, workload logic, roles, What Changed, publication semantics, frontend payloads, UI, schedules, Render services, GitHub cadence, adaptive polling, or Continuous Updates activation. It does not retire a legacy entry point and does not implement a workflow engine or queue.

## 17. Tests

Focused tests cover vocabulary validation, pending/start/stage/terminal lifecycle, baseball date, every scope category, uniqueness and lookup indexes, successful zero mutations, partial results, classified failure association, parent-child correlation and deletion behavior, terminal idempotence, and compatibility through `sync_metadata`. Existing daily, postgame, CU, repair, job, and sync-status suites exercise the representative wrappers. Migration validation uses the repository migration chain and production-style upgrade command.

## 18. SP-02 Handoff

SP-02 owns job enqueueing, claiming, leases, retries, backoff, priority, dedupe, crash recovery, and dead-letter behavior. It should continue attaching each durable job to its execution envelope through the existing nullable `sync_jobs.sync_run_id` foreign key. A parent run may create child runs for separately meaningful operations; individual queue attempts should not create ad hoc alternate run vocabularies. Job status and run status remain distinct: a job explains execution mechanics, while a run explains the meaningful synchronization operation and its domain outcome.

SP-02 should decide exactly when a queued operation creates its pending run and how retries reuse or relate run envelopes. It must preserve SP-01 terminal idempotence and correlation lineage rather than embedding queue state in `outcome_json`.

## 19. Acceptance Checklist

- [x] One backend-owned controlled vocabulary exists.
- [x] Existing `SyncRun`, `SyncFailure`, `SyncJob`, CU, fingerprint, and publication concepts are reused.
- [x] All SP production lanes and operational modes are representable.
- [x] Trigger, baseball date, status, stage, source domain, and queryable entity scope are durable.
- [x] Parent-child causality and execution correlation are durable without parent-delete history loss.
- [x] Outcome counters, publication linkage, zero-mutation success, partial completion, and classified failure association are representable.
- [x] Completion is idempotent and existing compatibility callers remain supported.
- [x] Daily, postgame, CU, and manual repair paths provide bounded integration proof.
- [x] Migration is additive and preserves existing rows.
- [x] Scheduling, acquisition, baseball semantics, publication semantics, and frontend behavior are unchanged.
- [x] Queue mechanics are explicitly deferred to SP-02.
