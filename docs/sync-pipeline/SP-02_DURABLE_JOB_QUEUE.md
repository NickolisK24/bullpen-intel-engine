# SP-02 Durable Job Queue

## 1. Objective

SP-02 extends BaseballOS's existing PostgreSQL `sync_jobs` substrate into the common durable execution engine beneath the Sync Pipeline. Work accepted through the canonical service is transactionally enqueued, active-deduplicated, priority ordered, claimed with a fenced lease, retried with bounded delay, recoverable after worker loss, and retained in a visible terminal state. It does not activate a worker, move a production sync path, or change baseball/publication behavior.

## 2. Existing Infrastructure Reused

| Existing concept | Disposition | SP-02 contract |
|---|---|---|
| `SyncJob` | **EXTEND / WRAP** | Remains the one durable executable-work model. No V2 or broker queue was added. |
| `services/sync_jobs.py` | **EXTEND** | Becomes the canonical enqueue/claim/lease/retry boundary while retaining its checkpoint compatibility API. |
| `SyncRun` | **REUSE AS-IS** | Optional `sync_run_id` associates work with its logical operation; job transitions never finalize a run. |
| `SyncFailure` | **REUSE AS-IS** | Remains domain/entity failure evidence. Queue attempt errors stay on the job/attempt unless orchestration deliberately creates a domain failure. |
| CU final-game obligations | **DO NOT TOUCH / MIGRATE LATER** | Existing observation-fingerprint identity, stage checkpoints, retries, and supersession continue unchanged. |
| `GameIngestionWorkItem` | **DO NOT TOUCH** | Remains the final-game canonical completeness checkpoint, not a general queue row. |
| Writer/advisory locks | **REUSE AS-IS** | Continue protecting canonical/publication writers. Queue row locks protect only queue ownership. |
| Schedulers and command wrappers | **DO NOT TOUCH** | No cadence, daemon, cron, or routing change occurs in SP-02. |

The legacy permanent uniqueness tuple `(job_name, scope_key, product_date)` is replaced by active-only `dedupe_key` enforcement. Existing rows are preserved with a null dedupe key. Current CU/checkpoint writers continue their established identity checks until later migration.

## 3. SyncRun vs SyncJob Boundary

`SyncRun` answers what logical synchronization operation happened, why, for which baseball date/entity cohort, and with what domain outcome. `SyncJob` answers what executable work exists, when it is eligible, who owns it, how many claims occurred, and whether automatic execution can continue.

A job may reference one run; one run may have many jobs. A job may also reference a parent job for execution causality. Parent deletion uses `ON DELETE SET NULL` and cannot erase child work. Queue completion, retry, and death do not mutate `SyncRun`. `job_state_summary(sync_run_id)` exposes counts for later orchestration without deciding run outcome.

## 4. Job Schema

Existing fields retained: ID, `job_name`, family, lane, scope key, product date, status, attempts/max attempts, start/completion/heartbeat/duration, error fields, `details_json`, run linkage, and timestamps.

SP-02 adds:

- `scope_type`: queryable league/date/game/team/pitcher/source-domain routing.
- `payload_schema_version`: version for the existing `details_json` work payload.
- `dedupe_key`: caller-owned logical active-work identity, including future source version/fingerprint where applicable.
- `priority`: integer 0–1000; lower values execute first; default 100.
- `first_available_at`: immutable initial eligibility time; `available_at`: current/retry eligibility time.
- `claimed_at`, `lease_until`, `worker_id`, `claim_token`: fenced lease state.
- `dead_at`: exhausted/non-retryable terminal time.
- `result_json`: bounded result separate from the preserved original payload.
- `parent_job_id`: optional execution lineage.

`sync_job_attempts` is a compact append-only row per claim: attempt number, worker, fencing token, claimed/lease/finished times, outcome, retryability, and error class/message.

## 5. Job Lifecycle

Canonical queue lifecycle:

```text
pending -> running
retry_wait -> running
running -> succeeded
running -> retry_wait
running -> dead
running -> pending       (explicit release)
running -> running       (expired lease reclaimed under a new fencing token)
```

`pending`, `running`, and `retry_wait` are active. `succeeded` and `dead` are terminal. Terminal jobs cannot be heartbeated, reclaimed, completed again, or revived by the canonical API.

For production safety, existing checkpoint-only `failed` and `skipped` values remain supported by the legacy helper surface. Existing `failed` rows remain retryable up to their current maximum; `skipped` remains an explicit completed/superseded checkpoint. The canonical engine never emits either compatibility value.

