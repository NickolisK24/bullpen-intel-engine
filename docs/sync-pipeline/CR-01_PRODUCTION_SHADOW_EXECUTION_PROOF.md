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

It does not claim publication, cache handoff, morning, closure, repair, roster, transaction, or legacy job types. Before merge, the new path is invoked by the existing `baseballos-sync.yml` workflow's manual-only `shadow_sp` mode. The old three-minute Render shadow cron remains unchanged because it deploys `main` and runs the legacy CU command; repointing it before this branch is reviewed would not be safe.

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

The Render services and their legacy schedules were not changed. Production shadow proof ran in the isolated `sync-pipeline-shadow` GitHub job at commit `ec02c78be78f4eaa7f693fdd0e1f6c9dadbd07b2`, using the production application database with these job-scoped controls:

| Control | Value |
|---|---:|
| `SYNC_PIPELINE_ENABLED` | `true` |
| `SYNC_PIPELINE_SHADOW_MODE` | `true` |
| `SYNC_PIPELINE_PUBLICATION_ENABLED` | `false` |
| `SYNC_PIPELINE_MORNING_ENABLED` | `false` |
| `SYNC_PIPELINE_CLOSURE_ENABLED` | `false` |
| `BASEBALLOS_LEGACY_PUBLICATION_ENABLED` | `true` |
| `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED` | `true` |

The job applies only additive migrations before execution. Workflow run `34427659598` skipped `public-sync`, legacy intraday work, internal enrichment, static distribution, and the legacy shadow-health job. The existing Render legacy services remained deployed and scheduled throughout.

## 12. Natural MLB Evidence

No fixture or operator-created baseball mutation was used. Production run `34427035335` read MLB's official September 9 slate and persisted schedule observation `1`. It classified 15 real games: ten Final transitions and five live starts. The live games produced 30 provisional mutation rows across teams `109`, `112`, `113`, `118`, `119`, `121`, `134`, `145`, `146`, and `158`.

Production run `34427358337` then observed a meaningful official change for gamePk `824871`: schedule observation `37` classified `game_final_corrected`, job `381` reconciled final-game version `11`, and final mutation `100` was persisted. The same run observed additional natural live workload changes: observations `39`, `40`, and `41` produced seven live mutations, with later observations `42`, `43`, and `48` producing three more.

The final proof run `34427659598` retained subject-level evidence. Complete live-feed observation `49` for gamePk `824064` (version `4`) changed pitcher `42` for team `109`; job `393` created its live mutation and job `417` created impact plan `17`. Complete observations `50`–`52`, `54`, and `55` independently proved continuing natural updates for gamePks `824549`, `823818`, and `823739`.

## 13. Exact Lineage IDs

Initial schedule-to-owner lineage from run `34427035335`:

* SP-04: job `336`, SyncRun `6533`, SourceObservation `1`.
* SP-08: jobs `348`–`352`, SyncRuns `6534`, `6535`, `6536`, `6537`, and `6539`, SourceObservations `2`–`6`, live mutations `1`–`30`.
* SP-07: jobs `337`–`346`, SyncRuns `6540`–`6549`, final game versions `1`–`10`, final mutations `1`–`99`.
* SP-09: jobs `353`, `355`, `357`, `359`, `361`, `363`–`365`; SyncRuns `6550`–`6557`; impact plans `1`–`8`.
* SP-10: job `373` / SyncRun `6607` consumed impact plan `1` for gamePk `823739` and completed derived cohort `1`; `publication_candidate_job_id` remained `null`.

Correction lineage from runs `34427358337` and `34427659598`:

* gamePk `824871` → schedule job `347` / SyncRun `6559` / SourceObservation `37`.
* `RECONCILE_FINAL_GAME` job `381` / SyncRun `6570` → final game version `11` / mutation `100` → impact job `403` / SyncRun `6606` → impact plan `28` → derived job `445` queued.

No publication candidate was created in any proof run.

## 14. Health Report

The read-only health report at `2026-09-10T01:57:22.864691` confirmed the seven controls above with zero activation violations. It reported:

* migration head `c9d4e6f8a1b2`;
* `352` succeeded jobs, `36` pending, `1` running, `27` failed, `0` retry-wait, `0` dead, and `0` stale leases;
* `0` failed source attempts, `3` partial attempts, and `0` unreconciled Final games;
* `0` publication candidates, `0` cache-handoff failures, and `0` publication-pointer inconsistencies;
* no atomic current publication, matching the shadow/no-cutover posture.

The broader SP-14 result remains `NO-GO`. The health status is `blocked` because atomic publication is not cut over and SP-05 roster authority has not yet established 30-team production coverage. The report also retained existing failed-job and live-observation signals for later remediation; CR-01 does not relabel them healthy.

## 15. Remaining Blockers

After the production proof:

* the permanent three-minute Render shadow service still runs the legacy CU command from `main`; a reviewed deployment change is needed to make CR-01's entrypoint recurrent;
* SP-05 production roster authority remains `0/30`, so the overall SP-14 verdict remains `NO-GO`;
* atomic publication/current-reader cutover remains intentionally disabled;
* existing continuous-update partial/failing runs remain CR-02 scope because they did not prevent the isolated SP shadow path from succeeding;
* queued SP-10 work needs further shadow cycles, while one natural cohort and SP-01/SP-02/SP-03 plus live/final/SP-09 lineage are proven.

## 16. Rollback Procedure

1. Set `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false` on the shadow service.
2. Leave `BASEBALLOS_LEGACY_PUBLICATION_ENABLED=true`.
3. Leave `BASEBALLOS_LEGACY_SCHEDULERS_ENABLED=true`.
4. Do not dispatch the manual `shadow_sp` workflow mode; if a permanent service is later configured, disable its two pipeline flags.
5. Confirm daily, morning, postgame, and continuous legacy services remain enabled.
6. Retain all additive shadow evidence; no migration downgrade or data deletion is required.

## 17. Validation

Focused local validation before the final documentation commit:

* shadow/configuration/derived tests: `19 passed, 1 skipped` after lineage-report expansion;
* combined shadow/configuration/certification/workflow tests: `203 passed, 1 skipped`;
* backend CI shard accounting: `438` files and `9,831` node IDs, no missing or duplicate coverage.

Production workflow evidence:

* run `34427035335`: succeeded; `24` bounded jobs; `36` source observations; publication pointer `null` → `null`;
* run `34427358337`: succeeded; `24` bounded jobs; `12` source observations; publication pointer `null` → `null`;
* run `34427659598`: succeeded at commit `ec02c78be78f4eaa7f693fdd0e1f6c9dadbd07b2`; `24` bounded jobs; `7` subject-identified source observations; `8` live mutations; `12` impact plans; completed cohort `1`; publication pointer `null` → `null`.

Final pull-request CI is recorded in the PR before merge.

PostgreSQL and full CI results are recorded after the final branch commit is pushed.

## 18. CR-01 Verdict

`PASS` for the scoped CR-01 blocker. The new entrypoint executed against production data, consumed real SP-02 work, persisted SP-01/SP-03 and natural live/final/impact/cohort lineage, and could not advance publication authority. The overall SP-14 certification remains `NO-GO`; recurrent Render scheduling, roster coverage, publication cutover, and the existing continuous-update failure stream remain separate certification work.
