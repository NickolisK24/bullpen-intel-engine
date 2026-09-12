# SP-14 — Production Certification, Activation & Legacy Retirement

## 1. Objective

Certify SP-00 through SP-13, make their operational state queryable, define a reversible cutover, and prevent legacy retirement until production evidence proves the replacement. SP-14 adds no baseball metric or public semantic.

## 2. Exact Certified SHA

The package base is `a950b0a79fddb681509e55bd7bb2e6f71dd84339`. The final branch SHA is recorded in the PR closeout after all validation. No production deployment of this branch occurred during certification.

## 3. Migration Head

`c9d4e6f8a1b2` adds only certification evidence and legacy transition tables. Empty-database upgrade and migration round-trip are certification requirements.

## 4. Legacy vs New Responsibility Map

The complete queryable map is returned by `legacy_responsibility_map()` and persisted to `sync_legacy_transition_states` only on an explicit record run. Current decisions:

* Daily, morning, postgame, full-live continuous, derived, and publication paths remain primary.
* SP-01 through SP-13 remain dormant/new-table paths pending shadow proof.
* Atomic publication consumer migration, request-time authority-write audit, and complete natural lineage are blockers.
* Nothing is disabled or deleted.

The detailed table, commands, schedule, and rollback are in `SYNC_PIPELINE_PRODUCTION_MANIFEST.md`.

## 5. Certification Gates

| Gate | Current verdict | Required evidence before PASS |
|---|---|---|
| A Schema / Migration | PASS locally | one head; empty PostgreSQL upgrade; round-trip |
| B Queue / Worker | BLOCKED for production | natural durable queue flow plus crash/lease/dead-letter recovery |
| C Source Evidence | BLOCKED for production | natural immutable observation/no-op/correction/partial proof |
| D Game Lifecycle | BLOCKED | one complete scheduled → pregame → live → final lifecycle under the new pipeline, plus edge states |
| E Roster / Transactions | BLOCKED | new-pipeline 30-team roster evidence and one natural change when available |
| F Final / Live Authority | BLOCKED | SP-08 live IDs superseded by SP-07 final IDs without double counting |
| G Impact / Derived | BLOCKED | natural exact-scope plan/cohort with input watermark and bounded recompute |
| H Publication | FAIL | public readers do not yet resolve the SP-11 atomic current pointer |
| I Daily Completeness | BLOCKED | natural morning and overnight closure/reopen cycle |
| J Repair / Backfill | PASS in focused fixture; BLOCKED for production | disposable PostgreSQL scale/resume drill and audited operator evidence |

Any critical failed, blocked, or not-run check yields `NO-GO`. A noncritical warning may coexist with GO only when every critical check passes.

September 11 AUDIT-R3 revalidation: Gate G remains blocked by F03's incomplete
actual input manifest. Gate H remains blocked by F04/F05. R3-A makes reader
admission unconditional and affected-game-specific, but does not certify full
reader contracts, population denominators, comparison semantics, or activation.
The exact recovered findings and ordered remaining work are recorded in
[AUDIT-R3 publication integrity](AUDIT-R3_PUBLICATION_INTEGRITY.md). Historical
gate evidence below is not a current deployment attestation.

## 6. Certification Evidence

`sync_certification_runs` stores exact SHA, migration head, environment, configuration fingerprint, gate statuses, proof identifiers, failures, warnings, and verdict. `sync_certification_checks` stores one immutable measured check per gate. Identical evidence reuses the same certification run; it is not silently rewritten.

Certification version: `sync-pipeline-certification-v1`.

## 7. Observability Contract

`collect_operational_health()` reports:

* queue depth by status, retry-wait, dead jobs, and stale leases;
* recent failed/partial source attempts;
* overdue game polls and live games without a recent observation;
* unreconciled Final games and roster-authority team count;
* plans awaiting dispatch; running/stale/failed cohorts;
* preparing/ready publications and current pointer consistency;
* cache handoff retry state;
* blocked/reopened closures; active/blocked repairs.

The command emits structured JSON and exits nonzero for NO-GO. No frontend dashboard or unauthenticated endpoint was added.

## 8. Operational Health

`healthy` means no alertable condition is present. `degraded` includes retries, source partials/failures, overdue polls, pending plans/cohorts/publications, cache retry, or active repairs. `blocked` includes dead jobs, fewer than 30 authoritative roster subjects, a missing/inconsistent atomic publication pointer, unreconciled Finals, blocked/reopened closures, or blocked/failed repairs.

