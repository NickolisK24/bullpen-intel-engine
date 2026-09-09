# SP-10 Derived Intelligence & Snapshot Cohort

## 1. Objective

SP-10 consumes one SP-09 `CanonicalImpactPlan`, executes only its requested domains and deterministic prerequisites, and records an immutable candidate cohort. The cohort is internal evidence. It does not publish, advance a current pointer, invalidate a cache, or alter a schedule.

## 2. Existing Intelligence Reused

The implementation converges on existing Continuous Updates work rather than adding new baseball calculators.

| Existing component | SP-10 disposition | Reason |
|---|---|---|
| `incremental_workload_rest.recompute_workload_rest_impact` (CU-04) | REUSE AS-IS | Bounded pitcher/team workload and rest projection with parity evidence; no publication side effects. |
| `incremental_arm_read_team_state.recompute_arm_reads_team_state` (CU-05) | REUSE AS-IS | Uses governed availability, active-bullpen, Arm Read, and Team State authorities without changing thresholds. |
| `incremental_read_model_rebuild.rebuild_read_model_impact` (CU-06) | REUSE AS-IS | Builds a copied shadow snapshot and explicitly does not publish, cache, or install serving authority. |
| `CanonicalImpactPlan` and `PROCESS_DERIVED_INTELLIGENCE` (SP-09) | EXTEND | They remain the sole scope and dispatch contract. |
| SP-05 roster intervals, SP-06 pregame versions, SP-07 final versions, SP-08 provisional states | REUSE AS-IS | They provide versioned authority watermarks. |
| Existing DashboardSnapshot/current publication models | DO NOT TOUCH | SP-11 owns candidate validation and pointer/cache handoff. |
| Legacy daily/postgame/CU derived writes | MIGRATE LATER | Preserved until SP-14 parity and production certification. |

The broad deployment, role, performance, rotation, concentration, snapshot, and What Changed shapes continue to come from the existing shadow Team Board/read-model package. SP-10 persists that result by cohort; it does not duplicate the underlying formulas.

## 3. Cohort Definition

`derived_intelligence_cohorts` is the durable execution envelope for one plan/input/method combination. Its lifecycle is:

`running -> complete | partial | stale | failed | superseded`

Identity is `SHA-256(impact plan fingerprint, authority, sorted input manifest, sorted execution domains, method versions, derived-cohort-v1)`. The fingerprint is unique. The same exact inputs reuse the same cohort; a source or method version change produces a different cohort.

The cohort stores requested and expanded domains, exact affected game/team/pitcher sets, status, correlation/run linkage, predecessor/supersession linkage, input manifest, method versions, and completion time. It contains no public/current flag.

## 4. Authority Model

The SP-09 authority class is preserved unchanged:

* `live`: provisional current evidence only; never an SP-11 publication candidate in v1.
* `final`: official SP-07 current final versions.
* `corrected_final`: corrected SP-07 current versions, producing a new cohort.
* `roster_authoritative`: SP-05 current membership intervals.
* `pregame_authoritative`: latest SP-06 official context version.

Final and corrected-final cohorts can reference the matching prior live cohort through `supersedes_cohort_id`. Live values are never added to final `GameLog` workload. The default live adapter reads only SP-08 provisional rows; the final adapter reuses CU-04 over the SP-07-maintained current `GameLog` compatibility projection while watermarking the exact SP-07 current versions.

## 5. Input Manifest / Watermark

`derived_cohort_inputs` and the cohort JSON manifest record compact references, not source payload copies:

| Authority/input | Watermark |
|---|---|
| final game | current `FinalGameVersion.id` and fact fingerprint |
| final appearance | current `FinalPitchingAppearanceVersion.id` and fact fingerprint |
| live appearance | current `ProvisionalPitchingAppearanceState.id`, fact fingerprint, latest observation |
| roster | current effective `RosterMembershipInterval` identity and opened observation |
| pregame | latest `GamePregameContextVersion.id`, fingerprint, and observation |
| source evidence | SP-09 source observation IDs |

SP-10 captures the manifest before compute and rebuilds it before completion. It does not use `updated_at` as authority identity.

## 6. Dependency Graph

The centralized graph in `services/derived_intelligence.py` is versioned by the cohort schema and maps only semantic prerequisites:

