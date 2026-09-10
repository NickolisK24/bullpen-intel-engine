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

Final manual verification workflow `34478842541` ran
`production-shadow-v2` at exact reviewed SHA
`1e5b7a23bf9cf91bcf92a50a9e008a342e261f48` with migration head
`c9d4e6f8a1b2`. It succeeded, reused morning run `6888`, processed 12 bounded
jobs, and retained `30/30` active and 40-man roster coverage.

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

Production SyncRun `6888` planned roster jobs `490` through `519`. Three bounded
manual cycles consumed them in groups of 12, 12, and 6. Every job succeeded.
The active-roster observation IDs were `84, 86, 88, 90, 92, 94, 96, 98, 100,
102, 104, 106, 141, 143, 145, 147, 149, 151, 153, 155, 157, 159, 161, 163,
201, 203, 205, 207, 209, 211`; the paired 40-man observation ID immediately
followed each active ID (`85` through `212`). All 60 observations were authoritative
and complete. Active responses contained 28 players per club and produced 13 to
15 current pitcher intervals per club. No team was empty, missing, partial,
failed, or stale at measurement time.

## 8. Transaction Execution

The morning contract enqueues one league transaction job for D-2 through D. SP-05 owns acquisition, source evidence, normalization, truncation protection, and any targeted roster follow-up. Exactly 1000 rows remain partial by contract. Production job `520`, SyncRun `6888`, acquired `2026-09-08` through `2026-09-10`. It returned 63 of a requested maximum 1000 rows, persisted source observation `213`, classified the response `complete`, stored all 63 records, and found no canonical transaction change. This is a valid natural no-op, not a manufactured mutation.

## 9. 30-Team Coverage

`report_roster_authority_coverage.py` is a read-only report keyed by baseball date and the latest shadow morning run's exact team scopes. For each club it reports the latest active and 40-man attempt, source observation, SyncRun/job, completeness, timestamp/age, and current active pitcher membership count. `29/30`, partial, failed, missing, or unexpected empty active evidence fails the report.

The third bounded manual cycle, workflow run `34477831122`, measured active
coverage `30/30` and 40-man coverage `30/30` for official club IDs `108, 109,
110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 133, 134, 135,
136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 158`. Missing,
partial, failed, stale, and suspicious-empty sets were all empty. The workflow's
overall result remained partial because a separate queued historical finality
fetch could not resolve exactly one game; roster authority itself completed.

## 10. Freshness

Current authority requires a source attempt for the requested baseball date, complete authoritative source evidence, and a current SP-05 active-pitcher interval when the official response is nonempty. Age is measured from the completed source fetch attempt. Forty-man authority is reported independently.

## 11. SP-12 Morning Proof

The shadow cycle runs the SP-12 planner at most once per baseball date under source `sp12_morning_shadow`. It records 30 team scopes, one schedule obligation, 30 roster obligations, one bounded transaction obligation, missing prior Final work, current pregame jobs, and orphaned SP-09/SP-10 work. Closure checks and SP-11 publication obligations are detected but explicitly recorded as suppressed. No child job executes inline in the planner.

The first exact-SHA manual cycle, workflow run `34476575855`, created morning
SyncRun `6888`. The immutable planning result recorded 30 expected/enumerated
teams, schedule job `489`, roster jobs `490` through `519`, transaction job
`520`, bounded missing-Final jobs `521` through `696`, and targeted repair jobs
`697` through `701`. No pregame job was due at that observation time. Closure
check for `2026-09-09` and publication candidates for cohorts `1` through `29`
were detected and explicitly suppressed. The planner returned before child
execution; later shadow cycles consumed children through SP-02.

## 12. Queue Behavior

Every cycle reports before/after status counts by allowlisted job type. SP-02 active dedupe, leases, heartbeat, and fencing remain authoritative. The morning plan is reused after its first successful run for the date, and the acquisition reserve drains roster/transaction work across bounded cycles.

## 13. Multiple-Cycle Proof

No recurring exact-SHA cycles can be claimed until the dedicated Render service is repointed. Manual runs `34476575855`, `34477483370`, and `34477831122` at `89a93a010b6bed43d6dc27b1d87c6fabc6e86c92` demonstrated bounded continuation: the same morning run was reused, active roster work drained `0 -> 12 -> 24 -> 30`, and transaction work completed once. They are operator-dispatched proofs, not recurring execution. The third run also exposed a genuine retryable finality blocker instead of hiding it.