These are operator states only and do not alter public confidence wording.

## 9. Production Configuration

Read-only Render inspection on 2026-09-09 identified five BaseballOS cron services on `main`: daily 10:05 UTC, morning 14:05 UTC, postgame 02:05/04:05/06:05 UTC, and two `*/3` continuous jobs. GitHub fallback runs at 10:17, 14:23, and 02:11/04:11/06:11 UTC.

Recent Render evidence showed:

* Full-live runs 6498–6500 ended partial and their cron invocations exited 1 after stale/ambiguous observation rejections.
* The separate `shadow_full_chain` cron exited successfully but reported `kill_switch_disabled`, zero games checked, and no run ID.
* Morning execution 101 succeeded and verified legacy publication; it did not exercise SP-12.

No Render configuration is changed. No BaseballOS Postgres instance was visible through the connected Render workspace, so production database SP tables could not be queried through that connector.

## 10. Activation Stages

0. **Dark:** all `SYNC_PIPELINE_*` controls false; current state.
1. **Shadow:** enable the pipeline and shadow mode only; publication/morning/closure remain false.
2. **Acquisition/canonical:** after Gates B–F pass, enable owner workers while legacy publication remains authority; isolate duplicate canonical writers.
3. **Derived/publication:** after consumer migration and Gates G–H pass, disable the legacy publication writer before enabling SP-11 publication.
4. **Full pipeline:** after Gates I–J and a full operational cycle, enable SP-12 planners and disable overlapping legacy schedules.

Each stage requires a separate PASS verdict. A failed or blocked stage stops progression.

## 11. Feature Flags

The seven flags and safe defaults are listed in the production manifest. Validation rejects parent-disabled children, shadow publication, duplicate publication writers, and overlapping non-shadow morning/closure orchestrators.

## 12. Natural MLB Proof

At 2026-09-09 during the implementation window, the official MLB schedule returned 15 games and exactly 30 distinct MLB clubs. It contained five Final games, nine In Progress games, one Warmup game, and one Pre-Game game. All 15 schedule entries named both probable starters.

Game `824791` was observed In Progress in inning 5. Official live-feed pitching state showed away starter Foster Griffin (MLBAM 656492) at 62 pitches/7 outs, followed by Matt Festa (670036) at 31 pitches/7 outs and Franco Aleman (680916) at 4 pitches/1 out. This proves a natural starter exit and multiple reliever entries in the official source. It does not prove SP-08 production lineage because SP-08 was not deployed.

No natural roster/transaction change was manufactured.

## 13. Live→Final Proof

Fixture and PostgreSQL package tests cover authority supersession. Natural source evidence exists for a live bullpen event, but there is no deployed SP-08 observation/mutation ID followed through SP-07. Gate F remains blocked.

## 14. Final→Impact→Derived→Publication Proof

The SP-14 full-chain fixture establishes:

`SP-03 source observation → SP-07 final versions/mutations → SP-09 plan → SP-10 cohort → SP-11 publication → SP-12 closure`.

It then applies an official-line correction, preserves final V1, creates V2, reopens closure, creates a targeted corrected plan/cohort/publication, and recloses while preserving `closed → reopened → closed` history. The test exposed and fixed two lineage defects: superseded publications now satisfy their historical plan obligation, and corrected-final cohorts select final/corrected-final predecessors.

Natural production IDs for this complete new chain are unavailable; the gate remains blocked for production.

## 15. 30-Team Morning Proof

SP-12 tests prove a strict 30-team denominator and fail closed at 29. The official schedule read independently contained all 30 teams on 2026-09-09. Render morning execution 101 used the legacy schedule-only path. A natural SP-12 30-team run has not occurred, so Gate E/I remains blocked.

## 16. Nightly Closure Proof

The full-chain fixture proves close, correction reopen, targeted downstream processing, new publication, and reclose without losing the first closure. Natural production closure IDs do not exist because SP-12 is dormant.

## 17. Repair/Backfill Proof

Focused SP-13 tests prove dry run, bounded chunks, resumability, source partial blocking, method/rule replay, owner routing, and closure reopen. The full-chain test additionally proves a one-game dry run cannot mutate or publish. Seven-day production-like scale and natural repair IDs remain unmeasured.

## 18. Parity Matrix

