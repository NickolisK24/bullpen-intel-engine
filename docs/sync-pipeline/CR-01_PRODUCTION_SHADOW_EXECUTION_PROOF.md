# CR-01 Production Shadow Execution Proof

## 1. Objective

CR-01 closes only the production-certification blocker that the completed sync pipeline was dormant and had no natural production lineage. It activates bounded shadow acquisition and processing while legacy publication and legacy schedulers remain production authority.

## 2. Starting Integration SHA

`7044d70722a933e62ef8a5434a97523e9ce978df`

## 3. Production Configuration Before

Read-only Render inspection on 2026-09-09/10 found every BaseballOS service deploying from `main`, not `feat/sync-pipeline`.

| Service | Render ID | Deployed branch/commit | Cadence | Command | Observed role |
|---|---|---|---|---|---|
| BaseballOS API | `srv-d7qp8na8qa3s73d149sg` | `main` / `361d727c8986ea00efec372765eff8ac3d3d8e83` | continuous | `bash scripts/render_start.sh` | public API |
| BaseballOS Continuous Updates | `crn-daaer0e7bikc7388ghag` | `main` / `77fda302f732a3dfc4d1e0af00185fc5ffb260d0` | `*/3 * * * *` | `cd backend && python scripts/run_continuous_cycle.py` | legacy full-live CU |
| baseballos-continuous-shadow-detect | `crn-da98kclg1s2s739k0870` | `main` / `77fda302f732a3dfc4d1e0af00185fc5ffb260d0` | `*/3 * * * *` | `python backend/scripts/run_continuous_cycle.py --mode shadow_full_chain` | legacy CU shadow, disabled |
| BaseballOS Morning Primary | `crn-da8ldm6gekts73ao3a6g` | `main` | `5 14 * * *` | `run_due_sync.py --mode morning ... --public-only` | legacy |
| BaseballOS Daily Primary | `crn-da8f605g1s2s73983o1g` | `main` | `5 10 * * *` | `run_due_sync.py --mode daily ... --public-only` | legacy |
| BaseballOS Postgame Primary | `crn-da8f4mbtqb8s73a1htdg` | `main` | `5 2,4,6 * * *` | `run_due_sync.py --mode postgame ... --public-only` | legacy |

The Render workspace exposes no BaseballOS PostgreSQL resource. Application services connect through their configured database environment, so production lineage must be inspected by a read-only command running inside a BaseballOS service rather than by copying credentials.

## 4. Shadow Kill Switch Root Cause

The three-minute shadow cron invokes the legacy CU-08 `continuous_execution.run_continuous_cycle` path. That path is gated by `BASEBALLOS_CONTINUOUS_ENABLED`, not by the SP-14 `SYNC_PIPELINE_*` controls. Its production result was repeatedly:

* `mode=shadow_full_chain`
* `status=off`
* `reason_code=kill_switch_disabled`
* `sync_run_id=null`

Even if that legacy switch were enabled, the command would run CU shadow logic. It would not provide a deployed consumer for the completed SP-02 `sync_pipeline` lane. No Render service before CR-01 ran the SP-04 through SP-10 worker chain.

## 5. Shadow Entry Point

CR-01 adds:

```text
python backend/scripts/run_sync_pipeline_shadow.py --max-jobs 24
```

The one-shot command:

1. validates the exact activation-control posture;
2. requires the current database migration head;
3. seeds or reuses one current-date SP-04 schedule job;
4. consumes at most 24 eligible jobs;
5. schedules SP-06 and SP-08 work after a schedule poll;
6. reports exact lineage IDs;
7. verifies the SP-11 pointer did not change.

It has no busy loop and relies on SP-02 active dedupe, leases, heartbeat, retry, and fencing.

## 6. Worker / Queue Execution Path

The shadow worker claims only:

* `fetch_schedule`
* `fetch_pregame_context`
* `fetch_live_game_delta`
* `reconcile_final_game`
* `process_canonical_impact`
* `process_derived_intelligence`

