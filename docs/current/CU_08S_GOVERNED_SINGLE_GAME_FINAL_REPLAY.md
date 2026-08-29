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

New CU-08S focused tests: **15 passed**.

CU-01/CU-03/CU-04/CU-05/CU-06 and continuous-chain selection:
**143 passed, 1 skipped**.

Continuous/checkpoint/publication/scheduling selection:
**149 passed, 3 skipped**. The skips are PostgreSQL-only checks in the local
SQLite environment.

Compilation passed for the changed service. Final repository validation remains
to be recorded before promotion. CI shard accounting passed with **402 files**
and **9,146 tests**, each assigned exactly once.

## 20. Hosted PostgreSQL proof

**NOT AVAILABLE on the local, unpushed branch.** No PostgreSQL connection is
configured in this workspace. Required hosted proof remains:

- advisory-lock one-winner behavior;
- durable claim/consume;
- restart inertness;
- authorized no-op consumption;
- rollback/no partial canonical state;
- unchanged publication state.

This is the only acceptance evidence still missing.

## 21. Schema impact

None. The Alembic graph is unchanged. Existing `game_observation_states`,
`sync_jobs`, and their established constraints provide the required durable
state.

## 22. Blockers

No implementation or semantic blocker was found. Hosted PostgreSQL validation is
not available before push, so the final acceptance verdict remains partial rather
than claiming unobserved production-shaped concurrency proof.

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