| Case | Evidence | Classification |
|---|---|---|
| final appearances/team-at-appearance | SP-07/CU fixtures | semantic parity |
| many-reliever affected scope | SP-09 parity fixture | semantic parity |
| one-pitcher correction | SP-07–SP-11 fixtures | intentional immutable-version improvement |
| probable-starter change | SP-06/SP-09 fixture | bounded context-only parity |
| live appearance update | SP-08/SP-09 fixture | provisional structural improvement |
| workload/rest, arm read, Team State | SP-10 CU parity fixtures | semantic parity |
| 30-team morning | SP-12 fixture; official source denominator | production activation not proven |
| public read generation | SP-11 bundle fixture | blocker: current APIs still use legacy identities |
| publication data-through | legacy production API plus SP-11 fixture | structural parity not production-proven |

No unexplained difference is classified PASS.

## 19. Performance Results

Focused SQLite certification/full-chain tests are timed in the validation closeout. Natural MLB schedule and live-feed reads completed below the 20-second client bound. Production SP-01–SP-13 median/p95 timings are unavailable because the new pipeline is dormant; they remain a required shadow-stage measurement rather than an invented baseline.

## 20. Failure/Recovery Drills

The package suites cover source failure/partial, crash rollback, stale lease fencing, retry/dead state, duplicate work, final transaction rollback, input drift, pointer failure before commit, cache retry, blocked closure, and resumable repair. These are disposable DB/fixture proofs. Production recovery drills remain blocked until Stage 1.

## 21. Consumer Migration

`read_current_publication_bundle()` resolves one SP-11 pointer and all artifacts under that generation. Existing public endpoints do not call it. The Team Board exposes a coherent legacy `publication_identity` (production snapshot 2521, sync run 6220 during the read-only check), but that identity is not an SP-11 atomic publication ID and other public families remain independently resolved. Consumer migration is therefore a Gate H blocker.

## 22. Publication Cutover

No cutover occurs. Before cutover, backend readers must resolve one SP-11 identity once per request; parity, fallback, trust metadata, and immutable share/preview generation must pass. Then disable the legacy publication writer before enabling the new publication writer.

## 23. Scheduler Authority

Target: Render planners/workers are primary and GitHub is verifier/fallback. Current: legacy Render and GitHub schedules remain active. The duplicate three-minute services require deliberate consolidation only after the shadow job actually runs and the full-live stale/ambiguous failures are resolved.

## 24. Legacy Retirement Decisions

No legacy responsibility is retired. Publication/request reads are `DEFER_RETIREMENT`; other core paths are `RETAIN_AS_PRIMARY` pending natural shadow proof. Safe disable-before-delete is mandatory.

## 25. Rollback Plan

Set all new flags false, stop only new services, leave additive data intact, restore legacy flags true, verify legacy due-window schedulers and public snapshot identity, then use SP-13 for any interrupted bounded obligation. No downgrade or data deletion is necessary.

## 26. Remaining Deferred Risks

* No natural deployed SP-08 → SP-07 → SP-09 → SP-10 → SP-11 lineage.
* No atomic-publication consumer cutover; mixed-generation risk remains outside the new bundle reader.
* Shadow cron is configured but disabled by kill switch.
* Full-live cron currently returns partial/failure for stale/ambiguous observations.
* No production database visibility for SP-14 health queries through the connected Render workspace.
* No production medians/p95s, memory growth, or representative EXPLAIN evidence for the dormant pipeline.
* No natural roster/transaction mutation occurred in the bounded observation window.
* `npm audit --omit=dev` reports two moderate React Router advisories; npm offers only the breaking React Router 7 upgrade, so dependency certification remains unresolved rather than broadening SP-14 into an unreviewed major-version migration.

## 27. Final Certification Verdict

**NO-GO.** The code-level architecture is coherent and repeatable, but production authority cannot safely move while the atomic publication consumer is uncut, the shadow path is off, the active continuous path is failing partial cycles, and natural end-to-end IDs do not exist.

## 28. Main Merge Preconditions

1. Deploy the integration branch to a staging/shadow environment with the migration applied.
2. Run Stage 1 through a complete MLB pregame/live/final/overnight/morning cycle.
3. Resolve stale/ambiguous continuous observation failures.
4. Record exact source, run, job, version, impact, cohort, publication, and closure IDs.
5. Migrate backend readers to one atomic publication identity and pass race/read consistency tests.
6. Run the PostgreSQL/full CI suite at the exact final SHA.
7. Record production performance/resource/query baselines.
8. Re-run the certification command with reviewed evidence and obtain GO.

Until then, do not merge `feat/sync-pipeline` to `main` and do not disable a legacy writer.
