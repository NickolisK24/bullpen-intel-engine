# CU-08S — Governed Single-Game Final-Observation Replay

## 1. Branch

`feat/governed-single-game-replay`

## 2. Starting main SHA

`c716b979734be7f5a42340895bd435c7bb14bb15` (`origin/main`, unchanged during implementation).

## 3. Discovered CU-08R gap

CU-08R proved that a finalized observation accepted by CU-02 becomes
`UNCHANGED` on exact replay, so adding a reviewed plan fingerprint later cannot
route that already-accepted event into CU-03. It also proved that the ordinary
`SHADOW_FULL_CHAIN` path does not use the game allowlist as a canonical-action
gate. CU-08S adds a separate governed replay path; it does not broaden ordinary
`SHADOW_FULL_CHAIN` behavior.

## 4. Design

One bounded cycle may inspect explicitly requested game PKs after normal CU-02
detection. A request is eligible only in `shadow_full_chain`, with publication
disabled, an exact game allowlist entry, an exact 64-character hexadecimal
reviewed plan fingerprint, and an eligible persisted accepted final event. The
reconstructed orchestration input retains the accepted event's classification,
identities, finality, source authority/order evidence, and material difference
summary. It enters CU-03 normally; CU-03 and CU-01 retain their existing
authorization and regenerated-plan checks.

## 5. Replay source of truth

`GameObservationState` is the only replay source. CU-08S neither fetches a new
payload for replay nor edits, deletes, resets, or reclassifies CU-02 state. It
requires the stored accepted event to be `FINALIZED` or `CORRECTED`, final under
the canonical finality vocabulary, and owned by the authoritative MLB live-feed
source. The ordinary detector still runs independently and retains all of its
stale/ambiguous/weaker-source behavior.

## 6. Explicit game-scope enforcement

Replay requires:

```text
game_pk in BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS
and
game_pk in BASEBALLOS_CONTINUOUS_ALLOWLIST_GAME_PKS
```

Team allowlists, schedule participants, and wildcard inference cannot authorize
a replay. A currently accepted material change for the same game in the same
cycle blocks the replay exception rather than causing two canonical actions.
Ordinary `SHADOW_FULL_CHAIN` scope behavior is unchanged.

## 7. Fingerprint enforcement

Replay requires one exact game-keyed value in
`BASEBALLOS_CONTINUOUS_PLAN_FINGERPRINTS`. CU-08S validates the configured value
as a 64-character hexadecimal fingerprint before CU-03. CU-03 passes it to the
reviewed CU-01 entrypoint, where the production-authoritative planner regenerates
the current plan and requires exact equality before canonical persistence.
Missing, malformed, wrong-game, or mismatched fingerprints fail closed.

## 8. One-shot authorization

`BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS` is the explicit request. Each authorized
combination has one durable checkpoint identity. Removing the game from the
request immediately prevents new attempts. A succeeded mutation or authorized
no-op changes the checkpoint to `succeeded`, after which later cron cycles return
`replay_already_consumed` without invoking CU-03.

## 9. Durable consumption model

No schema was added. CU-08S reuses the existing `SyncJob` control ledger with:

- job name `continuous_game_replay`;
- family `continuous_replay`;
- internal lane;
- scope key bound to game PK, accepted observation fingerprint, and reviewed
  plan fingerprint;
- product date equal to the stored official game date;
- maximum two attempts.

The existing unique `(job_name, scope_key, product_date)` constraint makes the
authorization identity durable. Existing succeeded rows are read without
rewriting their timestamps. A crash after a canonical commit but before
checkpoint completion is safe: the bounded retry reaches CU-01, reconciles to a
canonical no-op, and consumes the same checkpoint.

## 10. Concurrency behavior

The replay is created and claimed only while the existing continuous-cycle lock
is held. PostgreSQL uses a session advisory lock; non-PostgreSQL tests use the
existing process lock. Therefore two recurring cycles have one winner, and the
loser stops before creating or claiming replay state. `SyncJob` additionally
records running ownership and refuses an active second claim.

