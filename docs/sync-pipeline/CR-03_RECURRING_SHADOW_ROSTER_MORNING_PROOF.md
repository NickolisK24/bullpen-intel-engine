# CR-03 Recurring Shadow, Roster, and Morning Proof

## 1. Objective

CR-03 extends the certified non-publishing shadow path through SP-05 roster and transaction acquisition and the SP-12 morning planner. It also determines whether that exact path can run recurrently in production. Legacy scheduling, publication, and public readers remain authoritative.

## 2. Starting Integration SHA

`b56bb2fe05135eeb4531d2514c6ad62dbdeed627`, the merge commit for PR #825 into `feat/sync-pipeline`.

## 3. Production Configuration Before

Read-only inspection on 2026-09-10 found all Render services deploying from `main`. The relevant live deploy SHA was `aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65` for both continuous cron services.

| Service | Render ID | Cadence | Command | Authority |
|---|---|---:|---|---|
| BaseballOS Continuous Updates | `crn-daaer0e7bikc7388ghag` | `*/3 * * * *` | `cd backend && python scripts/run_continuous_cycle.py` | legacy CU primary |
| baseballos-continuous-shadow-detect | `crn-da98kclg1s2s739k0870` | `*/3 * * * *` | `python backend/scripts/run_continuous_cycle.py --mode shadow_full_chain` | legacy CU shadow command, not SP shadow |
| BaseballOS Morning Primary | `crn-da8ldm6gekts73ao3a6g` | `5 14 * * *` | legacy `run_due_sync.py --mode morning ... --public-only` | legacy primary |
| BaseballOS Daily Primary | `crn-da8f605g1s2s73983o1g` | `5 10 * * *` | legacy daily command | legacy primary |
| BaseballOS Postgame Primary | `crn-da8f4mbtqb8s73a1htdg` | `5 2,4,6 * * *` | legacy postgame command | legacy primary |

The production database is not exposed as a database resource in the inspected Render workspace. Safe production inspection therefore runs inside the isolated GitHub workflow with the configured database secret; credentials are never printed.

Before implementation, production workflow run `34474913176` at exact SHA `b56bb2fe05135eeb4531d2514c6ad62dbdeed627` succeeded. It showed migration head `c9d4e6f8a1b2`, SP shadow entrypoint `production-shadow-v1`, publication pointer `null` to `null`, roster authority `0/30`, and no dead or stale-leased jobs. It also retained current CR-02 evidence: one harmless stale observation and one nonblocking ambiguity did not fail the CU cycle.

## 4. Recurring Shadow Strategy

The safe recurring target is the existing dedicated three-minute Render shadow cron, repointed to:

```text
python backend/scripts/run_sync_pipeline_shadow.py --max-jobs 24 --include-morning --include-continuous-observation
```

It must deploy the reviewed integration SHA and retain the seven safe shadow controls. The current Render service cannot be repointed safely through the available production controls: it tracks `main`, while main changes are forbidden, and the available service tooling does not expose a branch/start-command update. Creating a second cron would duplicate scheduling and cannot safely inherit the existing database secret. Recurrence therefore remains a hard CR-03 blocker unless an authorized Render service update is performed.

## 5. Exact Deployed SHA

The manual production proof records `SYNC_PIPELINE_DEPLOY_SHA` from the exact GitHub checkout in every result. The recurring Render service remains at `aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65` on `main` and is not represented as running the CR-03 code.

## 6. Shadow Job Allowlist

`production-shadow-v2` can claim:

* `FETCH_SCHEDULE`
* `FETCH_ROSTER`
* `FETCH_TRANSACTIONS`
* `FETCH_PREGAME_CONTEXT`
* `FETCH_LIVE_GAME_DELTA`
* `RECONCILE_FINAL_GAME`
* `PROCESS_CANONICAL_IMPACT`
* `PROCESS_DERIVED_INTELLIGENCE`

It cannot claim publication, cache handoff, morning orchestration, or closure work. SP-10 publication dispatch remains disabled. The first 12 default claim slots are reserved for SP-05 acquisition so bounded cycles cannot starve the 30-team sweep behind downstream work.

## 7. SP-05 Roster Execution

The SP-12 shadow morning plan uses the official MLB team enumeration and fails unless it returns exactly 30 unique clubs. It enqueues one `FETCH_ROSTER` job per club. Each owner job acquires official `active` and `40Man` views through SP-03, and SP-05 only mutates membership intervals when both views are complete. Partial evidence remains durable but cannot close prior membership.

