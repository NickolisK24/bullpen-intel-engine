# CU-03 — Change-to-Impact Orchestration

## 1. Branch

`feat/change-impact-orchestration`

## 2. Starting main SHA

`e192d2b9d834116fc871852c828e76b68effb46d`

The branch was created from the current local `main`, which matched the accepted
CU-02 merge checkpoint. The unrelated untracked
`BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` was not read, changed, staged,
or deleted.

## 3. CU-01 handoff audit

The reviewed writer is
`services.game_driven_ingestion.run_game_driven_ingestion`. Exact-game writes
require all of the following:

- `mode=write`, which is non-publication-authoritative;
- `only_game_pks=[game_pk]`;
- a `complete_reconciliation_fingerprint` produced by a reviewed shadow plan;
- the existing game-driven planner to reauthorize the exact plan;
- canonical finality and usable official pitching evidence.

The writer reuses the postgame GameLog reconciler and the final-play-by-play
foundation. It returns insert/update/unchanged counts, pitch-event mutation
counts, and mutation-scoped affected pitcher/team IDs. Optional PBP failure is
reported but does not roll back a valid official pitching line. Its PBP writer
explicitly requires final and usable evidence. There is no reviewed CU-01 live
GameLog or live-PBP canonical write seam.

## 4. CU-02 handoff audit

`GameChangeResult` carries the persisted observation classification, finality,
source authority/order evidence, material difference map, accepted flag, and
stable observation identities. CU-02 classifications are `new_game`,
`unchanged`, `changed`, `finalized`, `corrected`, `stale_observation`,
`ambiguous_observation`, and `source_failure`. Weaker authority is represented
by a rejected stale observation with reason `weaker_source_authority`.

CU-02 persists its last accepted normalized observation in
`GameObservationState`. It remains standalone and does not call CU-01.

## 5. Decision matrix

| CU-02 evidence | CU-03 decision | CU-01 call |
|---|---|---:|
| `unchanged` | `no_action` | 0 |
| `new_game` | `no_action` (first observation only) | 0 |
| generic live/status/score change | `no_action` | 0 |
| live pitcher, play-count, pitch-count, or last-event change | `defer_live_canonical` | 0 |
| accepted finality transition | `ingest_final_game` | 0 until explicitly authorized; then exactly 1 |
| accepted newer post-final observation | `inspect_post_final_correction` | 0 until explicitly authorized; then exactly 1 |
| stale observation | `reject_observation` | 0 |
| ambiguous observation | `reject_observation` | 0 |
| weaker-authority observation | `reject_observation` | 0 |
| source failure | `source_failure` | 0 |
| delayed/postponed status | `no_action` | 0 |
| suspended/resumed status without new baseball events | `no_action` | 0 |
| suspended/resumed state with live baseball-event evidence | `defer_live_canonical` | 0 |

The bridge does not parse vague prose to decide that baseball changed. It uses
CU-02 classification, accepted state, finality, and typed normalized difference
paths.

## 6. Orchestration result contract

`ChangeImpactResult` includes gamePk, detection classification, decision,
reason/status, whether canonical work was attempted, CU-01 mode/call count,
finality, GameLog and pitch reconciliation counts, canonical-mutation status,
mutation-scoped local/MLB pitcher IDs and team IDs, optional-PBP status,
source-failure state, `publication_affected=false`, and
`downstream_recomputation_triggered=false`.

## 7. Live-game safety contract

All live canonical work is deferred. A live pitching change or new pitch is
important observation evidence, but CU-01's existing writers are final-only.
CU-03 therefore records the deterministic `defer_live_canonical` result and
does not weaken finality, write partial GameLogs, or invent a second live PBP
authority.

## 8. Finality-transition contract

An accepted CU-02 `finalized` result in `final_pending_data` or
`final_and_usable` selects `ingest_final_game`. It still performs no write
unless the caller explicitly enables the non-authoritative write and supplies
the reviewed CU-01 plan fingerprint. CU-01 then rechecks schedule finality and
official evidence before writing.

## 9. Post-final correction contract

Only an accepted CU-02 `corrected` result with final status selects canonical
inspection. The same explicit reviewed-plan authorization is required. CU-01's
persisted source ordering remains the second defense, and affected entities are
returned only for actual canonical correction mutations.

## 10. Observation-order layering

The safety order is:

`CU-02 accepted source ordering -> CU-03 decision -> CU-01 canonical ordering`.

Stale, ambiguous, weaker, source-failure, and otherwise unaccepted observations
stop before CU-01. Neither layer promotes local acquisition time to source
revision authority.

## 11. Affected-entity ownership

CU-03 does not inspect roster participants, schedule teams, or mutable
`Pitcher.team_id` to guess impact. It copies affected IDs only from CU-01's
reconciliation report. CU-01 derives team impact from mutation-owned historical
appearance/event ownership.

