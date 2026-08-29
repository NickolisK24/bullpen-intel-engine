# CU-05 Incremental Arm Reads & Team State

## Verdict

**PASS — CU-05 ACCEPTED**

CU-05 recomputes bounded current Arm Reads and Team State from the exact CU-04 workload/rest result, achieves exact parity with the existing production calculators, and stops before every public read-model, publication, cache, and scheduling seam.

## Repository state

- Branch: `feat/incremental-team-state`
- Starting main SHA: `b45e4bc0f94aa9158c23c88ba2c769a08af30008`
- `origin/main` at branch creation: `b45e4bc0f94aa9158c23c88ba2c769a08af30008`
- Main drift during implementation: NONE at the final pre-commit check
- Schema changes: NONE
- Alembic head: `c6d8e1f3a5b7`

The unrelated untracked `BASEBALLOS_DATA_ENGINEERING_INTERVIEW_AUDIT.md` remained untouched.

## Targeted semantic audit

### Authoritative Arm Read calculator

The production path is singular:

1. `services.availability.classify_availability` derives the governed availability result.
2. `services.pitcher_public_labels.build_public_arm_read` projects that result and roster authority into the canonical public Arm Read vocabulary.

CU-05 extracted no thresholds or labels. It added `classify_availability_inputs`, and the existing `classify_availability` now delegates to it after deriving the same workload/rest inputs. This gives CU-04's already-derived input contract a pure entrypoint through the same classification body.

Canonical labels remain exactly:

- Clean Option
- Watch Arm
- Limited Rest
- Unavailable
- Limited Read

### Authoritative Team State calculator

The production path is also singular:

1. `services.share_artifact_generation.resolve_team_readiness_payload` loads and classifies team records.
2. `api.team_operations.resolve_readiness_population` resolves the canonical current active bullpen.
3. `team_operations.assemble_bullpen_readiness` applies the locked Contract A Team State classifier.
4. `services.team_state_public_vocabulary.public_state_for` maps supported internal states to Fresh, Stretched, or Vulnerable.

No second Team State engine was found or created. Contract A thresholds, precedence, partition mapping, and public vocabulary were untouched.

### Team State evidence/input seam

CU-05 reuses the existing readiness payload and compares these deterministic outputs:

- represented membership and availability dates
- canonical active-bullpen membership IDs
- Arm Read records and evidence state
- availability distribution
- coverage inventory
- readiness status code
- complete `team_state_evidence`
- canonical public Team State projection

The production readiness resolver gained one bounded `classified_record_overrides` seam. It replaces only same-current-team records whose CU-04 workload/rest inputs changed; all population, trust, freshness, Arm Read, and Team State logic remains in the existing resolver.

## Date, membership, and unknown contracts

### Represented date/currentness

- CU-05 requires CU-04's explicit `data_through` and `availability_reference_date`.
- The resolver's shadow-only `represented_date_override` is converted through `trusted_slate_reference_dates`.
- Membership uses the represented slate date.
- Availability uses the represented slate plus one day.
- No CU-05 calculation uses `datetime.now()`, machine-local date, or request time as baseball authority.

### Active bullpen membership

`resolve_active_bullpen_membership` remains the production owner. It reuses Canonical Roster Authority plus Role Authority and fails closed when membership is unproven. `select_active_bullpen_records` remains the Team State population filter.

An affected historical team remains a requested bounded team input. If an affected pitcher currently belongs to a different canonical active bullpen, CU-05 may add that current team as a dependency, but only after the existing membership authority proves membership. It never rewrites historical appearance ownership or derives current membership from a GameLog alone.

### Off-active and unavailable

- Off-active, injured-list, starter, and other non-bullpen records remain outside the Team State population.
- Roster Authority can still project an off-active arm as Unavailable where that existing public contract applies.
- Historical workload remains descriptive and does not promote an off-active or position player into current bullpen membership.

### Limited Read and unknown

Missing, stale, incomplete, failed, historical, or unknown workload evidence remains fail-closed. It is not converted to zero, rested, available, or Clean Option. `build_public_arm_read` continues to project insufficient current evidence as Limited Read.

## CU-05 architecture

`services.incremental_arm_read_team_state.recompute_arm_reads_team_state` consumes:

- gamePk
- CU-04 represented dates
- CU-04 `pitchers_recomputed`
- CU-04 `teams_recomputed`
- CU-04 pitcher workload/rest results
- CU-04 completion and parity status

The chain is:

`CU-04 result -> bounded availability overrides -> canonical membership -> canonical Arm Reads -> canonical Team State -> parity -> STOP`

Hard no-action gate:

`CU-04 no action or untrusted parity -> zero CU-05 provider calls -> zero derived work`