* `rest <- workload`
* `arm_read <- workload + rest`
* `concentration <- workload`
* `clean_options <- roster_composition + arm_read`
* `bullpen_churn <- roster_composition`
* `role_movement <- deployment`
* `team_state <- roster_composition + workload + rest + arm_read + concentration + clean_options`
* `pitcher_snapshot <- workload + rest + arm_read`
* `team_snapshot <- roster_composition + workload + rest + arm_read + team_state`
* `matchup_context <- game_context`
* `what_changed <- team_snapshot`

`read_models` does not force Team State for a pregame-only plan. Final and roster plans already request the team domains they need through SP-09.

## 7. Dependency Closure

Closure is deterministic, rejects unknown domains, deduplicates prerequisites, and records both `requested_domains_json` and `execution_domains_json`. It may expand within an affected team, but never discovers league scope independently. SP-09 remains scope authority.

## 8. Execution Order

The v1 order is:

1. roster composition / organizational depth
2. workload and provisional workload
3. rest
4. deployment
5. performance
6. rotation transfer
7. concentration and bullpen churn
8. Arm Read and clean options
9. Team State and role movement
10. pitcher snapshot
11. team snapshot
12. game context
13. matchup context
14. read models
15. What Changed

The adapter memoizes CU-04/CU-05/CU-06, so several requested domains do not repeat the same computation.

## 9. Workload / Rest

Final/corrected computation delegates to CU-04, which continues to use the governed fatigue and availability authorities and existing supported windows. SP-10 does not change formulas, date semantics, or thresholds. Corrected-final scope comes from SP-09, so one corrected pitcher expands only to the affected team dependencies.

Live `workload_current` and `team_workload_current` read SP-08 current provisional state IDs and retain pitches, outs, batters faced, and outing state. Those rows are never combined with final `GameLog` rows in one calculation.

## 10. Roster Composition / Churn

Roster-sensitive cohorts use SP-05 current versioned intervals effective on the cohort baseball date. Unknown/incomplete authority fails the domain rather than becoming an empty bullpen. Probable-starter context cannot open or close membership.

## 11. Deployment / Role

The candidate package reuses existing deployment and observed-role output. Historical role movement remains final-authority work. Live SP-09 plans do not request these domains, so an unfinished appearance cannot close a historical role shift.

## 12. Performance

Performance remains final/corrected-final only under SP-09 rules and retains current governed ERA/WHIP method versions (`1.1.0`/`1.0.0`). SP-10 does not finalize provisional live performance.

## 13. Rotation Transfer

Rotation transfer continues to use final actual starter and reliever facts, never SP-06 probable starters. Its recorded method version is `2026-06-18.phase2`. No starter-length prediction is introduced.

## 14. Concentration / Clean Options

Concentration depends on governed workload. Clean options depend on authoritative active membership and governed Arm Reads. No public ranking or new fatigue vocabulary is introduced.

## 15. Arm Read / Team State

CU-05 is the authority adapter. Existing public Arm Read vocabulary and Fresh/Stretched/Vulnerable semantics are unchanged. Team State is computed from one CU-04 result and one roster/date context inside the same cohort; dependent state is withheld if prerequisites fail.

## 16. Pitcher Snapshots

`derived_cohort_snapshots` stores one immutable `pitcher_intelligence` candidate per affected pitcher/cohort. Its payload is the union of only successfully executed domain outputs. It is authority- and baseball-date-labelled and cannot be a public pointer.

## 17. Team Snapshots

The analogous `team_intelligence` candidate contains the affected team’s successful workload, roster, Arm Read/Team State, and shadow package results. Unknown or failed domains are absent and listed in the cohort’s withheld domains; they are never serialized as zero.

## 18. Game / Matchup Context

Pregame cohorts reference the latest SP-06 context version and official starter identities. Final game context references the current SP-07 game version. Live game context references SP-08 provisional state IDs. Doubleheaders remain distinct because every game key is `gamePk`.

## 19. What Changed

The method manifest preserves `2026-06-19.v1`. Candidate change inputs are generated only after a coherent team snapshot. `predecessor_cohort_id` selects a completed/partial cohort with overlapping game/team/pitcher scope and the same authority class. No missing predecessor is interpreted as zero.

## 20. Method Version Manifest

Every execution domain has a backend-owned method/version entry. Existing explicit versions are reused where present; compatibility adapters have explicit v1 identifiers. Because versions participate in the fingerprint, SP-13 can intentionally replay the same plan with a later method manifest without overwriting the old cohort.

## 21. Live vs Final