It does not claim publication, cache handoff, morning, closure, repair, roster, transaction, or legacy job types. The three-minute shadow cron is reused; no second scheduler is introduced.

## 7. Database Access Method

The entrypoint uses the service's existing `DATABASE_URL` without printing it. It queries only `alembic_version` before execution and fails unless the head is `c9d4e6f8a1b2`. Its structured result exposes record IDs, not credentials or raw source payloads. The SP-14 certification command remains the read-only health inspection path inside the deployed environment.

## 8. Shadow Write Boundary

| State | Shadow policy |
|---|---|
| SP-01 runs / SP-02 jobs / SP-03 evidence | permitted |
| SP-04 operational game state | permitted |
| SP-06 pregame versions and mutations | permitted |
| SP-08 provisional state and mutations | permitted |
| SP-07 final immutable versions, mutations, and GameLog compatibility projection | permitted under existing SP-07 authority |
| SP-09 impact plans | permitted |
| SP-10 cohorts and candidate snapshots | permitted |
| SP-11 publication candidate job | suppressed in the shadow worker |
| SP-11 current pointer/cache handoff | forbidden and unclaimable |
| Legacy snapshots/publication pointers | legacy-only |

## 9. Publication Safety

The required configuration is:

```text
SYNC_PIPELINE_ENABLED=true
SYNC_PIPELINE_SHADOW_MODE=true
SYNC_PIPELINE_PUBLICATION_ENABLED=false
SYNC_PIPELINE_MORNING_ENABLED=false
SYNC_PIPELINE_CLOSURE_ENABLED=false
BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true
BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true
```

Invalid parent/child, shadow/publication, or duplicate-publication combinations fail before a job is planned. SP-10 is invoked with publication-candidate dispatch disabled. SP-11 jobs are absent from the claim allowlist. The current pointer is compared before and after every cycle.

## 10. Duplicate Writer Safety

Legacy scheduling and publication remain enabled. New immutable source/canonical/impact/cohort records are governed by their SP owners and deterministic dedupe/version contracts. The new worker does not write legacy snapshot/publication state and cannot advance the SP-11 current pointer. GameLog remains the already-governed SP-07 compatibility projection; it is not treated as new public publication authority.

## 11. Production Configuration After

This section records the reviewed Render deployment, exact flag values, and deployed commit after activation. It must be completed from live configuration before CR-01 can pass.

## 12. Natural MLB Evidence

Pending safe deployment. No production mutation will be manufactured. The first natural current-date schedule/state change observed by the new entrypoint will be recorded here.

## 13. Exact Lineage IDs

Pending safe deployment and natural execution. Required identifiers are SyncRun, SyncJob, SourceObservation, and gamePk; mutation, impact-plan, and cohort IDs are recorded when naturally produced.

## 14. Health Report

Pending safe deployment. The report must show pipeline enabled, shadow enabled, publication disabled, both legacy authorities enabled, and current queue/run/source obligations.

## 15. Remaining Blockers

At implementation time:

* the integration branch is not yet deployed by any Render service;
* production migration head and lineage must be verified inside a deployed BaseballOS service;
* a natural MLB change must traverse the new path;
* the legacy CU partial-run problem remains CR-02 unless it prevents this shadow path.

## 16. Rollback Procedure

1. Set `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false` on the shadow service.
2. Leave `BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true`.
3. Leave `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true`.
4. Verify the shadow command fails closed before creating a new job.
5. Confirm daily, morning, postgame, and continuous legacy services remain enabled.
6. Retain all additive shadow evidence; no migration downgrade or data deletion is required.

## 17. Validation

Focused local validation at implementation time:

* shadow/configuration/derived tests: `31 passed, 1 skipped`
* backend CI shard accounting: `438` files and `9,829` node IDs, no missing or duplicate coverage

PostgreSQL and full CI results are recorded after the final branch commit is pushed.

## 18. CR-01 Verdict

`BLOCKED` until a reviewed production deployment runs the new entrypoint, a worker consumes real SP-02 work, and exact natural lineage IDs are captured. The code change alone does not close CR-01.