The structured result includes requested/recomputed/skipped entity IDs, Arm Read results, Team State/evidence results, exact parity entries, failures, timings, and explicit false flags for read models, publication, cache invalidation, scheduling, and downstream recomputation.

## Recomputed and excluded domains

### Arm Reads recomputed

- availability status and evidence state
- roster-authority projection
- canonical public Arm Read key/label
- current active-bullpen eligibility

### Team State inputs recomputed

- current active-bullpen membership
- governed availability distribution
- coverage inventory
- Contract A partition/evidence
- internal readiness status
- Fresh/Stretched/Vulnerable projection where publishable

### Explicitly excluded

- Team Board
- League/Dashboard
- Matchup
- Tonight
- public Pitcher read models
- History
- What Changed
- snapshot or Share Artifact publication
- cache invalidation
- notifications
- scheduling, workers, polling, or daemon behavior

## Files changed

- `backend/services/availability.py`
- `backend/services/incremental_workload_rest.py`
- `backend/services/share_artifact_generation.py`
- `backend/services/incremental_arm_read_team_state.py`
- `backend/scripts/run_cu05_proof.py`
- `backend/tests/test_incremental_arm_read_team_state.py`
- `backend/tests/ci_shard_manifest.json`
- `docs/current/CU_05_INCREMENTAL_ARM_READS_TEAM_STATE.md`

The CU-04 result adds `fatigue_score` and `fatigue_risk_level` to its existing bounded rest-input carrier. This is additive and necessary to invoke the authoritative availability classifier without reconstructing its score or rereading the wall clock.

## Proof dataset and evidence boundary

The exact accepted 15-game CU proof dataset was reused.

- Canonical acquisition, reconciliation, affected entities, and CU-04 workload/rest: captured real-game evidence
- Current active-bullpen membership and higher-level Team State distribution in the historical 15-game harness: controlled real-shape overlay
- Reason for controlled membership: the historical capture does not contain reproducible current roster snapshots for those past dates
- Real production membership/resolver behavior: separately proven through persisted pitcher, roster snapshot, fatigue, GameLog, and readiness fixtures

The controlled evidence is not claimed as naturally observed historical current-roster truth.

## Strongest end-to-end proof

The focused chain test proves:

`CU-02 FINALIZED -> CU-03 authorized -> CU-01 canonical reconciliation -> CU-04 parity -> CU-05 Arm Reads/Team State parity -> STOP`

Observed controlled fixture:

- GameLogs inserted: 4
- Pitch events inserted: 4
- Affected pitchers: 2
- Affected teams: 2
- CU-04 parity: MATCH
- CU-05 Arm Reads: exactly the 2 mutation-scoped eligible pitchers
- CU-05 Team States: exactly the 2 bounded teams
- CU-05 parity: MATCH
- Public/read-model/cache work: 0

Exact observation replay produced CU-01 calls 0, CU-04 work 0, and CU-05 work 0.

## Parity matrices

### Arm Read parity

For each eligible affected pitcher, exact comparisons covered:

- pitcher and team identity
- canonical public read key/label/source
- availability evidence state
- roster-authority status and active flag

Result: **1,356 / 1,356 MATCH**.

### Team State parity

For each bounded team, exact comparisons covered:

- represented dates
- active member IDs and missing records
- readiness status
- public Team State
- availability distribution
- coverage inventory
- complete Contract A evidence and decisive inputs

Result: **1,650 / 1,650 MATCH**.

### Overall

- Comparable CU-05 fields: 3,006
- Matches: 3,006
- Mismatches: 0
- Parity: **100%**

The coupled CU-04 proof was rerun after adding its two required score-carrier fields:

- CU-04 fields: 3,212
- CU-04 mismatches: 0
- CU-04 parity: **100%**

## State coverage

Natural/captured higher-level state coverage is not claimed because current roster truth cannot be reconstructed from the historical capture.

Controlled authoritative-shape tests exercised all Arm Read labels:

- Clean Option
- Watch Arm
- Limited Rest
- Unavailable
- Limited Read

Controlled Contract A tests exercised all Team States:

- Fresh
- Stretched
- Vulnerable

The 15-game controlled membership overlay yielded 30 Vulnerable results because each per-game affected subset is intentionally thinner than a complete current bullpen. Those labels are parity evidence for the calculator, not claims about the historical clubs' natural Team States.

## Replay, restart, and correction

### No-op replay

Five accepted games replayed with:

- canonical mutations: 0
- CU-04 calls/work: 0
- CU-05 calls/work: 0
- affected derived entities: 0

### Direct determinism and restart

Repeated and post-session-restart calculations from identical canonical inputs produced identical Arm Reads, Team State/evidence results, and parity entries. No ephemeral state participates in correctness.