Production IDs and counts are recorded after the exact-SHA proof runs.

## 8. Transaction Execution

The morning contract enqueues one league transaction job for D-2 through D. SP-05 owns acquisition, source evidence, normalization, truncation protection, and any targeted roster follow-up. Exactly 1000 rows remain partial by contract. Production range and completeness are recorded after proof.

## 9. 30-Team Coverage

`report_roster_authority_coverage.py` is a read-only report keyed by baseball date and the latest shadow morning run's exact team scopes. For each club it reports the latest active and 40-man attempt, source observation, SyncRun/job, completeness, timestamp/age, and current active pitcher membership count. `29/30`, partial, failed, missing, or unexpected empty active evidence fails the report.

Production coverage evidence is recorded after proof.

## 10. Freshness

Current authority requires a source attempt for the requested baseball date, complete authoritative source evidence, and a current SP-05 active-pitcher interval when the official response is nonempty. Age is measured from the completed source fetch attempt. Forty-man authority is reported independently.

## 11. SP-12 Morning Proof

The shadow cycle runs the SP-12 planner at most once per baseball date under source `sp12_morning_shadow`. It records 30 team scopes, one schedule obligation, 30 roster obligations, one bounded transaction obligation, missing prior Final work, current pregame jobs, and orphaned SP-09/SP-10 work. Closure checks and SP-11 publication obligations are detected but explicitly recorded as suppressed. No child job executes inline in the planner.

Production run and obligation IDs are recorded after proof.

## 12. Queue Behavior

Every cycle reports before/after status counts by allowlisted job type. SP-02 active dedupe, leases, heartbeat, and fencing remain authoritative. The morning plan is reused after its first successful run for the date, and the acquisition reserve drains roster/transaction work across bounded cycles.

## 13. Multiple-Cycle Proof

No recurring exact-SHA cycles can be claimed until the dedicated Render service is repointed. Manual exact-SHA cycles may demonstrate idempotence and queue drain, but they are not recurrence and are labeled separately.

## 14. Natural Roster Mutation

No production mutation is manufactured. Any natural roster/transaction change observed during the proof window is recorded with its source, mutation, impact, and cohort lineage; absence of a natural change is reported explicitly.

## 15. Publication Safety

The required posture remains pipeline on, shadow on, publication/morning/closure controls off, and both legacy controls on. Shadow SP-12 suppresses publication job creation, SP-10 cannot dispatch a publication candidate, the worker cannot claim SP-11, and every cycle verifies `atomic_publication_current` before and after. Public jobs in the shared workflow are skipped for `shadow_sp`.

## 16. Legacy Coexistence

Legacy daily, morning, postgame, CU, roster compatibility, publication, and public reads remain enabled and authoritative. SP-05 adds governed source evidence and membership history. Its compatibility projection uses the existing SP-05 contract and deterministic owner locks; it is not a second publication authority.

## 17. Duplicate Writer Audit

Both paths may observe roster data. During shadow, legacy is product authority and SP-05 is authoritative for its new interval/mutation history plus its already-governed compatibility projection. Complete-source and team-scoped locking rules make repeated equivalent SP-05 work a no-op; partial evidence cannot clear state. No new legacy publication or current-pointer writer was added.

## 18. Health Before and After

Before: roster authority `0/30`; atomic publication intentionally absent; exact current queue and observation evidence are in workflow run `34474913176`.

After evidence is recorded after production proof. Historical failed/partial runs are retained; current-window health is not made green by deleting history.

## 19. Rollback

1. Repoint or disable only the dedicated shadow cron.
2. Set `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false` for that path.
3. Keep both legacy controls true.
4. Keep publication, morning, and closure controls false.
5. Verify legacy daily, morning, postgame, CU, publication, and readers continue.
6. Retain all SP evidence and membership history; no database rollback is required.

## 20. Remaining Certification Blockers

Recurring exact-SHA execution remains blocked until the dedicated Render service can be repointed. Atomic publication and reader cutover remain CR-04 scope. Other blockers are updated after bounded production proof.

## 21. Validation

Focused PostgreSQL validation before production proof: `71 passed, 2 skipped` across shadow, SP-05, SP-12, roster-health, and certification tests.

Final CI and production proof results are recorded after the branch is pushed.

## 22. Verdict

`BLOCKED` unless the dedicated recurring Render shadow service is demonstrably running `production-shadow-v2` at the exact reviewed SHA and multiple natural cycles drain the queue. Manual proof alone cannot satisfy that gate.