## 14. Natural Roster Mutation

No production mutation was manufactured. Roster reconciliation naturally created
SP-05 membership history while establishing first production authority. The
bounded transaction source changed at the observation layer but all 63 canonical
records were unchanged, so there was no natural transaction mutation to trace.

## 15. Publication Safety

The required posture remains pipeline on, shadow on, publication/morning/closure controls off, and both legacy controls on. Shadow SP-12 suppresses publication job creation, SP-10 cannot dispatch a publication candidate, the worker cannot claim SP-11, and every cycle verifies `atomic_publication_current` before and after. Public jobs in the shared workflow are skipped for `shadow_sp`.

All proof cycles observed the atomic pointer as `null` before and after. A
separate read-only production API check on 2026-09-10 continued to serve legacy
dashboard snapshot `2604`, SyncRun `6770`, published at
`2026-09-10T10:09:34.990858`, with data through `2026-09-09`. Thus the new
shadow evidence did not become public authority.

## 16. Legacy Coexistence

Legacy daily, morning, postgame, CU, roster compatibility, publication, and public reads remain enabled and authoritative. SP-05 adds governed source evidence and membership history. Its compatibility projection uses the existing SP-05 contract and deterministic owner locks; it is not a second publication authority.

## 17. Duplicate Writer Audit

Both paths may observe roster data. During shadow, legacy is product authority and SP-05 is authoritative for its new interval/mutation history plus its already-governed compatibility projection. Complete-source and team-scoped locking rules make repeated equivalent SP-05 work a no-op; partial evidence cannot clear state. No new legacy publication or current-pointer writer was added.

## 18. Health Before and After

Before: roster authority `0/30`; atomic publication intentionally absent; exact current queue and observation evidence are in workflow run `34474913176`.

After: authoritative active and 40-man coverage are both `30/30`; all roster and
transaction jobs from morning run `6888` are succeeded; atomic publication is
still absent. The third cycle moved roster pending from 6 to 0 and transaction
pending from 1 to 0. The wider shadow queue still contained 141 pending and one
retry-wait final-reconciliation job plus 64 pending impact jobs, so steady-state
recurring drain is not certified. Historical failed/partial runs remain intact.

The final exact-SHA cycle succeeded and moved 12 final-reconciliation jobs to 12
new impact jobs without increasing the combined bounded queue (`218` before and
after across the displayed nonterminal allowlist). SP-14 health then reported
roster authority 30, no dead jobs, no stale leases, no unreconciled Final games,
one retry-wait job, five overdue polls, and the expected blocker
`atomic_current_publication_missing`. Its `last_recurring_shadow_job_id=450`
still referred to the old deployed recurring path, proving the manual exact-SHA
run had not been misclassified as recurrence.

## 19. Rollback

1. Repoint or disable only the dedicated shadow cron.
2. Set `SYNC_PIPELINE_SHADOW_MODE=false` or `SYNC_PIPELINE_ENABLED=false` for that path.
3. Keep both legacy controls true.
4. Keep publication, morning, and closure controls false.
5. Verify legacy daily, morning, postgame, CU, publication, and readers continue.
6. Retain all SP evidence and membership history; no database rollback is required.

## 20. Remaining Certification Blockers

Recurring exact-SHA execution remains blocked until the dedicated Render service can be repointed. The wider queue also needs recurrent drain and the retrying historical finality job needs owner-path resolution. Atomic publication and reader cutover remain CR-04 scope.

## 21. Validation

Focused PostgreSQL validation after final production proof: `71 passed, 2 skipped
in 7.24s` across shadow, SP-05, SP-12, roster-health, and certification tests.

Production proof used GitHub workflow runs `34474913176`, `34476575855`,
`34477483370`, `34477831122`, and final exact-SHA run `34478842541` (success).
Required PR CI is the final integration check.

## 22. Verdict

`BLOCKED` unless the dedicated recurring Render shadow service is demonstrably running `production-shadow-v2` at the exact reviewed SHA and multiple natural cycles drain the queue. Manual proof alone cannot satisfy that gate.