The local lock-refusal proof passed. The PostgreSQL advisory-lock and checkpoint
proof is present in the hosted test selection but has not run in a hosted
PostgreSQL environment on this unpushed branch.

## 11. No-op behavior

An authorized CU-01 reconciliation with zero canonical mutation is recorded as
`authorized_no_op`, marked succeeded/consumed, emits no affected entities, and
does not invoke CU-04, CU-05, or CU-06. Exact later cycles remain inert.

## 12. Mutation behavior

A successful reviewed canonical mutation is recorded as `mutated` and consumed.
Only the requested game enters the replay chain. Mutation-scoped pitcher/team
IDs continue to come exclusively from CU-01. A pre-commit exception records a
failed attempt and permits at most one retry; after two failed attempts the
request is inert with `replay_attempts_exhausted`.

## 13. Downstream propagation

Only a real canonical mutation reaches CU-04, CU-05, and CU-06 through the
existing bounded chain. The focused mutation proof observed exactly one call to
each service. Authorized no-op and every refusal observed zero downstream calls.

## 14. Publication/cache safety

Replay is accepted only in `shadow_full_chain` and only when
`BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED=false`. The existing publisher branch
remains unreachable in this mode. Focused proof retained:

- `live_publications = 0`;
- `cache_handoffs = 0`;
- `production_authority_affected = false`;
- publication target `none`.

No publication pointer, snapshot writer, cache adapter, frontend authority, or
scheduled authority was added or changed.

## 15. Observability

Compact structured log events were added:

- `game_replay_requested`;
- `game_replay_authorized`;
- `game_replay_completed` with `mutated` or `authorized_no_op`;
- `game_replay_refused` with a bounded reason code;
- `game_replay_failed`.

The cycle result now includes bounded `replay_results` with game, status, reason,
outcome, plan fingerprint where authorized, and the durable checkpoint summary.
Raw MLB payloads and connection data are not logged.

## 16. Configuration

The minimum one-game shape is:

```text
BASEBALLOS_CONTINUOUS_MODE=shadow_full_chain
BASEBALLOS_CONTINUOUS_ENABLED=true
BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED=false
BASEBALLOS_CONTINUOUS_ALLOWLIST_GAME_PKS=<game_pk>
BASEBALLOS_CONTINUOUS_PLAN_FINGERPRINTS={"<game_pk>":"<reviewed 64-char fingerprint>"}
BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS=<game_pk>
```

Malformed replay game lists block configuration. No team allowlist is required
or consulted for replay authorization.

## 17. Revocation

Remove any one of the replay request, game allowlist entry, or game-keyed plan
fingerprint to revoke authorization without a deploy. Emergency rollback remains
`--mode shadow_detect`; the kill switch remains
`BASEBALLOS_CONTINUOUS_ENABLED=false`.

## 18. Restart behavior

The restart test removes the SQLAlchemy session after consumption, reconstructs
the application-side state, and repeats the same configured request. The stored
`SyncJob` remains succeeded, CU-03 is not called, and the result is
`replay_already_consumed`.

## 19. Tests

New CU-08S focused tests: **21 passed on PostgreSQL 16** and **20 passed,
1 PostgreSQL-only skip on SQLite**.

CU-01/CU-03/CU-04/CU-05/CU-06 and continuous-chain selection on PostgreSQL:
**136 passed**.

Continuous/checkpoint/publication/scheduling selection on PostgreSQL:
**98 passed**.

Compilation passed for the changed service. Final repository validation remains
to be recorded before promotion. CI shard accounting passed with **402 files**
and **9,146 tests**, each assigned exactly once.

## 20. Hosted PostgreSQL proof

**HOSTED CI NOT YET AVAILABLE on the local, unpushed branch.** A disposable
PostgreSQL 16 service completed the full production-shaped preflight, including
two independent spawned processes and connections. Required GitHub-hosted proof
remains the promotion gate:

- advisory-lock one-winner behavior;
- durable claim/consume;
- restart inertness;
- authorized no-op consumption;
- rollback/no partial canonical state;
- unchanged publication state.

This is the only acceptance evidence still missing. The local PostgreSQL proof
must not be relabelled as hosted CI.