Live cohorts are internal and provisional. Final/corrected-final cohorts select SP-07 current versions and may supersede a matching live cohort. SP-11 receives only complete non-live cohorts in v1. This prevents a late live job or unfinished-game record from becoming publication authority.

## 22. Input Drift

Before snapshots or an SP-11 handoff are committed, SP-10:

1. revalidates the SP-02 lease fence;
2. refreshes the impact plan status;
3. recaptures the complete input manifest;
4. compares it byte-for-byte with the starting manifest.

Drift or plan supersession marks the cohort and every domain `stale`, persists no candidate snapshots, and enqueues no publication job.

## 23. Failure Isolation

Each domain has `requested`, `prerequisite`, `succeeded`, `failed`, `withheld`, `skipped`, or `stale` evidence. A failed prerequisite withholds dependents. Independent successful domains survive in a `partial` cohort, but v1 sends only `complete` cohorts to SP-11. A cohort with no successful domains is `failed`. Missing information is never converted to zero.

## 24. Snapshot Atomicity

Candidate snapshots, domain outcomes, final watermark validation, cohort completion, and SP-11 enqueue occur in one database transaction. A crash before commit leaves no half-complete candidate. SP-02 lease fencing is checked between domains and before completion. A stale owner therefore cannot finish or dispatch after its lease is lost.

## 25. CU / Legacy Parity

SP-10 calls CU-04, CU-05, and CU-06 directly rather than reimplementing them. Their existing parity suites remain the semantic proof for workload/rest, Arm Read, Team State, and shadow read models. SP-10 tests prove exact SP-09 scope, dependency order, candidate atomicity, failure isolation, live/final separation, drift rejection, and dedupe. No intentional baseball-semantic difference exists.

Legacy writers remain enabled and unchanged. SP-14 must compare naturally produced cohorts to production outputs before retiring any path.

## 26. Queue Flow

Input is SP-09 `PROCESS_DERIVED_INTELLIGENCE` payload schema v1. The worker validates the plan/rules version, creates a child `INCREMENTAL_INTELLIGENCE` SyncRun, fences its lease throughout execution, and records affected scopes/outcomes.

An eligible cohort produces exactly one `PUBLISH_DERIVED_COHORT` job (payload v1, priority 70, dedupe key `PUBLISH_DERIVED_COHORT:{cohort_fingerprint}`). This is only an SP-11 handoff. No handler or publication behavior exists in SP-10.

## 27. Database / Index Design

The additive migration creates:

* `derived_intelligence_cohorts`: fingerprint, lifecycle, scope, manifest, method versions, lineage, and job/run linkage;
* `derived_intelligence_cohort_domains`: per-domain status and failure evidence;
* `derived_cohort_inputs`: queryable watermark entries;
* `derived_cohort_snapshots`: immutable cohort-bound pitcher/team/game candidates.

Indexes cover date/status, authority/status, correlation, domain failures, input lookup/observation, and entity/date snapshot history. JSON payloads are not indexed. No historical rows are guessed or backfilled.

## 28. Explicit Non-Goals

SP-10 does not publish, switch a current pointer, invalidate a cache/CDN, change schedules, change acquisition, recalibrate any baseball metric, backfill history, retire CU/legacy work, build a frontend surface, or start SP-11 execution.

## 29. SP-11 Handoff

SP-11 receives one complete non-live cohort with its fingerprint, impact plan, authority, baseball date, exact entity sets, completed/withheld domains, input manifest, method versions, and predecessor/supersession IDs. SP-11 must validate that evidence and publish atomically; it must not recompute baseball intelligence.

## 30. Acceptance Checklist

* [x] One durable, authority-aware cohort contract.
* [x] SP-09 plan is the only scope authority.
* [x] Deterministic dependency closure and execution order.
* [x] Existing CU baseball semantics reused without recalibration.
* [x] Final and live inputs remain separate; final supersedes live.
* [x] SP-05 roster and SP-06 pregame authority retained.
* [x] Cohort-bound candidate snapshots; no public pointer.
* [x] Input/method manifest and pre-completion drift check.
* [x] Dependency-aware failure isolation and unknown-not-zero behavior.
* [x] Fingerprint uniqueness, queue dedupe, and lease fencing.
* [x] Bounded team/pitcher/game scope; no automatic league rebuild.
* [x] Additive, downgrade-capable migration with no guessed backfill.
* [x] No frontend, scheduler, acquisition, or publication behavior change.