## 6. Job Type Vocabulary

`JobType` is the backend source of truth. Future-ready types are `fetch_schedule`, `fetch_game`, `reconcile_final_game`, `fetch_roster`, `fetch_transactions`, `fetch_statcast`, `rebuild_pitcher`, `rebuild_team`, `build_read_models`, `publish`, `reconcile_date`, and `targeted_repair`.

Established executable/checkpoint identities are also recognized: `workload_evidence`, `composed_reads`, `legacy_read_reconciliation_audit`, `backtest_refresh`, `continuous_final_game_reconciliation`, and `continuous_game_replay`. Database storage remains strings for migration flexibility; `enqueue_job` rejects unknown types.

## 7. Priority Contract

Priority is bounded from 0 through 1000. Lower number means higher priority. Claim order is:

1. priority ascending;
2. effective `available_at` ascending;
3. creation time ascending;
4. job ID ascending.

SP-02 defines ordering mechanics only. Later packages choose domain priorities.

## 8. Dedupe Contract

Every canonical enqueue requires a non-empty `dedupe_key`. PostgreSQL and SQLite enforce one row per non-null key while status is `pending`, `running`, or `retry_wait` through partial unique index `uq_sync_jobs_active_dedupe_key`.

`enqueue_job` first returns an existing active row when present. A nested transaction/savepoint handles two racing inserts: the database chooses the winner and the loser returns that active row. No in-memory set is authoritative.

Terminal `succeeded`/`dead` rows release the key, so future work can reuse a logical identity. A future source adapter should include source domain, entity, and source version/fingerprint when different versions may legitimately coexist, for example `FETCH_GAME:777123:<fingerprint>`.

## 9. Claiming Contract

`claim_next_job(worker_id, ...)` runs in one database transaction. It selects only the new `sync_pipeline` lane, so installing SP-02 cannot consume established `internal` CU/checkpoint rows. Within that lane its eligible query selects:

- `pending` or `retry_wait` with effective availability at or before now; or
- `running` with an expired non-null lease.

It orders by the priority contract and issues `SELECT ... FOR UPDATE SKIP LOCKED`. Concurrent workers skip a row locked by another transaction and can claim different work without a queue-wide lock. Terminal and future-available rows are never selected. Optional validated job-type filtering is supported. No polling loop or sleep exists in the service.

Indexes `ix_sync_jobs_claim_ready(lane, status, priority, available_at, created_at, id)` and `ix_sync_jobs_lease_expiry(lane, status, lease_until)` support the two eligibility branches. The active-dedupe partial index supports enqueue conflict resolution. At BaseballOS scale, correctness and bounded index count take precedence over more specialized indexes.

## 10. Lease Contract

Each claim writes worker ID, latest claim time, lease expiration, and a new UUID fencing token. Attempt count increments on claim and a matching attempt row is appended. Completion clears current ownership/token/expiry but retains the latest claim time; the attempt ledger retains every prior claim. Default lease duration is five minutes. Live leases are not stealable; expired leases are independently reclaimable without heartbeat correctness.

Every completion/retry/release operation locks the row and requires all of:

- status is `running`;
- worker ID matches;
- fencing token matches the current claim;
- lease has not expired.

A prior worker therefore cannot settle work after reclamation, even if it resumes later.

## 11. Heartbeat Contract

`heartbeat_job` applies the same owner/token/live-lease checks. It may extend only the current attempt. The default extension is five minutes and the default hard boundary is one hour from that attempt's claim. Service inputs are bounded to 24 hours; heartbeat can never revive expired or terminal work. The attempt row's lease time advances with the job row.

## 12. Retry/Backoff Contract

Attempts increment only when execution is claimed. A retryable failure before exhaustion moves the job to `retry_wait`, clears ownership, retains the error, and sets `available_at` using exponential delay:

```text
min(3600 seconds, 30 seconds * 2^(attempt - 1)) with deterministic ±20% jitter
```

The deterministic jitter depends on job ID and attempt number, so retries spread without making tests or incident reconstruction nondeterministic. A future adapter may provide `retry_after_seconds`; the queue caps it at six hours. HTTP request retries remain source-adapter behavior and are not moved into this layer.

## 13. Dead/Exhausted Contract

A non-retryable error or failure at `max_attempts` transitions directly to `dead`. `dead_job` is the explicit non-retryable completion boundary; `retry_job(..., retryable=False)` provides the same guarded transition for execution wrappers. An expired running job already at its maximum is also terminalized before another claim. The job is never deleted: payload, run/scope/parent identity, attempt count, error class/message, result, timestamps, and all attempt rows remain queryable.