## 21. Schema impact

None. The Alembic graph is unchanged. Existing `game_observation_states`,
`sync_jobs`, and their established constraints provide the required durable
state.

## 22. Blockers

The first PostgreSQL rollback injection exposed one bounded defect: after a
database statement error, the session remained transaction-aborted and could not
persist the failed replay checkpoint. CU-08S now explicitly rolls back that
failed unit of work before recording the bounded failure. The complete
PostgreSQL proof passed after the fix. Hosted validation is not available before
push, so the verdict remains partial rather than claiming unobserved hosted CI.

## 23. Target-game 822690 eligibility assessment

CU-08R recorded that game `822690` retains an accepted `FINALIZED` observation at
`final_pending_data` with accepted identity
`53e1b38f86614aed9f5c6f39325fba31369ede1c8cb7b4ce9313a036bddd989e`.
Later equal-revision/different-content payloads were rejected as ambiguous and
did not replace that accepted state. That stored event is structurally eligible
for the CU-08S replay source contract.

This repository task did not query the current production row, generate a target
plan, approve a fingerprint, or modify Render. Therefore `822690` is a reference
candidate only, not authorized. A production preflight must re-read the stored
row and independently generate/review the exact plan.

## 24. Final verdict

**PARTIAL — HOSTED POSTGRESQL PROOF PENDING**

The bounded implementation and all locally available semantic proofs pass. CU-08S
must not be called accepted until hosted PostgreSQL proves the real advisory-lock
and durable checkpoint behavior.

## 25. Exact next production authorization step

First, push this branch through a focused PR and require hosted PostgreSQL plus
the existing continuous/publication/scheduling checks. If those pass, merge with
a normal merge commit. Only in a separate authorization task should an operator:

1. verify the current stored accepted final observation for one game;
2. generate the exclusive CU-01 plan twice and confirm identical fingerprints;
3. review the complete plan and target scope;
4. configure exactly that game in replay request, game allowlist, and fingerprint
   map while publication remains false;
5. observe one consumed mutation or authorized no-op and the next inert cycle;
6. remove the replay request and fingerprint.

Do not change Render or authorize game `822690` in CU-08S itself.

## CU-08S-P — PostgreSQL durability and concurrency acceptance evidence

### 1. Environment

Disposable PostgreSQL 16 container, isolated database
`baseballos_cu08s_test`, current branch code, no production connection, no
production rows, and no retained container volume. This is production-shaped
local PostgreSQL evidence, not GitHub-hosted CI.

### 2. Database revision

A separate fresh-database migration run upgraded successfully from base through
`c6d8e1f3a5b7`; both `db current` and `db heads` reported
`c6d8e1f3a5b7 (head)`. Migration validation and fixture testing used separate
fresh database lifecycles so migration-owned tables could not contaminate test
fixture teardown.

### 3. Single claim

The first eligible request created one `SyncJob` with status `running`, attempt
count 1, game/observation/plan-bound scope key, start and heartbeat timestamps,
and the official game date. A completed claim became `succeeded` with a
completion timestamp and structured outcome.

### 4. Concurrent same-game claim

Two spawned Python processes opened independent PostgreSQL connections. Process
A acquired the advisory cycle lock and paused inside CU-03. Process B attempted
the same configured replay during that pause and returned
`cycle_already_running`, zero canonical actions, and no replay checkpoint
mutation. After release, A completed `authorized_no_op`. Final durable evidence:
one `SyncJob`, status `succeeded`, attempts 1. Exactly one claimant reached
CU-03.

### 5. Concurrent different-game behavior

The current continuous cycle lock intentionally serializes all continuous work,
including different games. CU-08S does not weaken that established global
exclusion merely to increase replay concurrency. Different games may execute in
later cycles, not concurrently.

### 6. Successful mutation

The real-shape proof used the actual CU-02 accepted-final state, canonical CU-01
shadow planner and reviewed fingerprint, CU-03 orchestration, CU-01 writer,
CU-04 workload/rest, CU-05 arm reads/Team State, and CU-06 bounded read-model
rebuild. It produced one canonical mutation game, two affected pitchers, two
historically owning teams, two CU-04 pitcher recomputations, two CU-05 arm-read
recomputations, bounded CU-06 work, then a consumed `mutated` checkpoint. Exact
replay performed zero CU-03 calls.

