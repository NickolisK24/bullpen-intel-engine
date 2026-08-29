# CU-08 — Controlled Continuous Execution & Cadence Activation

## 1. Branch

`feat/controlled-continuous-execution`

## 2. Starting main SHA

`4b82cc0345c9bbe735a844d7d414f88182c51ba8` (PR #775 merge). `main` and
`origin/main` were identical before implementation. Main CI run `33236342271`
completed successfully at that SHA.

## 3. Current Render scheduled architecture

Render Cron remains primary trigger authority and GitHub Actions remains the
delayed fallback. Both call the same durable due-window runner; neither invokes
CU-08.

| Lane | Render UTC cadence | GitHub fallback | Command/authority |
|---|---:|---:|---|
| Daily | `5 10 * * *` | `17 10 * * *` | `run_due_sync.py --mode daily`; broad canonical, derived, and governed publication authority |
| Morning | `5 14 * * *` | `23 14 * * *` | `run_due_sync.py --mode morning`; schedule/Tonight correction |
| Postgame | `5 2,4,6 * * *` | `11 2,4,6 * * *` | `run_due_sync.py --mode postgame`; completed-game reconciliation and governed publication |
| Intraday repair | none | manual only | dormant governed repair/audit |

The documented command ceilings remain 40 minutes daily, 20 minutes postgame,
and 5 minutes morning. MLB acquisition already uses bounded request timeouts,
up to three transient retries, capped exponential backoff, jitter, and
`Retry-After` handling. The repository has no root `render.yaml`; Render jobs
remain dashboard-managed. CU-08 adds no Render or GitHub schedule.

## 4. Continuous cycle architecture

`run_continuous_cycle` is one process-bounded call:

```text
validated mode/config
  -> nonblocking continuous-cycle lock
  -> public writer lock for canonical modes
  -> bounded CU-02 active-slate observation
  -> unchanged/rejected/failure gate
  -> CU-03 reviewed-plan authorization
  -> CU-01 canonical reconciliation
  -> CU-04 -> CU-05 -> CU-06
  -> optional CU-07 proof target or explicitly injected live target
  -> durable result
  -> STOP
```

It has no loop, sleep, worker, queue, daemon, or scheduler dependency.

## 5. Activation-mode contract

| Mode | Allowed behavior |
|---|---|
| `OFF` | no source request, lock, canonical work, or publication |
| `SHADOW_DETECT` | CU-02 only; persisted observations and run metadata |
| `SHADOW_FULL_CHAIN` | CU-02 through CU-06 where CU-03 authorization and reviewed plan permit; no CU-07 call |
| `PROOF_PUBLICATION` | full chain; CU-07 targets only `cu07_incremental_proof` |
| `LIMITED_LIVE` | game/team allowlist, production-publication switch, cohort cap, and explicit production publisher all required |
| `FULL_LIVE` | separate publication switch and explicit full-live acknowledgement required; not enabled or wired by CU-08 |

## 6. Production default

`BASEBALLOS_CONTINUOUS_ENABLED=false`, mode `off`, and production publication
false. Missing configuration is OFF. Invalid active configuration fails closed.

## 7. Scheduler-ready command

```text
python backend/scripts/run_continuous_cycle.py \
  --represented-time 2026-08-29T22:00:00Z
```

`--mode` may select a mode, but cannot override the environment kill switch.
The command forces `AUTO_SYNC=false`, acquires locks, runs once, prints JSON,
and exits. No scheduler invokes it.

## 8. Locking/overlap strategy

Every enabled cycle takes nonblocking advisory key `820260803` on PostgreSQL
(a process lock on SQLite). Canonical modes additionally take the established
public sync writer lock. Thus a second continuous cycle skips, while daily or
postgame work and a canonical continuous cycle cannot overlap. Locks are
session-scoped and disappear on process/database disconnect.

## 9. Source-budget strategy

Defaults: 32 requests, 15 games, 4 canonical actions, 2 publication cohorts,
and 120 seconds per cycle. CU-02 reserves one schedule request, caps feed
requests before acquisition, and prioritizes current live/current-day games
over correction-window finals when capped. The cycle stops starting new game
work after the measured client budget is reached. An in-flight game operation
finishes or rolls back atomically.

## 10. Game-selection/cadence strategy

CU-02 continues to select the represented day's slate, recent authoritative
finals in the two-day correction window, and suspended games. CU-08 adds only a
cap and active/current priority; there is no historical or full-season scan.
Dynamic sub-minute scheduling is intentionally deferred.

## 11. Mode-to-publication authority map

| Mode | Target |
|---|---|
| OFF / shadow modes | none |
| PROOF_PUBLICATION | `cu07_incremental_proof` |
| LIMITED_LIVE / FULL_LIVE | explicit injected `production_current` publisher only |

The repository command supplies no production publisher. Therefore merge alone
cannot advance production current state.

## 12. Allowlist design

LIMITED_LIVE accepts explicit gamePks and/or team IDs. A game may enter
canonical work only when its game identity is allowed; a publication cohort is
allowed only by gamePk or when all affected teams are allowed. Empty allowlists
are invalid. No random or percentage rollout exists.

## 13. Kill-switch design

`BASEBALLOS_CONTINUOUS_ENABLED=false` prevents source work. A separate
`BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED=false` blocks production publication
while permitting shadow/proof execution. FULL_LIVE also requires
`BASEBALLOS_CONTINUOUS_FULL_LIVE_ACKNOWLEDGED=true`.

## 14. Failure/circuit-breaker behavior

Failures are scoped by game/stage. One game failure does not block an
independent game. Core source failures open the cycle breaker at three failures
or a 50% failure ratio; no later canonical/publication work starts. Optional
PBP behavior remains CU-01's established nonblocking contract. A failed cohort
is never treated as published.

## 15. Retry behavior

CU-08 adds no retry loop. It reuses the MLB client's bounded retries and lets
the next recurring invocation retry durable pending work naturally.

## 16. Missed-cycle/restart recovery

CU-02 observations, CU-01 canonical facts, and CU-07 identities are durable.
No in-memory event queue or orchestration checkpoint is required. Exact replay
after restart remains UNCHANGED and performs no CU-03 through CU-07 work.

## 17. Existing scheduled-sync coexistence

Scheduled jobs remain production authority and reconciliation/backstop. The
shared public advisory lock prevents concurrent canonical/public writes.
Sequential reconciliation remains protected by CU-01 idempotency, source
ordering, and CU-07 expected-current checks.

## 18. Continuous vs postgame proof

The relevant suite passed the real postgame idempotency contract (second run:
zero new GameLogs), CU-01 replay/correction contracts, the shared public-writer
conflict test, and CU-07 PostgreSQL expected-current concurrency. This proves
overlap skips and sequential same-state reconciliation cannot duplicate the
canonical or proof-publication cohort. Existing postgame authority was not
modified or invoked by the cycle itself.

## 19. Continuous vs daily-sync proof

Daily wiring, authority, finality, publication-critical, schedule-authority,
and game-driven shadow tests remained green. The continuous chain uses the same
canonical/derived calculators and cannot overlap the daily writer. No daily
command or publication gate changed.

## 20. Reconciliation contract

Broad sync may reconcile equal/newer authoritative truth. Stale CU-02/CU-01
evidence cannot overwrite newer accepted facts, and stale CU-07 candidates
cannot rotate the proof pointer. The cycle does not generate What Changed, so
it cannot fabricate duplicate transitions.

## 21. Run metadata/observability

Completed enabled cycles use `SyncRun(job_name="continuous_cycle")`, outside
the last-successful public freshness authority query. A canonical-mode run may
correctly appear temporarily as the active writer while it holds the shared
public lock. Stored and returned evidence includes
mode, outcome, games, failures, requests/retries, canonical mutations,
affected entities, stage counters, proof/live publication counts, cache
handoffs, breaker/timeout/lock state, and runtime. OFF creates no run.

## 22. Freshness latency metrics

The result records detection elapsed time, upstream observation timestamp when
MLB supplies one, cycle start/finish, and each lower-stage structured result.
MLB does not provide a trustworthy baseball-event occurrence time for every
change, so source-event latency is not claimed. Initial SLO-style rollout
targets are median detection under 3 minutes and final proof publication under
5 minutes after authoritative source availability; these are not product
promises and require production shadow evidence.

## 23. Files changed

- `backend/services/continuous_execution.py`
- `backend/scripts/run_continuous_cycle.py`
- `backend/services/game_change_detection.py`
- `backend/tests/test_continuous_execution.py`
- `backend/tests/test_game_change_detection.py`
- `backend/tests/ci_shard_manifest.json`
- `backend/.env.example`
- this report

## 24. Schema changes

None. Alembic remains one head: `c6d8e1f3a5b7`.

## 25. Stage A — OFF proof

The command returned `off/mode_off`, zero locks, zero requests, zero work, and
no publication with default environment values.

## 26. Stage B — SHADOW_DETECT proof

CU-02 ran alone, persisted non-public cycle metadata, and emitted no CU-03+
calls. A natural MLB scheduled-slate observation checked 15 games: first cycle
15 NEW_GAME, exact replay 15 UNCHANGED.

## 27. Stage C — SHADOW_FULL_CHAIN proof

Controlled finality evidence invoked CU-03 through CU-06 once. Unchanged,
stale, ambiguous, weaker, and source-failure evidence performed no downstream
work. No publication candidate was created.

## 28. Stage D — PROOF_PUBLICATION proof

The strongest real-shape fixture ran CU-03 through CU-07: one canonical game
mutation, two affected pitchers, two historical teams, bounded CU-04/CU-05,
CU-06 rebuild, one atomic proof publication, and one cache handoff. Production
authority remained false. Exact replay performed no chain work.

## 29. Stage E — LIMITED_LIVE simulation proof

An isolated injected production-shaped publisher proved allowed game scope,
expected-current propagation, one live cohort, and one cache handoff. A
non-allowlisted game performed zero canonical work; an allowed game without a
publisher failed closed. No real production pointer was touched.

## 30. Natural live-game evidence

On 2026-08-29 the official MLB schedule exposed 17 games, all Scheduled at the
observation time. Natural scheduled first-observation/replay evidence was
collected, but no upcoming-to-live, pitching-change, or live-to-final transition
occurred during the bounded proof. Those transitions remain controlled
real-shape evidence rather than natural CU-08 evidence.

## 31. Multi-cycle proof

Controlled sequence: changed cycle ran CU-03→CU-06 once; exact replay ran zero
CU-03+ actions. The real 15-game replay likewise produced 15 UNCHANGED and zero
downstream actions.

## 32. Overlap proof

SQLite/process tests showed a second cycle skips. Local PostgreSQL proof in an
isolated `cu08_test_runtime` schema showed one advisory-lock winner. CU-07's
PostgreSQL reader and competing-candidate proofs also passed. The temporary
schema was dropped and verified absent.

## 33. Kill-switch proof

An active shadow cycle completed; the next cycle with execution disabled made
no detector call. Existing scheduler files were byte-unmodified.

## 34. Source/load measurements

Natural 15-game scheduled slate:

| Cycle | Checked | Changed | Unchanged | Requests | Retries | Detector runtime |
|---|---:|---:|---:|---:|---:|---:|
| first | 15 | 15 | 0 | 16 | 0 | 780.73 ms |
| exact replay | 15 | 0 | 15 | 16 | 0 | 464.66 ms |

The cap prevents more than 15 feeds per cycle; lower canonical work is also
bounded to four games and two publication cohorts.

## 35. Full-slate runtime

The measured 15-game detector cycle was below one second from this environment.
The real-shape full-chain test completed inside the 1.49-second focused test
run, but was not isolated as a production network benchmark. The command has a
120-second stop-starting-work boundary; production p95 must be measured before
advancing beyond shadow.

## 36. Recommended initial cadence

After safe merge, create a separately authorized Render Cron at **every three
minutes**, mode SHADOW_DETECT, for 24–48 hours. Advance only if observed p95 is
comfortably below 120 seconds and source failures/locks remain healthy. Do not
start at one minute. SHADOW_FULL_CHAIN and proof publication need separate
evidence windows before any limited-live simulation.

## 37. Estimated daily request/run load

Three-minute cadence is 480 invocations/day. At the absolute 15-game cap it is
7,680 schedule/feed requests/day; a 12-hour active window at that cap is about
3,840. Actual work should be lower outside the active slate. Canonical writes,
publication, and cache handoffs occur only on accepted material changes; exact
replay produces none.

## 38. PostgreSQL concurrency proof

PASS in an isolated local PostgreSQL schema:

- one continuous advisory-lock winner;
- second cycle lock rejected nonblockingly;
- readers observed old committed state until atomic new commit;
- two same-expected-current candidates produced one commit and one conflict;
- exactly one proof snapshot remained current.

## 39. Focused tests

- CU-08 focused: `24 passed, 1 skipped` on SQLite (the skip is PostgreSQL-only).
- CU-02 through CU-08 focused: `143 passed, 3 skipped`.

## 40. Broad relevant tests

`718 passed, 3 skipped, 1 deselected` across continuous ingestion/detection,
orchestration, workload, Team State, read models, publication, finality,
concurrency, postgame/daily wiring, scheduling, and governance. The deselected
case is the established Windows temporary-path `bash -n` incompatibility; its
failure reproduced unchanged when included.

CI shard verification: 400 files, 9,117 tests, every test assigned exactly
once. Compilation and whitespace checks passed.

## 41. Full backend status

NOT RUN. The bounded semantic/authority suite and PostgreSQL concurrency proof
were used as the acceptance evidence.

## 42. Remaining risks

- Natural live/finality transition evidence has not yet been collected under a
  recurring Render invocation.
- Full-chain production p95 and source pressure are not yet measured.
- The repository command intentionally has no production publisher; real
  LIMITED_LIVE needs a separately reviewed authority adapter/activation.
- Environment changes on Render require its normal service configuration
  update/restart; CU-08 adds no remote control plane.
- Existing broad jobs remain long-running; canonical modes may skip while they
  hold the public writer lock, then recover next cycle.

## 43. Proven claims

The cycle is bounded, one-shot, restart-safe, default-OFF, mode-explicit,
lock-protected, source-capped, breaker-protected, allowlist-aware, and durable.
It avoids downstream work on unchanged games, composes the accepted chain, can
publish atomically to proof authority, and coexists with scheduled authority
without modifying it.

## 44. Unproven claims

No claim is made that recurring production shadow execution, natural live
latency, real LIMITED_LIVE authority, FULL_LIVE authority, or a production
cache handoff has been proven. No claim is made that the full backend suite is
green.

## 45. Final verdict

**PASS — CU-08 IMPLEMENTATION ACCEPTED**

The implementation acceptance is for dormant, scheduler-ready capability. It
is not authorization to activate production continuous execution.

## 46. Exact safe repository integration recommendation

Fetch current main, audit drift, rerun CU-08 focused plus PostgreSQL hosted CI,
push this branch, open a normal PR, require all hosted checks, and merge with a
normal merge commit. Do not add a schedule in that PR.

## 47. Exact staged production activation recommendation

1. SHADOW_DETECT every three minutes for 24–48 hours.
2. Review p50/p95 runtime, requests, lock skips, failures, and natural changes.
3. SHADOW_FULL_CHAIN with reviewed plan fingerprints and publication disabled.
4. PROOF_PUBLICATION to `cu07_incremental_proof`; validate cache retries and
   scheduled reconciliation.
5. LIMITED_LIVE only in a separately authorized change with explicit game/team
   allowlist and a reviewed production publisher.
6. Expand allowlist gradually; consider FULL_LIVE only after a separate gate.

## 48. Actions not yet authorized

- adding or enabling a Render/GitHub recurring schedule;
- changing any existing cadence;
- enabling LIMITED_LIVE or FULL_LIVE;
- installing a production publication adapter;
- changing production environment variables;
- retiring daily/postgame reconciliation;
- deploying or running production migrations;
- changing baseball semantics, frontend behavior, What Changed, or caches;
- beginning CU-09.