## 12. Files changed

- `backend/services/change_impact_orchestration.py`
- `backend/scripts/orchestrate_game_change.py`
- `backend/tests/test_change_impact_orchestration.py`
- `backend/tests/ci_shard_manifest.json`
- `docs/current/CU_03_CHANGE_TO_IMPACT_ORCHESTRATION.md`

No frontend, workflow, Render, scheduler, publication, Team State, or read-model
file changed.

## 13. Schema changes

None. CU-02 already persists accepted observations; CU-01 already persists
canonical reconciliation and ordering evidence. CU-03 is a deterministic bridge
and does not need an orchestration ledger or queue.

## 14. Proof dataset

The established real-game evidence remains the exact CU-01/CU-02 15-game set:
823826, 823989, 823180, 824878, 823016, 822692, 822771, 823014, 823825,
822773, 823585, 823505, 824963, 822694, and 823179. That accepted evidence
covers multi-reliever, extra-inning, position-player pitching, optional fields,
idempotency, ownership, and workload parity.

CU-03 adds a controlled bridge proof combining the captured real MLB live-feed
shape from game 823826 with the established deterministic CU-01 final-game
fixture. It covers first observation, live-to-final transition, canonical
write, exact observation replay, direct canonical replay, and restart.

## 15. Natural versus controlled evidence

Naturally sourced and previously accepted: the 15 finalized MLB games and their
CU-01/CU-02 canonical/replay evidence.

Controlled real-shape replay in CU-03: live progression, pitching/PBP change
decisions, finality transition, post-final correction routing, stale,
ambiguous, weaker authority, delay/postponement, suspension/resumption, source
failure, optional PBP failure, and position-player orchestration behavior.

No controlled transition is claimed as a naturally observed live transition.

## 16. Finality handoff proof

The integrated test performs:

`CU-02 NEW_GAME -> CU-02 FINALIZED -> CU-03 INGEST_FINAL_GAME -> reviewed CU-01 write`.

Observed result: one CU-01 invocation, four GameLog inserts, four pitch-event
inserts, affected reliever MLB IDs 1002 and 2002, affected teams 111 and 147,
and no publication or derived recomputation.

## 17. No-op proof

An exact final-feed replay returns CU-02 `unchanged`. CU-03 returns `no_action`,
makes zero CU-01 calls, and emits no affected pitchers or teams. A separately
authorized direct CU-01 replay produced zero GameLog inserts/updates, zero pitch
inserts/updates/supersessions, and zero affected pitchers/teams.

## 18. Restart proof

After `db.session.remove()` (application/session restart boundary), the accepted
unchanged result still produces zero CU-01 calls and zero affected entities.
The canonical GameLog and pitch-event row counts remain four and four. CU-03 has
no ephemeral correctness state.

## 19. Stale, ambiguous, and weaker proof

Parameterized tests pass each rejected CU-02 class to CU-03 while supplying a
canonical ingestor that fails the test if called. All return a rejection/no-op,
make zero CU-01 calls, and emit zero affected entities.

## 20. Position-player pitching proof

An orchestration-level position-player fixture preserves current team and `CF`
position while allowing a historical canonical mutation result to name that
MLB identity as affected. Existing CU-01 real-game proof for Pedro Pages,
Jorbit Vivas, and Myles Straw remains the canonical identity regression proof.

## 21. Optional PBP failure proof

A CU-01 report with complete official pitching-line inserts and optional PBP
status `incomplete` maps to a reconciled CU-03 result. Core GameLog mutations
and their affected teams remain present; pitch inserts remain zero. Core-source
failure separately maps to `canonical_failed` and emits no impact.

## 22. CU-01 call-count evidence

- unchanged: 0
- stale: 0
- ambiguous: 0
- weaker authority: 0
- generic or live change: 0
- finality transition without explicit authorization/fingerprint: 0
- authorized reviewed finality transition: 1
- identical CU-02 final replay: 0
- controlled direct canonical idempotency replay: 1, with zero mutations

## 23. Canonical mutation evidence

The strongest integrated handoff inserted four final-game GameLogs and four
normalized pitch events through existing CU-01 code. The bridge itself owns no
canonical writer. The direct replay demonstrated zero insert, update, or
supersession mutations.

## 24. Affected-pitcher/team evidence

First reconciliation returned exactly the two relievers whose workload-bearing
canonical appearances changed and both historically owning game-side teams.
No-op, restart, stale, ambiguous, weaker, and source-failure results returned
empty affected sets.

## 25. Publication sentinels

A pre-existing `DashboardSnapshot` sentinel retained its ID, payload, count,
and unpublished state through final ingestion and replays. CU-03 imports or
calls no publication, snapshot, share-artifact, What Changed, or cache service.
Both result booleans remain false.

