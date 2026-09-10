# CU-03I — Main Integration and Regression Proof

## 1. Branch

`feat/change-impact-orchestration`

## 2. Starting CU-03 HEAD

`618d43c2b0aaeab142d634b15b032ad7f3f5dd62`

The accepted commit remains an ancestor of the integrated branch. The unrelated
untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` remained untouched.

## 3. Current/integrated origin/main SHA

`fc5c2fe9ba464bba8df4e2cdb6733762ecd3e7a4`

## 4. Merge commit SHA

`f476b17711fb9d65455f1e7cde8e7893571123b5`

The integration used a normal `--no-ff` merge. It did not rebase, squash, or
rewrite the accepted CU-03 commit.

## 5. Ahead/behind state

Immediately after the integration merge the branch was two commits ahead and
zero commits behind `origin/main`. The durable CU-03I proof commit adds one
further feature-branch commit; no push occurred.

## 6. Upstream commit audit

| SHA | Title | Files and behavior | CU-03 interaction |
|---|---|---|---|
| `fc5c2fe9ba464bba8df4e2cdb6733762ecd3e7a4` | `docs: publish generated team preview pages` | Updates only generated timestamps in 30 `frontend/public/team/*/index.html` files. Snapshot ID, data-through date, team reads, routes, runtime code, workflows, and backend are unchanged. | **NO INTERACTION** |

The actual diff contains no CU-01 ingestion, CU-02 detector, CU-03, finality,
ordering, authority, GameLog, PBP, plan fingerprint, migration, scheduler,
workflow, publication runtime, Team State methodology, workload/rest, or test
change.

## 7. Conflict resolutions

None. Git's `ort` strategy merged the generated frontend files without a
conflict. No ours/theirs override was used.

## 8. Current Render execution map

The repository has no root Render Blueprint; the primary jobs remain
dashboard-managed Render Cron services:

| Job | UTC schedule | Command and production path |
|---|---|---|
| Daily | `5 10 * * *` | `run_due_sync.py --mode daily ... --days-back 7 --public-only` -> canonical scheduled sync -> derived/public state -> guarded publication |
| Postgame | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame ... --public-only` -> completed-game refresh -> canonical/derived state -> guarded publication |
| Morning | `5 14 * * *` | `run_due_sync.py --mode morning ... --public-only` -> slate acquisition -> guarded public refresh |

GitHub `baseballos-sync.yml` retains delayed fallback schedules at 10:17,
02/04/06:11, and 14:23 UTC. Render remains primary under
`BASEBALLOS_SCHEDULER_AUTHORITY=render_cron_v1`; GitHub has not regained primary
authority. The seasonal intraday repair remains manual only.

## 9. CU-03 invocation map

The only executable CU-03 entrypoint is the standalone
`backend/scripts/orchestrate_game_change.py`. It disables `AUTO_SYNC` before app
import and requires an explicit flag plus reviewed fingerprint before a final
write can be attempted. Repository search found no CU-03 reference in Render,
GitHub workflows, `run_due_sync.py`, CU-02's detector command, or another
production entrypoint.

Current state remains:

`manual/proof invocation -> CU-02 observation -> CU-03 decision -> optional reviewed CU-01 final write -> STOP`.

## 10. Migration-head result

CU-03 and CU-03I add no schema. `flask db heads` reports exactly one head:
`c6d8e1f3a5b7`. The upstream generated-page commit adds no migration. CU-01 and
CU-02 migrations remain intact, and the 56-test migration/appearance-ownership
suite remains green.

## 11. Decision-matrix replay

The integrated focused suite passed every accepted mapping:

- unchanged/new/generic non-final -> no action;
- live pitcher, play-count, pitch-count, or last-event change -> defer live
  canonical work;
- finalized/corrected -> authorization required;
- stale/ambiguous/weaker -> rejected before CU-01;
- source failure -> fail closed;
- postponed/suspended without new baseball events -> no action;
- resumed/live event evidence -> deferred, not forced through final ingestion.

No taxonomy or runtime decision changed during integration.

## 12. Authorization-gate proof

An unauthorized finality or correction result returns
`authorization_required`, with zero CU-01 invocations and zero mutations.
Enabling canonical action without a fingerprint also makes zero CU-01 calls.
Only an explicit `allow_canonical_write=true` plus non-empty reviewed fingerprint
reaches CU-01's own reauthorization gate. Generic `changed` results cannot take
this path.

## 13. Plan-fingerprint proof

- Correct current shadow fingerprint: CU-01 reauthorizes and writes.
- Missing fingerprint: CU-03 stops before CU-01.
- Incorrect fingerprint: CU-01's exclusive-scope authorization tests return
  `plan_fingerprint_mismatch` before canonical mutation.
- Stale fingerprint: the new CU-03I regression obtains a real shadow
  fingerprint, changes authoritative pitching evidence, and presents the stale
  fingerprint. CU-01 recomputes the plan, rejects the mismatch before PBP or
  persistence, and leaves GameLog/pitch/affected sets empty.

Semantic call-count note: an incorrect or stale but well-formed hash cannot be
identified from the string alone. CU-03 therefore enters the CU-01
reauthorization planner once; no CU-01 canonical reconciliation/write handler
runs. This is fail-closed plan validation, not canonical ingestion. The result
truthfully records one CU-01 entrypoint invocation and zero canonical mutation.

## 14. Strongest finality handoff

The accepted integrated proof reproduced exactly:

`CU-02 FINALIZED -> CU-03 INGEST_FINAL_GAME -> explicit authorization -> reviewed fingerprint -> CU-01 once -> 4 GameLogs -> 4 pitch events -> relievers 1002/2002 -> historical teams 111/147 -> STOP`.

There was no source or fixture change.

## 15. CU-01 call counts

- unchanged: 0
- stale CU-02 observation: 0
- ambiguous CU-02 observation: 0
- weaker-authority CU-02 observation: 0
- source failure: 0
- unsupported/generic/live observation: 0
- unauthorized finality: 0
- finality missing fingerprint: 0
- valid authorized finality: 1
- exact accepted-observation replay: 0
- deliberate direct canonical replay: 1, zero mutations
- stale plan reauthorization: 1 planner entry, zero canonical write

## 16. Exact no-op replay

The same accepted final observation returns CU-02 `unchanged`; CU-03 returns
`no_action`. CU-01 calls, GameLog mutations, pitch mutations, affected pitchers,
affected teams, publication effects, and derived recomputation are all zero.

## 17. Restart replay

After the session/application restart boundary, the persisted CU-02 fingerprint
still classifies the same feed as unchanged. CU-03 again makes zero CU-01 calls
and emits no affected entities. No CU-03 ephemeral state participates in
correctness.

## 18. Direct canonical replay

The deliberate reviewed replay enters CU-01 once on the already canonical final
game. It reports zero GameLog inserts/updates, zero pitch
inserts/updates/supersessions, and zero affected pitchers/teams. The four
GameLogs and four pitch rows remain singular.

## 19. Observation-order layering

The integrated chain remains:

`CU-02 accepted source ordering -> CU-03 decision -> CU-01 canonical ordering`.

Rejected CU-02 evidence never reaches CU-01. Existing lower-level CU-01 tests
still reject stale, ambiguous, and weaker canonical pitch observations,
including across restart. Local acquisition time remains non-authoritative.

## 20. Affected-entity ownership

CU-03 copies affected IDs only from CU-01's mutation report. It does not inspect
schedule participants, all observed pitchers, detector differences, or current
`Pitcher.team_id`. Existing correction coverage proves one corrected pitcher
emits only that pitcher and the historical appearance-owning team. Every no-op
and rejection emits empty sets.

## 21. Position-player pitching proof

The orchestration regression preserves a position player's current team and
`CF` position while allowing a historical pitching mutation to name the player
as affected. CU-03 does not promote the player to a current bullpen role or
rewrite position to pitcher. Accepted CU-01 real-game coverage remains intact.

## 22. Optional PBP failure proof

When core final pitching lines succeed and optional PBP is incomplete, CU-03
returns the valid GameLog mutation and its mutation-scoped affected entities,
reports optional PBP `incomplete`, and performs no publication or derived work.
Core source failure remains fail closed and emits no impact.

## 23. Live-game safety proof

Live inning progression makes zero CU-01 calls. Live pitching changes and new
live PBP/event evidence select `defer_live_canonical`, also with zero CU-01
final-game calls. Integration added no live writer or partial GameLog authority.

## 24. Zero derived-recomputation proof

CU-03 imports and calls no workload, rest, fatigue/arm-read, Team State,
concentration, rotation, role/deployment, performance, Team Board, League,
Matchup, Tonight, Pitcher-read, History, or What Changed builder. Focused results
keep `downstream_recomputation_triggered=false`; the canonical handoff sentinel
changes only CU-02 observation and CU-01 GameLog/PBP state.

## 25. Zero-publication proof

The strongest handoff preserves the existing DashboardSnapshot sentinel's ID,
count, payload, and publication state. CU-03 has no publication/share/cache
dependency. Relevant snapshot/publication suites passed, and the feature diff
against integrated main contains no publication or frontend runtime change.
The generated preview timestamp changes are solely the audited upstream main
commit and are not CU-03 behavior.

## 26. Scheduling regression proof

`git diff origin/main...HEAD` contains only the CU-03 service, standalone script,
tests/shard assignment, and proof documentation. There is no Render file,
workflow, cron expression, `run_due_sync.py`, scheduler, worker, daemon, polling
loop, or automatic CU-02-to-CU-03 wiring change.

## 27. Orchestration-efficiency measurements

The controlled end-to-end sequence examines three CU-02 observations: first
observation, finality transition, and exact replay. Results are one observation
only/no-action, one canonical inspection and mutation, and one unchanged/no
action:

- observations: 3
- normal canonical inspections: 1 (33.3%)
- actual mutation runs: 1 (33.3% of observations; 100% of normal inspections)
- exact replay CU-01 calls: 0
- first-run affected relievers/teams: 2/2

Across the 12 non-final/rejected matrix scenarios, CU-01 calls remain 0/12. The
separate direct replay and stale-plan checks intentionally exercise lower-level
idempotency/authorization and are not normal orchestration work.

## 28. Focused test results

- CU-03 focused after added stale-plan regression: **22 passed**.
- CU-03 + CU-02 + CU-01 focused: **51 passed**.
- Focused plus exclusive-scope fingerprint authorization: **77 passed**.
- Strongest handoff retained 4 GameLogs, 4 pitches, 2 relievers, and 2 teams.

## 29. Expanded test results

- Relevant ingestion/finality/order/PBP/postgame/ownership/snapshot/publication/
  scheduling selection: **490 passed**.
- Qualified expanded shadow/scheduling/publication selection: **472 passed,
  1 known Windows bash-path test deselected**.
- Frontend suite after upstream static-page integration: **1,210 passed**.
- CI shard verification: **PASS**, 395 files and 9,012 node IDs exactly once.
- Python compilation: **PASS**.
- Alembic head: **PASS**, one head `c6d8e1f3a5b7`.
- Whitespace/diff checks: **PASS**, with only expected Windows line-ending
  warnings.

## 30. Broader diagnostic

Qualified disposable-SQLite full backend run completed in 280.99 seconds:
**8,885 passed, 73 skipped, 54 failed**. A cached-failure rerun produced
**53 failures, 1 pass, 70 deselected** in 3.17 seconds. The extra first-run
failure was order-dependent and did not reproduce.

The 53 consistent failures match the accepted baseline clusters: Windows/bash
path execution, platform/CORS assumptions, historical source-hash and
branch-diff freeze fixtures, no-op/incident-audit environment assumptions, and
Windows `/proc` behavior. None imports or exercises CU-03. No new consistent
CU-03 integration regression was found. The broader diagnostic is **FAIL
(unrelated baseline)**, not green.

## 31. Remaining known gaps

- Natural live, suspension/resumption, and post-final correction orchestration
  remain controlled real-shape proofs.
- A stale reviewed hash necessarily enters CU-01's authorization planner before
  it can be identified as stale; canonical write/reconciliation remains zero.
- CU-03 remains dormant and has no production cadence, hosted PostgreSQL, or
  deployment proof in this local-only task.
- Live canonical reconciliation remains intentionally unsupported.
- Dashboard-managed Render resource values were not modified or independently
  queried; repository evidence proves no integration change.

## 32. Proven claims

- The only upstream commit has no CU-03 interaction and merged conflict-free.
- All accepted decision, authorization, finality, replay, restart, ordering,
  affected-entity, position-player, optional-PBP, publication, and live-safety
  contracts remain intact.
- Correct fingerprints authorize; missing, incorrect, and stale fingerprints
  cannot mutate canonical state.
- CU-03 remains deterministic, standalone, non-scheduled, and non-authoritative.
- No derived recomputation, publication, cache invalidation, frontend runtime,
  or scheduling behavior was introduced.

## 33. Unproven claims

- CU-03 is not proven as or enabled as a production recurring service.
- No natural live transition or natural post-final correction was observed.
- No hosted PostgreSQL/PR validation was performed because this task is local
  integration proof only.
- No workload/rest or other derived recomputation claim is made.

## 34. Final verdict

**PASS — READY FOR MAIN**

The integrated branch satisfies the CU-03I acceptance statement. The plan gate
remains real and fail closed; for stale/wrong hashes, CU-01 planning may run to
establish mismatch, but canonical reconciliation, mutation, and downstream
impact remain zero.

## 35. Exact recommended repository integration action

Use a separate repository-integration task to fetch and re-verify `origin/main`,
push `feat/change-impact-orchestration` without force, open a PR to `main`, wait
for required hosted PostgreSQL/CI checks, audit the final diff, and merge with a
normal merge commit. Preserve `618d43c2...` and `f476b177...`; do not rebase or
squash. Do not schedule or deploy CU-03 as part of that merge task.

## 36. Exact next slice only after repository merge

Only after CU-03 is safely merged and repository validation passes may a new,
separately authorized CU-04 design consume mutation-scoped affected entities
for incremental workload/rest recalculation. CU-04 is not started here.