### 7. Authorized no-op

Canonical no-op returned `authorized_no_op`, stored status `succeeded`, emitted
no affected entities, and invoked none of CU-04/CU-05/CU-06. Later discovery
returned `replay_already_consumed` without incrementing attempts.

### 8. Restart

After consumption, the SQLAlchemy session was removed and rebuilt. The next
process/session read the succeeded `SyncJob`, returned inert, and did not invoke
CU-03. Both mutation and no-op consumption rely on PostgreSQL state, not Python
memory.

### 9. Pre-commit failure

A controlled PostgreSQL statement error occurred after claim and before any
canonical commit. The first run emitted no affected entities or downstream
work. The transaction was rolled back and the durable checkpoint recorded
`failed`, attempts 1. Attempt 2 safely completed an authorized no-op.

### 10. Bounded failure

Two controlled pre-commit failures produced attempts 2 and status `failed`.
Attempt 3 returned `replay_attempts_exhausted`; CU-03 was not called. No infinite
retry exists.

### 11. Rollback

The initial PostgreSQL proof exposed and fixed the transaction-aborted failure
checkpoint defect. `_fail_replay` now rolls back before loading and updating the
checkpoint. The rerun proved no partial canonical state, no false success, and a
correct retryable failure row.

### 12. Crash-like recovery

A claim was left `running` to simulate process termination. An immediate new
cycle returned `replay_claimed_elsewhere`. After moving the durable heartbeat
beyond the established 60-minute stale threshold, the next cycle reclaimed the
same job as attempt 2, completed no-op, and became succeeded/inert. No permanent
wedge or concurrent double execution occurred.

### 13. Publication/cache safety

Every replay configuration kept publication disabled. Mutation, no-op, failure,
restart, and concurrency results all retained zero live publications, zero cache
handoffs, and `production_authority_affected=false`. The replay code still has no
publisher path in `shadow_full_chain`.

### 14. Game isolation

An authorization containing only game A did not authorize game B. Requesting B
with only A's fingerprint returned `missing_fingerprint` before checkpoint
creation or CU-03. Team scope and current roster identity were never substituted
for exact game scope.

### 15. Revocation

Removing `BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS` before claim produced no replay
result, checkpoint, or execution. Removing configuration after completion does
not alter the durable succeeded history.

### 16. Repeated-cron inertness

Four recurring cycles produced: cycle 1 authorized no-op; cycles 2–4
`replay_already_consumed`. CU-03 call count remained exactly 1.

### 17. Durable row evidence

The proofs asserted the stored job ID, `continuous_game_replay` job name,
`continuous_replay` family, internal lane, game/accepted-observation/plan-bound
scope key, official product date, status, attempts, started/heartbeat/completed
timestamps, and bounded structured outcome. No raw source payload or secret was
recorded.

### 18. Tests

- CU-08S PostgreSQL: **21 passed**.
- CU-01 through CU-06 plus continuous chain on PostgreSQL: **136 passed**.
- checkpoint/publication/scheduling on PostgreSQL: **98 passed**.
- SQLite portability: **20 passed, 1 PostgreSQL-only skip**.
- CI shard verification: **402 files / 9,152 tests**, exactly once.
- compilation and whitespace validation: **PASS**.

### 19. Final verdict

**PARTIAL — GITHUB-HOSTED POSTGRESQL PROOF PENDING**

All available real-PostgreSQL durability, rollback, restart, bounded-failure,
real-chain mutation, and independent-process concurrency proofs pass. The task
explicitly requires hosted PostgreSQL, and the branch has not been pushed, so
the evidence cannot honestly be called hosted acceptance yet.

### 20. Merge recommendation

Push the branch, open a focused PR, require all four hosted PostgreSQL shards plus
migration and collection accounting, then use a normal merge commit only if all
required checks pass. Do not authorize a production game, modify Render, or
change publication configuration as part of that promotion.