## 26. Derived-recomputation sentinels

CU-03 has no dependency on workload, fatigue/rest, availability, Team State,
Team Board, League, Matchup, Tonight, Pitcher read, or history builders. The
focused handoff changes only CU-02 observation state plus CU-01 canonical
GameLog/PBP state. `downstream_recomputation_triggered` is always false.

## 27. Scheduling regression proof

Current production execution remains dashboard-managed Render Cron:

| Job | UTC cadence | Existing command |
|---|---|---|
| daily | `5 10 * * *` | `run_due_sync.py --mode daily ... --days-back 7 --public-only` |
| postgame | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame ... --public-only` |
| morning | `5 14 * * *` | `run_due_sync.py --mode morning ... --public-only` |

GitHub retains delayed fallback schedules at 10:17, 02/04/06:11, and 14:23 UTC.
No root Render Blueprint exists. The CU-03 script disables `AUTO_SYNC` before
importing the Flask app, contains no loop/daemon, and appears in no workflow,
Render command, or existing sync entrypoint. No cadence or authority file is in
the diff.

## 28. Source-efficiency measurements

The controlled end-to-end cycle made three CU-02 observations: first/new,
finality/material, and exact final replay. They produced one normal canonical
inspection and one actual mutation. The exact replay avoided CU-01 entirely.
The separate direct idempotency proof deliberately made one additional CU-01
call to prove zero canonical mutations.

Across the 12 non-final/rejected matrix scenarios, canonical calls were 0/12.
No additional MLB request is introduced by the decision function; an authorized
write uses CU-01's existing acquisition behavior. Optimization and production
polling remain out of scope.

## 29. Test results

- CU-03 focused: **21 passed**.
- CU-03 + accepted CU-02 + accepted CU-01 focused: **50 passed**.
- Selected finality, ingestion, reconciliation, provenance, postgame,
  scheduling, snapshot, publication, and historical-ownership suite:
  **460 passed**, with two working-directory-qualified migration test failures;
  rerunning that migration/ownership file from `backend` passed **56/56**.
- Expanded shadow/scheduling/publication selection: **471 passed** with two
  known environment failures. The remote-database-qualified failure passed
  against explicit disposable SQLite; the Windows-to-bash temporary-path test
  remains the accepted host-path failure. The qualified shadow workflow rerun
  passed **145 tests with that one host-path case deselected**.
- CI shard verification: **PASS**, 395 files and 9,011 node IDs exactly once.
- Alembic heads: **PASS**, one head `c6d8e1f3a5b7`.
- Python compilation: **PASS**.
- `git diff --check`: **PASS**; only the repository's LF-to-CRLF warning for the
  shard manifest was emitted.

## 30. Remaining known gaps

- No naturally timed live-to-final or naturally observed post-final correction
  was captured during CU-03; those remain controlled real-shape proofs.
- CU-03 intentionally does not ingest live partial canonical facts because no
  reviewed CU-01 live writer exists.
- Production invocation policy, scheduling, and derived recomputation are not
  implemented.
- Dashboard-managed Render resource values were not changed or independently
  queried; repository configuration and accepted operations documentation are
  the scheduling evidence.

## 31. Proven claims

- CU-02 results map deterministically to a bounded CU-03 decision.
- Rejected/unchanged/live-deferred observations do not reach CU-01.
- Final/correction writes require explicit enablement and a reviewed CU-01 plan.
- The real bridge invokes existing CU-01 once and returns only CU-01 mutation
  counts and mutation-derived affected entities.
- Replay and restart are idempotent.
- Optional PBP remains nonblocking and core acquisition remains fail closed.
- Position-player current identity remains unchanged.
- No derived, publication, cache, frontend, scheduler, or authority path is
  activated.

## 32. Unproven claims

- CU-03 is not proven as a production scheduled service and is not enabled as
  one.
- Natural live, suspension/resumption, and post-final correction orchestration
  have not been observed.
- No claim is made that live canonical reconciliation is supported.
- No derived recomputation or public-currentness claim is made.

## 33. Final verdict

**PASS — CU-03 ACCEPTED**

The acceptance statement is supported by deterministic decision tests, the
integrated finality-to-CU-01 handoff, mutation-scoped impact, fail-closed
ordering, replay/restart behavior, and publication/derived/scheduling
boundaries.

## 34. Exact recommended next slice

First integrate CU-03 into current `main` through a separate normal-merge,
hosted-PostgreSQL validation task while preserving its non-scheduled status.
Only after that repository integration should a separately scoped CU-04 consume
the mutation-scoped pitcher/team result to recalculate workload and rest. This
task does not begin CU-04.