### Correction

A controlled authoritative correction changed an affected appearance from 18 to 52 pitches:

- CU-04 recomputed only the affected pitcher/team
- the pitcher Arm Read changed to Unavailable
- the bounded team's availability distribution changed
- Team State still matched broad authority
- unrelated entities were not recomputed
- no public state changed

Crossing a Team State boundary is not required for correctness; unchanged state with changed evidence is retained honestly.

## Ownership and special cases

### Historical/current team ownership

A controlled trade-shaped case kept the historical affected team as bounded input while projecting the current Arm Read only through the pitcher's proven current-team membership. Mutable current identity did not rewrite historical ownership.

### Position-player pitching

Three position players in the 15-game capture were excluded from current Arm Read membership. Their historical identities remained unchanged. The 15-game totals therefore contain 116 workload recomputations but 113 eligible Arm Read recomputations.

### Optional PBP

CU-05 consumes CU-04 core workload/rest facts and has no pitch-tracking dependency. A controlled failed-nonblocking PBP status still produced successful Arm Read and Team State parity once core GameLog workload existed.

### Failure scope

Arm Read or Team State provider failures return structured partial results. Missing dependent inputs cannot claim parity, and no fallback old state is presented as newly computed. The shadow path performs no public writes, so mixed public state is impossible.

## Safety sentinels

Before/after and call-graph tests proved zero mutation or invocation of:

- Dashboard/public snapshots
- historical snapshots
- Share Artifacts
- Team Board or other read models
- publication pointers
- What Changed
- cache invalidation
- Render or GitHub scheduling

The only CU-05 entrypoint outside tests is the explicit developer proof script. `AUTO_SYNC` is disabled before application imports.

## Efficiency

Across the 15-game proof:

- affected workload pitchers: 116
- eligible Arm Reads recomputed: 113
- Team States recomputed: 30
- Arm Read runtime: 50.490 ms
- Team State runtime: 15.922 ms
- broad pitcher-read work units: 2,070
- incremental Arm Read work units: 113 (**5.46%**)
- broad Team State work units: 315
- incremental Team State work units: 30 (**9.52%**)

No all-pitcher, all-team, league-sync, or daily-sync function is called by CU-05.

## Validation

- CU-05 focused: **22 passed**
- chain/availability/Arm Read/Team State/roster semantic selection: **338 passed**
- publication/scheduling/governance selection: **254 passed** after qualifying the inherited remote `DATABASE_URL` for the one environment-sensitive test
- appearance-team/freeze-policy selection: **128 passed, 1 skipped**
- additional readiness/roster/Team Board authority selection: **90 passed**
- exact 15-game CU-05 proof: PASS
- coupled exact 15-game CU-04 proof: PASS
- CI shard verification: **397 files / 9,057 tests, every test assigned exactly once**
- Python compilation: PASS
- migration head verification: PASS
- whitespace check: PASS
- full backend diagnostic: NOT RUN under the approved focused-suite policy

## Remaining known gaps

- Naturally observed historical current-roster Team State cannot be reproduced from the 15-game capture; current membership is proven separately with current-roster fixtures and the historical proof labels its overlay as controlled.
- Continuous roster-event propagation is not implemented. CU-05 reads existing current Roster Authority only.
- CU-05 remains dormant, shadow-only, non-authoritative, and non-publishing.
- CU-06 read-model rebuild and publication remain entirely unimplemented.

## Proven claims

- CU-05 consumes only trusted CU-04 bounded results.
- Exact no-op input performs zero CU-05 work.
- Arm Reads reuse the production classifier and vocabulary.
- Team State reuses the production population and Contract A calculator.
- Active membership, off-active, Limited Read, position-player, date, and ownership semantics remain intact.
- Comparable Arm Read and Team State/evidence fields achieve 100% parity.
- Corrections, replay, and restart are deterministic.
- No read model, public artifact, cache, schedule, or frontend behavior changes.

## Unproven claims

- CU-05 has not run against production data or production scheduling.
- No natural continuous roster-change handoff is claimed.
- No public read-model propagation or publication is claimed.
- The full backend suite was not run locally.

## Recommended integration action

Because `origin/main` did not advance and all bounded semantic, parity, authority, governance, and shard validations passed, use a direct safe push/PR/normal-merge task. Require hosted PostgreSQL migrations and all backend shards before merge. Do not add a separate heavy CU-05I phase unless main advances materially or hosted validation finds an interaction.

## Exact next slice after safe merge

Only after CU-05 is safely merged, CU-06 may address bounded Team Board, League, Matchup, and related read-model rebuilding under a separate authorization and publication-safety proof. CU-06 is not part of this branch.
