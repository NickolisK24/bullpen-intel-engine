# BaseballOS Sync Pipeline Production Manifest

## Authority map

This manifest describes the intended SP-00 through SP-14 production architecture. It does not activate it. Until the SP-14 certification verdict becomes GO, the established daily, morning, postgame, and continuous paths remain production authority.

| Layer | Owner | Durable records | Primary job types |
|---|---|---|---|
| Runs | SP-01 | `sync_runs`, `sync_run_scopes` | all pipeline jobs |
| Queue | SP-02 | `sync_jobs`, `sync_job_attempts` | durable claim, retry, lease, dead letter |
| Source evidence | SP-03 | `source_subjects`, `source_observations`, `source_fetch_attempts`, `source_payload_artifacts` | source-owner fetch jobs |
| Game state | SP-04 | `scheduled_games` game-state fields | `FETCH_SCHEDULE`, `RECONCILE_FINAL_GAME` |
| Roster/transactions | SP-05 | roster intervals/mutations and transaction versions | `FETCH_ROSTER`, `FETCH_TRANSACTIONS` |
| Pregame | SP-06 | current scheduled-game projection plus context versions/mutations | `FETCH_PREGAME_CONTEXT` |
| Final game | SP-07 | final game and appearance versions/mutations; `game_logs` compatibility projection | `RECONCILE_FINAL_GAME` |
| Live game | SP-08 | provisional appearance state and live mutations | `FETCH_LIVE_GAME_DELTA` |
| Impact | SP-09 | canonical impact plans, mutation and entity associations | `PROCESS_CANONICAL_IMPACT` |
| Derived | SP-10 | derived cohorts, domain outcomes, inputs, candidate snapshots | `PROCESS_DERIVED_INTELLIGENCE` |
| Publication | SP-11 | atomic publications, artifacts, current pointer, cache handoffs | `PUBLISH_DERIVED_COHORT`, `HANDOFF_PUBLICATION_CACHE` |
| Daily closure | SP-12 | date closures, versions, blockers | `RUN_MORNING_RECONCILIATION`, `CHECK_BASEBALL_DATE_CLOSURE` |
| Repair | SP-13 | repair requests, chunks, blockers | repair planner/checker plus owner jobs |
| Certification | SP-14 | certification runs/checks and legacy transition states | operator-invoked certification command |

## Run types

SP-01 owns the controlled vocabulary. Relevant top-level modes are morning reconciliation, nightly finalization, targeted repair, backfill, full reconciliation, and publication. Child work retains correlation and parent-run lineage.

## Source domains

Official MLB schedule/game status, rosters, transactions, pregame context, final boxscore, final play-by-play, and live feed are acquired through SP-03-aware owner services. Unknown, partial, failed, or unavailable sources never become guessed facts.

## Activation controls

All new controls default to false:

* `SYNC_PIPELINE_ENABLED`
* `SYNC_PIPELINE_SHADOW_MODE`
* `SYNC_PIPELINE_PUBLICATION_ENABLED`
* `SYNC_PIPELINE_MORNING_ENABLED`
* `SYNC_PIPELINE_CLOSURE_ENABLED`

Existing authority is described explicitly:

* `BASEBALLOS_LEGACY_PUBLICATION_ENABLED` defaults to true.
* `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED` defaults to true.

Unsafe combinations are rejected by the SP-14 certification command. Shadow mode cannot publish. New and legacy publication writers cannot both be enabled. New morning/closure orchestrators cannot run beside legacy schedulers outside shadow mode.

## Current production schedule

Read-only Render inspection on 2026-09-09 found these repository-backed services on `main`:

| Service | UTC cadence | Command | Current role |
|---|---:|---|---|
| BaseballOS Daily Primary | `5 10 * * *` | `run_due_sync.py --mode daily` | primary legacy authority |
| BaseballOS Morning Primary | `5 14 * * *` | `run_due_sync.py --mode morning` | primary legacy schedule refresh |
| BaseballOS Postgame Primary | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame` | primary legacy final/publication path |
| BaseballOS Continuous Updates | `*/3 * * * *` | `run_continuous_cycle.py` | current continuous full-live path |
| baseballos-continuous-shadow-detect | `*/3 * * * *` | `run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation` | recurring non-publishing SP verifier on `feat/sync-pipeline@63f87f...8ed` |

GitHub Actions remains scheduled at 10:17, 14:23, and 02:11/04:11/06:11 UTC as fallback/reconciliation. No schedule is changed by SP-14 while the verdict is NO-GO.

CR-03 extends the manual `shadow_sp` workflow mode with the non-publishing SP-05 roster/transaction worker path and one idempotent SP-12 morning plan per baseball date. CR-04 repointed the dedicated Render shadow cron to that certified entrypoint. The service now runs every three minutes from `feat/sync-pipeline` at exact deployed SHA `63f87feb421eb446fae09d28ab86390ecbbbb8ed`; its runtime flags keep publication, closure, and production morning authority disabled while retaining both legacy authority controls.

## Target architecture and cadence

After all certification gates pass:

1. Render scheduled planners create bounded SP-04, SP-05, SP-06, and SP-12 work.
2. A durable worker consumes SP-02 jobs with leases, heartbeat, fencing, and bounded concurrency.
3. Active games use SP-04 planning and SP-08 60–120 second live polling; delayed/suspended policies slow appropriately.
4. SP-07 final reconciliation hands one mutation cohort through SP-09, SP-10, and SP-11.
5. Morning reconciliation runs once before the normal use window; nightly closure checks after the game window and reschedules blocked dates without busy waiting.
6. GitHub remains a due-window verifier/fallback rather than a second independent writer.

Exact Render commands, concurrency, and final UTC schedules require a separate reviewed production change after certification.

## Current legacy decisions

* Legacy daily, morning, postgame, continuous, incremental intelligence, and publication remain primary.
* The configured shadow cron remains the legacy CU verifier and is not the certified SP shadow entrypoint.
* Request-time and independently resolved public reads remain a retirement blocker until they consume one SP-11 publication identity.
* Manual intraday repair remains available; SP-13 is not activated automatically.
* No legacy code is deleted in this package.

## CR-01 shadow execution boundary

`python backend/scripts/run_sync_pipeline_shadow.py --include-morning` is the only production shadow entrypoint for the completed SP pipeline with SP-05/SP-12 planning. It seeds current-date SP-04 work, plans the morning contract once per baseball date, and drains a bounded SP-02 allowlist:

* `FETCH_SCHEDULE`
* `FETCH_ROSTER`
* `FETCH_TRANSACTIONS`
* `FETCH_PREGAME_CONTEXT`
* `FETCH_LIVE_GAME_DELTA`
* `RECONCILE_FINAL_GAME`
* `PROCESS_CANONICAL_IMPACT`
* `PROCESS_DERIVED_INTELLIGENCE`

SP-10 receives `publication_candidate_enabled=false` in this path. SP-12 morning planning explicitly records but suppresses publication and closure obligations. The worker cannot claim `PUBLISH_DERIVED_COHORT`, `HANDOFF_PUBLICATION_CACHE`, morning orchestration, or closure jobs. Twelve of the 24 default claim slots are reserved for roster/transaction work so the 30-team sweep drains across bounded cycles. The entrypoint snapshots the SP-11 current pointer before work and fails if it changes. Legacy publication and legacy scheduler controls must remain enabled, or the entrypoint rejects the configuration before planning work.

## Rollback

Set every `SYNC_PIPELINE_*` control to false. Leave the additive evidence tables intact. Keep or restore `BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true` and `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true`. Confirm the established Render daily/morning/postgame/continuous services and GitHub fallback remain enabled. A rollback never deletes observations, canonical versions, cohorts, publications, closures, or repair history.

## CR-04 deployment gate

The original Render blocker was manually resolved on 2026-09-10. Dedicated cron
`crn-da98kclg1s2s739k0870` now deploys `feat/sync-pipeline`, runs
`production-shadow-v2` every three minutes, and reports exact code SHA
`63f87feb421eb446fae09d28ab86390ecbbbb8ed`. More than three naturally scheduled
successful cycles consumed bounded SP-02 work, preserved 30/30 active and 40-man
roster authority, retained CR-02 no-op/warning semantics, and left the atomic
publication pointer null.

Three rescheduled-game failures exposed an SP-07 row-selection defect. The
reviewed fix selects the safe Final row for the requested baseball date. Two
retrying jobs succeeded normally; terminal job `637` remains immutable evidence
but was governed through SP-13 request `1` and replacement SP-07 job `996`, which
created current final version `192`. Health now distinguishes that resolved dead
history from blocking dead work.

Publication and consumer cutover still remain fail-closed. The recurring service
does not yet deploy the CR-04 repair commit, its downstream backlog has not yielded
a selected/revalidated first current cohort, there is no atomic current
publication, and no public endpoint consumes the SP-11 bundle. Legacy schedulers,
publication, and readers remain authoritative. Exact evidence and remaining
preconditions are recorded in
`CR-04_INTEGRATION_DEPLOYMENT_ATOMIC_PUBLICATION_CUTOVER.md`.