## 14. Attempt Accounting

An append-only attempt table is justified because mutable job counters cannot prove crash recovery or prior lease ownership. One compact row is created per claim and uniquely keyed by `(sync_job_id, attempt_number)`. Outcomes include `succeeded`, `retry_wait`, `dead`, `released`, and `lease_expired`. This preserves debugging and duration/owner history without duplicating payloads.

## 15. Crash Recovery

Lease expiration is sufficient recovery authority:

1. Worker A claims and receives token A.
2. A disappears and its lease expires.
3. Worker B locks the row, closes A's attempt as `lease_expired`, increments attempts, and receives token B.
4. B succeeds and clears ownership.
5. A's later completion with token A is rejected.

The focused PostgreSQL suite proves active dedupe, row-lock skipping, distinct concurrent claims, lease reclaim, and stale-token rejection.

## 16. Existing CU Work Relationship

CU observation work remains alongside the canonical queue API on the same `SyncJob` model. Its payload schema, observation-fingerprint key, stage-local attempts, supersession rules, checkpoint helpers, and cycle/advisory locks are unchanged. `GameIngestionWorkItem` remains separate because it is canonical reconciliation completeness evidence rather than generic executable work.

This is deliberate compatibility, not a second queue. Later CU activation/migration can call the canonical lease API only after parity proves that stage-local attempt behavior and publication checkpoints survive. Existing writer locks remain necessary after queue claim because a job lease does not authorize concurrent canonical/publication mutation.

## 17. Database/Index Design

Migration `c4f8a2d7e6b1` follows SP-01 head `b5e7c1d9a4f2`. It preserves every existing row, adds nullable routing/lease fields plus safe priority default, replaces permanent tuple uniqueness with active-dedupe uniqueness, and creates attempt history. It performs no status guesses or historical job rewrite.

The downgrade removes SP-02 fields/table/indexes and restores the former tuple constraint. It is safe before new duplicate terminal generations exist; after such generations exist, operators must reconcile those rows before downgrading because the older schema cannot represent them.

## 18. Representative Integration

`run_next_job(worker_id, handlers, ...)` is a one-job internal execution boundary. It claims once, dispatches through an explicit handler registry, succeeds on return, records retry/death on exception, and re-raises the original exception. It contains no loop and has no scheduler, CLI, application-start, or production entry point. Tests exercise it only; production daily, postgame, repair, and CU routes remain unchanged.

## 19. Explicit Non-Goals

SP-02 does not add a scheduler, daemon, Render service, GitHub cadence, adaptive polling, source endpoint, Savant acquisition, HTTP retry change, fingerprint/version primitive, canonical baseball mutation, workload/Team State/arm-read/role change, publication behavior, API payload, frontend code, dashboard, or legacy retirement. It does not route existing production synchronization through the queue and does not implement SP-03.

## 20. SP-03 Handoff

SP-03 may place source domain/entity/version or fingerprint references inside the versioned payload and dedupe key. `details_json` remains the immutable-enough work request for one job; `result_json` is separate. SP-03 owns observation identity, payload artifacts, fingerprints, completeness, corrections, source fetch accounting, and adapters. It should not embed queue lease/retry state in source observations.

## 21. Acceptance Checklist

- [x] Existing `SyncJob` is the one durable queue model.
- [x] `SyncRun` and job lifecycle remain separate.
- [x] Enqueue is transactional and validates type, scope, payload version, priority, attempts, availability, run, parent, and dedupe identity.
- [x] Active duplicates are prevented by a partial unique database index, including concurrent PostgreSQL enqueue.
- [x] Future availability and deterministic priority ordering are durable.
- [x] PostgreSQL claim uses `FOR UPDATE SKIP LOCKED`.
- [x] Concurrent workers cannot own one live lease and may claim separate rows.
- [x] Owner plus fencing token protects heartbeat, completion, retry, and release.
- [x] Expired work is reclaimable; stale completion is rejected.
- [x] Retry/backoff is bounded and attempts are counted.
- [x] Non-retryable/exhausted work remains durably `dead`.
- [x] Attempt/lease history is append-only and compact.
- [x] Existing CU obligations, canonical checkpoints, and writer locks are preserved.
- [x] No production execution path or schedule is activated.
- [x] No acquisition, baseball/publication semantics, API, or frontend behavior changes.
- [x] SQLite service/migration tests and PostgreSQL concurrency/compatibility tests pass.
