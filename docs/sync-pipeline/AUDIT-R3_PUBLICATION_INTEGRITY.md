# AUDIT-R3 — Publication Integrity Revalidation

Maintainer: Nikko. Date: 2026-09-11.

## 1. Original findings and provenance

Base: `feat/sync-pipeline@0ce6506ebcb0e08bd3ac51e483fcf92d52ff6616`.
Branch: `fix/audit-r3-integrity`. No implementation edits preceded recovery.

The original audit was recovered from the untracked
`docs/audits/BASEBALLOS_SYNC_PIPELINE_FULL_AUDIT_2026-09-11.md` in the original
worktree. Its register (lines 67–69), sections 16–24 and section 50 agree.
Audited SHA: `09823f6ce9c2d1cf3603a4f43fb0f2c3816085eb`.
Audit SHA-256: `0d81b556aa03e23ffae7500775fef4a1137ef758d3c30d88b4dde5b7f577445d`.
R1 identifies that uncommitted audit as its input. Repository docs, backend/root
reports, audit artifacts, remediation commits, and PR #831/#833 descriptions and
comments were also inspected. No alternative original definitions were found.
SP-14 blockers were not substituted for original findings.

### F03 — internal audit map

Original wording: **Cohort manifest does not cover the mutable inputs actually used to build frozen public payloads**

- Severity: P1. Subsystem: SP-10 manifest and public candidate builders.
- Claimed consequence: frozen artifacts can contain different input generations
  while manifest revalidation succeeds.
- Original evidence: six captured input families; baseline expansion beyond plan
  scope; cohort 484/pitcher 388 mixes September 5 persisted fatigue with September
  11 cohort workload. This was generation disagreement, not a proven arithmetic error.
- Current paths: `derived_intelligence.capture_input_manifest`,
  `public_pitcher_current.build_public_pitcher_current_payload`,
  `incremental_read_model_rebuild`.
- Authority boundary: versioned canonical inputs versus mutable legacy
  presentation inputs. Pitcher fields, persisted fatigue/history and other
  lookback inputs remain outside the captured manifest.
- Classification: **CONFIRMED** by current code and PostgreSQL reproduction.

### F04 — internal audit map

Original wording: **Reader coverage is conditional, incomplete, and does not require each affected game's reader contract**

- Severity: P1. Subsystem: SP-11 admission, candidate reports and reader coverage.
- Claimed consequence: an incomplete generation can replace the pointer; an
  unrelated inherited matchup can conceal a missing affected-game contract.
- Original evidence: cohort 489 eligible without v2/pitcher-current; cohort
  515/game 825036 has context fields but no `read_models.matchup`.
- Current paths: `publish_derived_cohort`, `_candidate_report`,
  `_validate_reader_artifact_coverage`, `publication_reader_coverage`,
  `_DefaultDomainExecutor._pregame`.
- Root cause: coverage depends on `cu06-publication-artifacts-v2`; reports only
  check generic specs; coverage accepts any one matchup. Completed domains do
  not establish complete public contracts.
- Classification: **CONFIRMED** by current code, PostgreSQL reproduction and
  retained production artifacts. R3-A fixes only the admission slice below.

### F05 — internal audit map

Original wording: **What Changed is frozen against legacy snapshot comparison, not consistently governed atomic predecessor semantics**

- Severity: P1. Subsystem: What Changed generation and inheritance.
- Claimed consequence: an inherited legacy comparison can appear under a newer
  atomic generation without a governed stable comparison-event contract.
- Original evidence: `build_what_changed_candidate` passes legacy snapshot pair
  identity; `predecessor_cohort_id` is metadata only.
- Current paths: the same candidate builder and
  `AtomicPublicationReadContext.what_changed`; `frozen_predecessor_context`
  remains the candidate label.
- Authority boundary: legacy comparison pair versus atomic publication predecessor.
- Classification: **CONFIRMED** by current code, deterministic call recording
  and retained production artifacts. Numerical delta correctness was not inferred.

Original production samples are historical, not current measurements. R1 fixes
roster source ownership and R2 fences semantic writes; neither closes actual
candidate inputs, publication coverage or comparison identity.

## 2. Combined versus split decision

**SPLIT REQUIRED.** Producer input closure, admission and comparison-event
semantics are distinct contracts. A combined redesign would obscure review.

1. **R3-A, this package: F04 admission safety.** Remove the method-marker bypass,
   require every affected game's matchup, and use the same admission logic in
   read-only candidate/baseline reporting and the locked pointer path.
2. **R3-B: F03 actual input closure.** Declare exact expanded canonical inputs
   and immutable presentation identities; prove deterministic generation.
3. **R3-C: remaining F04 contracts/populations.** Use R3-B's governed inputs for
   independent pitcher/slate denominators, typed artifact identities, complete
   full/core/details schemas, two-way/transfer/conflict cases and pregame contracts.
4. **R3-D: F05 comparison authority.** Choose actual atomic predecessor diffs or
   an explicit immutable comparison-event contract and test inherited identity.

R3-A is dependency-safe admission hardening, not full F04 resolution. F03/F05
and the remaining F04 work still block cutover.

## 3. Current reproduction

F03: a real PostgreSQL Pitcher row and the actual public-pitcher builder were
used. Changing roster status changed the emitted pitcher contract while
`capture_input_manifest(plan)` remained equal. The builder was not stubbed.
This proves an omitted dependency, not a bypass of R2's owner rules. The change
was solely in a disposable database; legitimate owner updates also need input closure.

F04: before service edits, five regression cases produced **4 failed, 1 passed**.
A missing marker published, an unrelated marker published, internal-only
inspection returned eligible, and a second affected game without a matchup
published. The existing special-marker rejection passed. The defect was
admission policy, not the atomicity of pointer assignment.

F05: the candidate builder received predecessor cohort IDs None, 99 and 102.
All selected the same normalized legacy comparison 100 → 101 and labeled it
`frozen_predecessor_context`. Only the downstream comparison function was a
call recorder. Identity normalization and candidate selection executed normally.
The two F03/F05 reproduction checks passed on PostgreSQL; they remain local
evidence rather than permanent tests requiring unresolved defects to persist.

## 4. Corrected R3-A invariant

Every new pointer admission requires existing reader-family coverage regardless
of method label or authority family. `validated_publication_artifacts` combines
candidate/predecessor references, rejects stale overlapping candidates and checks
coverage. The owner calls it after the existing pointer lock, then repeats
cohort/fence checks before mutation. Candidate and first-baseline reports use
the same routine. A point-in-time eligible report never authorizes a later write.

Every game named by the cohort or plan needs a selected matchup. An unrelated
inherited game cannot satisfy it. Historical reader coverage checks declared
affected games and exposes `missing_game_ids`; the required game count no longer
uses successful artifact count as its denominator. The existing nonempty
baseline-game requirement remains; full slate/off-day semantics are deferred.

Direct candidate snapshot loading is batched. Inherited evidence references
remain immutable; coverage checks reader families without deleting history.
Long inheritance-chain loading remains the separate F12 limitation.

No formula, public vocabulary, frontend, source acquisition, canonical owner,
flag, migration path or schema changes. Incomplete pregame output is rejected,
not converted into a guessed matchup. Null starter values remain null.

## 5. Implementation files

- `backend/services/atomic_publication.py`: shared unconditional admission,
  affected-game coverage, baseline report validation and batched direct reads.
- `backend/services/atomic_publication_cutover.py`: real admission in inspection.
- `backend/services/atomic_publication_reads.py`: historical affected-game check
  and missing-game diagnostics.
- `backend/tests/test_atomic_publication.py`: regressions and real-admission races.
- `backend/tests/test_atomic_publication_cutover.py`: complete typed artifact fixtures.
- This document, operator runbook and SP-14 gate addendum.

## 6. PostgreSQL and concurrency proof

Target: PostgreSQL 16, loopback port 55439, disposable `baseballos_r3_test`.
Repository test utilities enforce disposable targets. Production was never a test target.

- Combined regression run: **225 passed**, no skips, 156.25 seconds.
- R1 isolation, roster owner and health: **39 passed**.
- R2 shared-writer suite: **23 passed**, including separate-connection races and
  the retained game 823413 numerical single-counting reference.
- Migration authority: **77 passed**, including uncontrolled command-path checks.
- Certification: **16 passed**; shadow safety: **8 passed**; derived cohorts:
  **18 passed**. The transactional final/correction/publication/closure fixture
  passed with real reader admission.
- Final publication/read/full-chain rerun after batching/baseline-report changes:
  **46 passed**, no skips, 50.03 seconds. This overlaps the combined run; the
  counts are not summed as unique tests. The 93-artifact batching check observed
  exactly two direct snapshot SELECTs.

The new real-admission PostgreSQL race uses separate sessions publishing one
complete candidate. They converge on one successor without duplicate publication;
a request frozen on N retains N's Team Board/What Changed after N+1. Repeated
missing-game rejection preserves the predecessor pointer and publication count.
A deliberately seeded historical incomplete generation fails reader coverage
without rewriting the old artifact. A complete generation without a method
marker publishes and retries idempotently.

Older storage/cache unit fixtures intentionally contain internal-only payloads.
Their named `storage_app` fixture explicitly stubs reader admission, so they are
storage/fencing unit proof, not coverage proof. R3, reader-ready, controlled
cutover and full-chain tests use the real gate. Controlled cutover fixtures now
contain 93 proper reader/internal artifacts instead of the incomplete 32.

## 7. Natural retained production evidence

Read-only inspection: **2026-09-11 23:04:24 UTC**. Transaction read-only was
asserted, timeout 15 seconds, rollback and connection disposal enforced.

- Cohort 489 retains 4 generic pitcher, 30 generic team and 30 What Changed
  artifacts, no v2/current-pitcher. R1 corrected its upstream history; its old
  eligibility claim is not asserted current.
- Latest inspected pregame artifact **30888**, cohort **595**, game **823817**,
  contains context version 22 and probable starters 700/281 but no matchup.
  The shape defect persists beyond original cohort 515.
- Latest inspected What Changed artifact **30875**, cohort **591**, team 121,
  retains legacy snapshots **2604 → 2640**, predecessor cohort **590**, and
  `frozen_predecessor_context`. That is not an atomic predecessor pair.
- Original artifact 4158, cohort 484/pitcher 388, retains September 5 fatigue.
  This historical immutable sample is not a new production failure claim.
- Pointer **1**, including its update timestamp, was identical before/after.
  Latest cohorts 613–617 were live-only, not publishable authority.

No MLB event or production race was manufactured. No production owner, repair,
cohort, publication or startup function was invoked. Production configuration
was not changed or independently recertified by this package.

## 8. R1, R2 and migration interaction

R1 MLB-only ownership, scoped uniqueness, void corrections and affiliate
fail-closed semantics are unchanged. R2 locks, precedence, database guards and
worker claims are unchanged. Migration recovery remains closed; integration
still requires verify_only. No migration, owner command, startup, credential or
Render setting is touched. The supplied operational R1/R2 PASS decisions are
preserved; stale committed pre-deployment prose is not used to revoke them.

## 9. SP-14 and remaining limitations

Gate G remains blocked by F03. Gate H remains blocked by remaining F04/F05.
This correction is not SP-14 GO, CR-04 PASS, or authority activation.

Still required: actual expanded input closure; typed artifact identity and full
view schemas; independent pitcher populations and two-way/transfer/conflict
cases; slate/empty-slate semantics; pregame reader production; comparison identity.
Existing dictionary/presence checks can still accept malformed payloads or an
incomplete board population. R3-A explicitly does not solve that remainder.

Local tests and collection accounting are not hosted CI or natural post-deploy proof.

## 10. Rollback and deployment boundary

At the initial implementation checkpoint: no deployment, merge, production schema mutation,
publication or pointer movement. After review/hosted CI, adoption needs an
explicit integration deployment plan, verify_only, publication/read/closure
authority disabled and natural non-publishing recurrence. No migration is needed.

A later rollback must preserve evidence and legacy public authority. Do not
bypass validation with a method marker, edit publication history, downgrade,
stamp, edit version rows or change migration owners.

## 11. Evidence and verdict

Evidence directory: `C:/Users/nikko/AppData/Local/Temp/baseballos-audit-r3/`:
F03/F05 reproduction, production read-only script/result and JUnit receipts.
The original audit and unrelated R2 edits remain untouched in their worktree.

Final collection accounting: **10,025 node IDs across 447 files**, each assigned
exactly once, zero missing/extra/duplicate files or node IDs. Shard counts:
2,293 / 2,374 / 3,467 / 1,891. No manifest edit was needed because regressions
extend existing shard-owned files. `git diff --check` passed.

At the initial implementation checkpoint, HEAD remained the exact base SHA
and the change was uncommitted. No PR, hosted CI, push or merge had occurred.
Original workspace changes were preserved. The subsequent R3-A promotion is
separately gated on local revalidation, hosted CI and integration-only review.
No production authority activation is included.
**SPLIT REQUIRED** for F03/F04/F05. R3-A is the first admission-safety slice;
R3-B actual input closure follows the reviewed R3-A integration merge.
R3-B/C/D implementation and production authority activation are not part of R3-A.


## 12. R3-A promotion review — September 12

The exact eight-file change was reviewed against integration base
`0ce6506ebcb0e08bd3ac51e483fcf92d52ff6616`. No implementation changes were needed.
The final focused PostgreSQL rerun passed **227 tests**, no skips, in 157.00
seconds: R1 39, R2 23, migration authority 77, certification 16, shadow 8,
derived cohorts 18, and publication/read/full-chain 46. An initial attempt could
not connect because the existing disposable PostgreSQL container was stopped;
a second attempt reached its startup window. The successful run followed an
explicit readiness check. Neither attempt indicated an implementation failure.

Collection accounting again passed for 10,025 tests / 447 files with no missing
or duplicate assignments, and `git diff --check` passed. Hosted push/PR CI,
reviewed integration merge and post-merge CI remain separate required gates;
the PR and final promotion receipt record their exact SHAs and run IDs.
SP-14 G/H remain blocked; F03 is R3-B, remaining F04 is R3-C, and F05 is R3-D.

## 13. R3-B dependency investigation — 2026-09-12

**Status: BLOCKED / incomplete input closure. No R3-B implementation or new
manifest guarantee is established by this section.** R3-A is merged as PR #837.
This investigation starts on `fix/audit-r3-input-closure` at the required
integration commit `f6d493aacb95fd62ff064c14e810ab1d45186d20`. Existing worktrees
were preserved. The R3-B worktree was clean before this documentation and local
diagnostic work. No deployment, production write, configuration change, or
authority activation was performed.

F03 remains exactly:

> Cohort manifest does not cover the mutable inputs actually used to build frozen public payloads

The following is a source-grounded dependency inventory and a record of the
remaining closure work. It is **not** a claim that the complete recursive,
field-level inventory or the remediation PASS criteria have been satisfied.
In particular, calling a legacy helper a governed authority does not prove that
SP-10 captured its mutable inputs.

### 13.1 Actual execution graph

`execute_derived_intelligence_job` creates its run, validates the job payload and
rules version, and calls `execute_derived_intelligence_plan` with the existing
claim heartbeat fence. The plan executor expands `DOMAIN_DEPENDENCIES`, captures
`capture_input_manifest(plan)`, computes the fingerprint, checks deduplication,
and creates the cohort/input/domain rows. `_DefaultDomainExecutor` then selects
these paths:

| Execution path | Actual consumption and output |
| --- | --- |
| Live authority | `_live` reads every current provisional appearance in the affected games; returns pitcher facts, team pitch/outs totals, and game appearance IDs. It does not apply the manifest's optional pitcher filter. |
| Roster composition, organizational depth, bullpen churn | `_roster` calls `resolve_active_bullpen_membership`, which calls `api.bullpen.build_team_roster_authority`. This path consumes legacy pitcher/fatigue/role/roster-readiness evidence. It does not directly build its output from the intervals enumerated in the manifest. |
| Workload, rest, concentration | `_workload_result` calls CU-04 `recompute_workload_rest_impact`: affected-pitcher calculations plus team-at-appearance workload windows. |
| Arm Read, clean options, Team State | `_team_result` calls CU-05 `recompute_arm_reads_team_state`: CU-04 results, current Pitcher rows, unresolved workload failures, active population, current fatigue rows, readiness and ledger checks. Current pitcher teams can expand the input plan's team set. |
| Pregame authority's game/matchup/read-model domains | `_pregame` returns the latest `GamePregameContextVersion`'s ID, probable pitchers and scheduled time. This is the current narrow behavior; R3-B must not expand its reader contract into R3-C. |
| Other game context | `_final_context` reads the current `FinalGameVersion` for each affected game. |
| Remaining non-live domains | `_read_result` invokes CU-06 `rebuild_read_model_impact` after CU-04/05, regardless of whether the domain label is `read_models`, `performance`, `deployment`, or another fallback domain. The label alone does not describe its reads. |

CU-06 resolves a latest valid `DashboardSnapshot`, copies its payload, and
overlays CU-04/05 results. It builds team boards, league rows, one plan game from
`SlateGame`, matchup and Tonight material, pitcher-current payloads, and legacy
What Changed material. `_publication_baseline_required` checks the current
atomic publication's reader coverage; until complete, the build expands to the
official 30-club directory and pitchers found in the copied board packages.
That expansion is an actual input-scope dependency, not permission to force
league-wide inputs for every later bounded cohort.

`_merge_snapshots` accumulates domain outputs. The plan executor recaptures the
manifest after domain execution. If it differs, no snapshots are persisted and
the cohort is stale. Otherwise `_persist_snapshots` creates the generic
team/pitcher/game snapshots and specialized Team Board v2, pitcher-current, and
What Changed snapshots. A complete non-live cohort can enqueue a publication
candidate. SP-11 `validate_publication_cohort` compares the same manifest before
the R3-A artifact coverage checks. Neither comparison can detect an input that
the collector never included.

### 13.2 Traced input inventory

Category A means versioned evidence; B means mutable projection or mutable
selection; C means a calculation over other inputs; E means a required
dependency whose absence/partial state must remain explicit. No row below is
excluded as harmless presentation merely because it is metadata.

| Domain / category | Source and exact values identified | Reader / output affected | Current manifest coverage and required closure |
| --- | --- | --- | --- |
| Plan and execution context / B | Plan authority, date, ordered affected game list (CU-06 uses element zero), teams, pitchers, requested domains, method overrides; comparable predecessor selection and baseline decision | `derived_intelligence`; all scopes, emitted predecessor metadata and baseline artifacts | Plan fingerprint/method versions are included, but expanded build scope, selected predecessor and baseline decision are not recorded as captured inputs. Capture the effective context once. |
| Final authority / A | `FinalGameVersion` ID, fingerprint, boxscore observation, current selector, teams, scores, innings and extra-innings state | `_final_context`; final game payload | IDs are captured only for final/corrected-final plans. Context consumption in another authority path and historical workload dependencies are not closed by that conditional branch. Preserve old version identities, validate selected current version separately. |
| Final appearance authority / A | Current `FinalPitchingAppearanceVersion` IDs/fingerprints/source observations for the selected games/pitchers | Canonical lineage versus compatibility workload | Captured only in final-authority branch, limited by requested games/pitchers. CU-04/public workload actually reads `GameLog`, including other games. Version IDs do not by themselves identify those projection values. |
| Live state / B with retained observation | `ProvisionalPitchingAppearanceState` ID, game, pitcher, team-at-appearance, pitches, outs, BF, outing status, current flag, fingerprint and observation | `_live`; pitcher/team/game outputs | Manifest applies a pitcher filter that `_live` does not. Must identify the exact game appearance set and final-supersession state; no stale live substitution for Final. |
| Pregame / A plus mutable latest selection | `GamePregameContextVersion` ID, version number, probable pitcher IDs, scheduled time, source observation and fingerprint | `_pregame`; game/matchup-context candidates | Captured only for pregame-authoritative plans. Include wherever actually consumed, with explicit absent/partial handling. This is separate from `SlateGame`. |
| MLB intervals / A plus current interval projection | `RosterMembershipInterval` current-version/void flags, team/pitcher/type, effective dates, opening observation, closure and correction identity | Governed MLB membership and roster lineage | Collector includes selected date-effective intervals conditionally. It does not establish that the legacy public population used by `_roster` equals those intervals. Preserve R1 ownership and scope; do not treat affiliate evidence as MLB membership. |
| Pitcher current identity / B | All emitted `Pitcher.to_dict()` values: IDs, name, team identity, assignment status/source/assignment timestamp, position, throwing hand, age, jersey, active flag, roster status/source/raw code/raw description/status timestamp. Generic `created_at`/`updated_at` are not emitted by this serializer. | `public_pitcher_current`, public recent work, team identity, eligibility, transactions | Missing. Explicitly consumed status/assignment timestamps are payload facts, not universal source-order authorities. The F03 reproduction changes `roster_status`. |
| Workload and appearance projection / B | `GameLog.to_dict()` fields including IDs/date/type, opponent, start flag, outs/IP, pitches/strikes, runs/ER/hits/walks/K/HR, leverage and decisions; additional appearance-team resolution and game-shape fields used by team readers | CU-04, pitcher recent logs, availability, public relief/deployment, performance, game context, role and What Changed | Missing. Need consumer-specific fields and windows, not whole-table hashes. A Final ID alone is insufficient while these builders still read mutable compatibility rows. |
| Workload windows and anchors / B/C | CU-04: 14-day pitcher window through represented date, latest pitcher date bounded by represented date. Pitcher-current: unbounded latest pitcher date; recent logs from that anchor minus 14 days with no upper date bound; availability window through reference date. Team relief: official appearance-team rows in its window, plus unattributed current-roster rows. | Workload/rest, recent work, withholding and deployment | Missing. These are different selectors; a single affected-game watermark or a single generic 14-day query is not equivalent. |
| Fatigue projection / B | Latest `FatigueScore` by `calculated_at`, optionally bounded by source snapshot generation time; public workload facts; current/latest rows for other bullpen members; pitcher trend from anchor minus 30 days through cutoff | Pitcher-current, CU-05 readiness, Tonight optionality | Missing. CU-04 calculations are local values, but CU-05 and pitcher-current still consume persisted scores. Their identity must distinguish source projections from SP-10's computed outputs. |
| Failure/withholding evidence / B/E | Unresolved `SyncFailure` rows selected by workload entity type and pitcher MLB reference; roster fetch/identity/conflict failures and resolution state | `_classified_override`, `availability_snapshot`, public roster-readiness; trust and availability withholding | Missing. A resolved/unresolved transition can alter output without an appearance/roster version changing. Detailed downstream trust field selection remains to be finished. |
| Public roster-readiness / B/E | `RosterStatusSnapshot` latest date/source/run, covered teams; pitcher cache/status divergence; scoped unresolved roster failures; source freshness verdict | `build_public_roster_readiness` via `api.bullpen.build_team_roster_authority`; actual active-bullpen population | Missing. Must capture the actual resolver inputs as well as governed MLB interval truth; replacing its semantics is not authorized merely to simplify closure. |
| Published dashboard source / B selection, retained payload | `DashboardSnapshot` ID, type, status/publication state, payload version, sync provenance, data-through, availability-reference date, generation/publish time; selected team packages, records/default pitcher IDs, freshness, workload/rotation/rest carriers and method stamps | CU-06 copied source, team board/core/details/full, matchup, pitcher cutoffs, league/slate | Missing. Freeze one selected source and its semantic subtrees. Whole dashboard identity can be a necessary selected-source dependency; do not mistake it for an SP-10 output watermark. |
| Published Team State / B selection over artifacts | `ShareArtifact` snapshot/run/subject/team/type identity, publication lifecycle, public payload, version and sort order | Board fallback state, league listing, comparison sidecars | Missing. Artifact lifecycle affects selection even when payloads are immutable. CU-05 overrides do not cover all baseline teams. |
| Scheduled game / B | `ScheduledGame` game/team/date, status, game type, doubleheader/game number, start-time and opponent context; final slate and lookback/lookahead sets | Team relief game numbers, season performance finality, schedule context, ledger completeness | Missing. Must identify actual consumed team/game windows and finality selectors; unrelated schedule fields must not be included without a consumer. |
| Slate game / B | `SlateGame` selected by first affected game PK; serialized game/teams/date/status/probable-starter and venue/time context | CU-06 matchup and Tonight game material | Missing. Pregame source version identity does not close a separately mutable slate projection. |
| Season starter history / B/E | Same-season `GameLog` start/relief history through credited starter's target game; `PitcherSeasonLedgerCoverage` pitcher/MLB IDs, season/type/target, coverage state/date, source/stored counts and fingerprints, reason codes; recomputed current stored manifest | `starter_assignment_context`, `history_coverage_for_game_log`; relief game context | Missing. A recent workload window alone cannot close this same-season historical dependency. |
| Performance / B/C/E | Selected active group and eligible pitcher IDs; season appearance metrics and start/team identity; schedule final/non-final/contradictory classification for qualifying game PKs | `performance_intelligence.qualifying_appearances` and public team performance | Missing. Source season schedule loader currently reads league rows, but unrelated rows must be distinguished from schedule classifications actually affecting selected appearances. No baseball formula change is proposed. |
| League identity / B | Active Pitcher team IDs, name and abbreviation; ordered first non-null identity per team; official club constants | League row identity and included-team rendering | Missing. The official MLB directory remains the club authority; compatibility display identity is a separate consumed projection. |
| Tonight comparative context / B/C | Team and league trailing GameLog windows; league latest fatigue/current availability records; pitcher role/roster state, workload failures, usage logs; team injury/role/concentration context | `build_team_bullpen_context`, league rotation/clean-options baselines, Tonight cards/game sides | Missing. Some out-of-team mutations are relevant because the current output really uses a league comparator. Do not label them irrelevant without tracing the comparator. |
| Tonight rotation sidecar / B selection | Independently latest trusted DashboardSnapshot and frozen rotation carrier | `_default_tonight_builder` supplies workload/rest resolvers but no rotation resolver; `serve_tonight` falls through to default rotation listing | Missing and not pinned to CU-06's source snapshot. This is a concrete potential mixed-generation input path, not a new R3-C denominator requirement. |
| Transaction evidence / B/E | Latest `PlayerTransactionSyncWindow` status/query dates; selected from/to-team transaction rows and key/date/type/description/category/identity/qualification/rehab evidence; referenced pitcher name/position/identity | `build_public_recent_transactions`; board details/full, explicit partial and withheld-event count | Missing. A complete-empty window and a missing window must be distinct. Final field-by-field qualification tracing remains necessary. |
| Legacy What Changed inputs / B selection over retained history | Team latest/previous game dates and eligible pitchers; appearance changes; comparison DashboardSnapshot sidecars, represented dates, payload contracts/source identity, active ShareArtifact IDs, underlying frozen-rest source snapshots, selected comparable endpoints; emitted predecessor cohort ID | `build_what_changed_candidate` → `build_team_changes_payload` → `resolve_latest_team_state_comparison` | Missing. Manifest actual selected legacy comparison and selection evidence without changing to atomic predecessor authority. The current resolver scans historical sidecars; hashing all history would not be a justified substitute for semantic selection closure. |
| Runtime trust and clock / B/E | Global latest workload/game/fatigue metadata; public SyncRun status/stage and freshness; ledger schedule/appearance/processed-game evidence; product date fallbacks; role-authority and freshness/ledger configuration | CU-05 readiness, optional fallback paths, freshness/withholding | Missing. Exact consumed semantic projections and configuration/date capture require further tracing; do not hash every SyncRun or source-readiness table. |
| Computed values / C | CU-04 workload result, CU-05 Arm Read/Team State result, copied/overlaid dashboard, board serializers, performance/role/deployment calculations | All candidate families | May be excluded as duplicate input identities only after their entire prerequisite set is closed and the same captured values are consumed. That prerequisite is not yet satisfied. |
| Optional failures / E | `_optional` exceptions and pitcher recent-work/deployment exceptions become unavailable sections; multiple legacy helpers roll back sessions on database errors | Frozen trust/withholding and candidate status | Successful-row digests alone cannot prove equivalence between successful and exception-degraded builds. Required capture must represent unavailability or fail the cohort; swallowing an error must not manufacture complete closure. |

### 13.3 Concrete missing-boundary consequences

1. The observed Pitcher mutation is not a hypothetical future enrichment: its
   exact value is emitted today by the shared public-pitcher serializer.
2. The live collector and live executor do not necessarily cover the same
   pitcher set. This requires a scope regression, not a broader reader schema.
3. The current manifest filters depend on plan authority/domain labels; the
   actual non-live fallback builder can read much more than those labels imply.
4. Capturing only Final V1/V2 for the trigger game misses historical GameLog
   corrections used by workload, season performance and credited-starter context.
5. A pointer/reader-completeness change can alter baseline expansion. Separate
   legacy snapshot resolutions can alter payload inputs during a build.
6. Roster interval closure alone cannot prove closure over legacy compatibility
   roster fields, role evidence and source-readiness withholding.
7. Merely comparing the same incomplete manifest twice is insufficient. Even a
   completed pre/post manifest design must handle ORM identity-map freshness,
   source changes during generation, A→B→A changes, and late changes between
   validation and semantic commit. No new PostgreSQL isolation/race proof is
   claimed here.

### 13.4 Closure design constraints retained for implementation

The next implementation must capture effective execution scope and one shared
input context before generating payloads. Use immutable versions for governed
Final/pregame/roster source truth, explicit references and selected semantic
payloads for legacy snapshots/artifacts, and bounded semantic projections for
the compatibility rows actually consumed. Store exact domain identities with
stable canonical serialization, not generic update timestamps. Required
missing/partial/conflicting inputs need an explicit status.

Persist a new manifest schema only once its guarantees are implemented. Keep
old `derived-cohort-v1` manifests readable as incomplete historical evidence;
do not rewrite them or infer identities they never recorded. Revalidation must
check the same captured selectors and expanded scope, and publication admission
must reject obsolete/incomplete closure. R3-A's shared admission routine must
remain the only admission path for baseline/candidate reporting.

No implementation is included here because the complete field-level closure,
especially readiness/qualification/fallback inputs and consistent snapshot
consumption, has not been proven. Adding the obvious Pitcher hash would leave
the other demonstrated dependencies unclosed. Hashing broad tables or hashing
the final derived payload would not satisfy the requested invariant.

### 13.5 Validation and remaining proof

The original local PostgreSQL reproduction was rerun on the required merge SHA:
`Pitcher(id=10, mlb_id=100001, team_id=110).roster_status` changes from NULL to
`injured_list`; `build_public_pitcher_current_payload(...).pitcher.roster_status`
changes while `capture_input_manifest(plan)` remains unchanged. The retained
F05 probe also reruns unchanged; it is not an R3-D implementation.

R3-A publication/read/full-chain baseline: **46 passed in 39.57 seconds** on
PostgreSQL. Shard accounting: **447 files, 10,025 node IDs, zero missing/extra
files or duplicate assignments**. Initial attempts to collect the external
cross-drive reproduction hit a Windows pytest collection PermissionError; a
local diagnostic copy ran successfully. This was a test invocation issue,
not a source-code failure.

The preservation run passed **191 tests in 106.25 seconds**: SP-09 impact 10,
SP-10 derived 18, R1 39, R2 23, migration authority 77, certification 16, and
shadow 8. Together with the 46 publication/read/full-chain tests, that is 237
baseline tests. A separate final diagnostic run passed three probes in 3.53
seconds: the original F03 and F05 checks plus persisted-cohort F03 evidence.

The persisted probe used the real plan executor and snapshot persistence with
an injected domain executor calling the real public-pitcher builder. Equivalent
requested scopes produced local cohorts 2 and 4, both marked complete, with
identical empty input manifests (`[]`) and different frozen
`pitcher_snapshot.pitcher.roster_status` values (NULL versus `injured_list`).
Separate plan fingerprints permit both builds; this does not claim equal
overall cohort fingerprints. The first manifest and artifact stayed unchanged.
This isolates the missing input identity, but is not a full default CU-04/05/06
build or a corrected-path proof.

For that sparse diagnostic only, ten old-manifest captures executed 21 SQL
statements total (including an initial expired-plan reload), averaged 1.424 ms,
and serialized to two bytes. These measurements describe the inadequate old
empty manifest, not representative cohort performance. Reproduction source
and JUnit receipts are retained locally under
`C:/Users/nikko/AppData/Local/Temp/baseballos-audit-r3/` as
`r3b_revalidation_probe.py`, `r3b-base-proof.xml`,
`r3b-invariant-baseline.xml`, and `r3b-persisted-proof.xml`.

No corrected-path, drift/rebuild, new corrected-Final/roster/pregame/workload
closure, mixed-generation, new-manifest determinism, or drifted-publication
admission proof exists yet. Existing passing suites do not establish those new
guarantees. No representative before/after closure performance result exists;
an empty/sparse manifest fixture cannot certify operational query bounds.

**Verdict: BLOCKED. F03 remains confirmed and unfixed.** No commit or PR is
authorized by the local-PASS condition yet. SP-14 Gates G/H stay blocked. Next
work remains completion of R3-B, followed by R3-C's remaining reader contracts
and R3-D's comparison authority. Neither later package has begun. Rollback is
not needed: no runtime code, schema, flags, or production state changed.

## 14. R3-B continuation — captured source selection, incomplete closure

**Status: BLOCKED. F03 is still confirmed and unfixed.** Section 13 and its
original diagnostic receipts are retained without revision. This continuation
adds uncommitted source-selection code and tests; it does not supersede that
investigation with a closed-input claim. The branch and HEAD remain
`fix/audit-r3-input-closure` at
`f6d493aacb95fd62ff064c14e810ab1d45186d20`.

### 14.1 Build-time authority contract

The intended complete protocol is capture, build from the captured generation,
revalidate mutable selectors, then persist semantic completion. The following
table converts the 26 categories in section 13.2 into capture responsibilities.
It is a design inventory, not a claim that all collectors or consumers exist.
In particular, a captured derived result is not a substitute for identifying
the source facts on which that result depends.

| Domain | Current selection point / consumers | Required semantic identity and capture point | Implementation state |
| --- | --- | --- | --- |
| Plan/execution | SP-10 fingerprint, predecessor selection, first affected game, baseline decision | Capture requested scope, represented date, ordered games, method/config versions, effective scope, predecessor and baseline eligibility evidence before the first domain | Requested scope, date, games, predecessor and baseline boolean captured for CU-06; effective scope evidence and full method/config identity remain open |
| Final game | `_final_context` selects current Final | Current immutable version ID/fingerprint/source plus explicit missing/finality state, captured for every consuming path | Existing conditional manifest only |
| Final appearance | Conditional SP-10 selector versus historical workload readers | Exact consumed appearance versions, not only the trigger game's versions; capture current selector evidence separately from immutable content | Open |
| Live appearance | `_live` selects all current game appearances | Exact game appearance population, semantic facts, observation and Final supersession state; capture before live domains | Existing collector/executor scope discrepancy remains open |
| Pregame version | `_pregame` independently selects latest version | Selected version and completeness per game, with absent/conflicting state; capture once | Existing conditional manifest only |
| MLB membership | SP-05 interval selector versus legacy roster population | Governed MLB membership/version/observation and effective-date set; separate compatibility population identity | Open; R1 ownership is unchanged |
| Pitcher projection | CU-04/05, public pitcher, role, eligibility, identity readers | Scoped consumed `Pitcher.to_dict()` fields plus eligibility/selection fields; capture selected members and selection evidence before classification | Open; the roster-status reproduction still applies |
| Appearance projection | CU-04, public workload, performance, deployment, game context | Consumer-specific GameLog values and appearance-team authority, bounded by each actual history window | Open |
| Workload windows/anchors | CU-04 bounded anchor versus public pitcher unbounded latest anchor | Explicit windows, selected anchor and absence state; the selected rows must be reused by consumers | Open; one generic recent-history window is insufficient |
| Fatigue | `latest_fatigue_rows`, public pitcher cutoff/trend, Tonight comparators | Exact selected scores and consumed workload facts, selection cutoff and trend window; capture population and latest-row selectors | Open; row IDs alone cannot identify mutable facts |
| Failures/withholding | Availability and roster unresolved-failure queries | Applicable failure identity, resolution state and consumed reason/status, bounded by domain/entity | Open; no global failure-log hash |
| Roster readiness | `build_public_roster_readiness` and legacy roster authority | Selected roster-status evidence, population/cache mismatch, source freshness and applicable failure verdict inputs | Open |
| Dashboard source | CU-06 latest valid dashboard | Selected source metadata and copied payload, including a captured missing-source result | Captured once and reused in CU-06; not yet persisted as a manifest input or revalidated at cohort completion |
| Published Team State | ShareArtifact current/lifecycle selection | Selected immutable payload identities plus lifecycle/selection evidence and explicit absence per effective team | Open |
| Scheduled game | Relief, season finality, schedule/ledger readers | Consumed game/date/team/status and schedule-shape facts within actual team/windows or referenced game PKs | Open; unrelated schedule rows cannot become blanket dependencies |
| Slate game | CU-06 selects `SlateGame` during generation | Selected game's consumed serialized facts, missing state and source identity, captured before generation | Open; the pinned dashboard does not pin this row |
| Starter history | Ledger coverage and season GameLog readers | Selected credited-starter history, coverage record and source/stored semantic fingerprints for the actual target | Open |
| Performance | Active eligible population, season appearances, schedule classification | Closed eligible set, appearance values and finality classifications actually used | Open; unchanged baseball formulas |
| League identity | Active Pitcher display-identity selection | Official club directory plus deterministic first applicable display identity for consumed league rows | Open |
| Tonight comparator | League workload/fatigue, roles, failures and team context | Explicit comparator population/window and exact semantic contributions, separately from requested teams | Open; some other-team changes are genuinely relevant |
| Rotation sidecar | Previously default independent latest resolver in `serve_tonight` | The same selected dashboard reference as CU-06 workload/rest | Resolver is now explicitly pinned to the supplied CU-06 snapshot |
| Transactions | Latest sync window, qualified from/to-team events, referenced players | Selected window/completeness plus exact qualified event evidence and identity fields, captured before board generation | Open |
| Legacy What Changed | Active sidecar selection and nearest compatible comparison | Capture selected current/predecessor sidecar, artifact lifecycle and underlying rest-source identities; retain existing comparison rules | Only emitted cohort predecessor selection is pinned; actual legacy comparator input remains open |
| Runtime/trust/date | `_sync_status_payload`, freshness, role/config and product date fallbacks | Explicit semantic reference dates/config plus actual consumed readiness metadata, with unavailable state | Open; no wall-clock or generic update-time identity substituted |
| Computed values | CU-04/05 results and downstream serializers | Excludable only after their source prerequisites are closed and captured consumption is proven | Not yet excludable on that basis |
| Optional failures | Exception-to-unavailable paths and legacy session rollbacks | Explicit captured unavailable outcome or cohort failure; transaction rollback must not permit a new mixed generation | Open |

For the legacy roster boundary the necessary strategy is to capture **both**
governed MLB membership identity and the independently consumed compatibility
population/projection. Merely manifesting intervals cannot cover roster status,
role eligibility or current compatibility team fields. This strategy has not
yet been implemented. No affiliate source has been granted MLB authority.

The same separation is necessary for workload: current GameLog and FatigueScore
consumption is not automatically reproducible from the Final versions presently
listed by the manifest. Readiness also requires its actual source/withholding
inputs. Passing a dashboard into `resolve_team_readiness_payload` merely to pin
it would change that resolver's freshness-authority choice; this continuation
does not make that unreviewed semantic substitution.

### 14.2 Implemented source-selection boundary

`CohortBuildContext` is currently an immutable **in-memory selection object**,
not the final complete build context or a v2 manifest. It captures represented
date, requested teams/pitchers, ordered games, the baseline decision, cohort
predecessor ID, and one copied dashboard source. Canonical JSON protects the
copy from ORM mutation and downstream overlay mutation. Each consumer receives
a private copy; a captured missing source stays missing.

The default SP-10 executor captures this selection before its first domain when
the plan uses CU-06. The cohort predecessor already selected by the plan executor
is passed into the domain executor, rather than queried again for candidate
generation. CU-06 rejects competing explicit source/context arguments and a
represented-date mismatch. Its Tonight call now supplies rotation, workload
and rest builders with the same snapshot resolver.

This does not pin all rows read by CU-04, CU-05, CU-06 or their helpers. Nor does
it prevent the separate legacy What Changed resolver from visiting mutable
current sidecars. `matches_source` is a local comparison utility used by the
tests; it is **not wired into cohort completion or publication admission**.
No capture/revalidate transaction guarantee follows from its existence.

The intended effective scope still must distinguish requested teams from the
30-club baseline and league comparator populations. The baseline boolean and
source packages are fixed in the current object, but a full effective-scope
manifest and per-domain selectors are not implemented. Copying the existing
dashboard payload in memory is not a proposal to store that payload again in
every cohort manifest.

### 14.3 Proof boundaries and remaining blockers

New checks cover canonical capture/private-copy behavior, missing-source
failure without latest fallback, contradictory source/date rejection, reuse
before the first domain, and shared Tonight sidecar selection. A PostgreSQL
test uses a second connection to insert S2 after S1 capture: injected CU-06
team, league, matchup and Tonight builders all observe S1; a new context uses
S2. This uses local candidate snapshot rows and injected builders. It does not
certify production trusted-source selection, default public artifact content,
or a fully closed persisted cohort. No production race was manufactured.

The required roster/workload/readiness races remain unproven. The original
Pitcher roster-status and persisted equivalent-scope reproduction remain valid:
neither the manifest collector nor that mutable population has been repaired.
No corrected-Final, roster-change, workload, pregame-row, irrelevant-scope,
new-manifest immutability or drifted-publication proof is established by snapshot
pinning. Object immutability and JSON determinism are narrower than those claims.

`derived-cohort-v1` and its historical manifests are unchanged. Old rows are
not rewritten or relabeled as closed. The required new-manifest classification
and rejection of old insufficient manifests at new closure certification are
**not implemented**. Publication admission still has the old input-coverage gap;
the R3-A checks themselves are preserved. No pointer is moved by these changes.

Representative capture/build SQL counts, full context size, scope scaling and
before/after complete-cohort timings cannot yet be reported for a closure that
does not exist. The sparse two-byte diagnostic in section 13 remains historical,
not a performance claim for this implementation.

R3-B remains BLOCKED and uncommitted. Completing captured current-row readers,
semantic input identities, effective scope, transaction/revalidation behavior,
legacy-manifest admission, and the full mutation/race matrix is still required
within R3-B. SP-14 Gates G/H and activation stage remain unchanged. R3-C reader
population/schema work and R3-D comparison-authority work remain deferred.
No deployment, Render change, migration authority change, main change, public
activation or legacy retirement occurred. No commit or PR is made under the
user's local-PASS requirement.

### 14.4 Continuation validation receipts

The final PostgreSQL preservation run passed **268 tests in 170.85 seconds**:

| Suite | Passed |
| --- | ---: |
| SP-09 canonical impact | 10 |
| SP-10 derived cohorts | 19 |
| CU-06 read-model rebuild | 20 |
| R1 roster isolation, transactions and health | 39 |
| R2 shared writer fencing | 23 |
| Migration authority | 77 |
| Atomic publication, cutover, reads and route boundary | 45 |
| SP-14 certification | 16 |
| Full chain | 1 |
| Shadow operation | 8 |
| Repair orchestration | 10 |

Seven new tests are included in these counts. They establish the limited
selection guarantees in section 14.3, not the complete R3-B race/mutation matrix.
The retained diagnostic source then passed **3 probes in 3.59 seconds**, including
both still-reproducing F03 cases and the unchanged F05 diagnostic. Passing those
diagnostic assertions proves the defects remain; it is not corrected-path proof.

Shard accounting passed with **447 files, 10,032 node IDs, no missing/extra
assignments and no duplicates**. Existing file assignments cover the added tests.
`git diff --check` passed. Windows line-ending normalization warnings are not
whitespace-check failures.

New local receipts beside the preserved section 13 receipts:
`r3b-context-baseline.xml`, `r3b-context-proof.xml`,
`r3b-context-regressions.xml`, and `r3b-context-retained-probes.xml` under
`C:/Users/nikko/AppData/Local/Temp/baseballos-audit-r3/`.
The intermediate 32-test and 39-test runs overlap the final 268-test run and
are not additional independent test counts. No hosted CI, commit, push, PR,
merge or deployment was performed.

The uncommitted runtime changes are confined to `cohort_build_context.py`,
`derived_intelligence.py`, and `incremental_read_model_rebuild.py`; regression
changes are in the existing two corresponding test files. This document retains
the original section 13 and appends this continuation. No other repository file
was intentionally changed. Any decision to remove the new runtime experiment
must preserve the earlier audit notes and retained reproductions; no production
rollback or schema operation is required.

## 15. R3-B1 — Captured Cohort Build Context

**B1 status: BLOCKED / partial implementation. F03 remains confirmed and
unfixed.** The broad remediation is now explicitly split into B1 captured
context, B2 roster/workload content, B3 pregame/readiness/effective scope, and
B4 complete closure certification. R3-C reader contracts and R3-D comparison
authority follow those slices. This split does not excuse an uncaptured mutable
selector in B1 merely because its selected row's fields belong to B2 or B3.
Sections 13 and 14 remain the record of the prior investigations.

### 15.1 Lifecycle implemented for the default executor

Before computing a default-executor cohort fingerprint or creating its rows,
SP-10 captures a `CohortBuildContext`. The immutable object contains value JSON,
IDs and tuples, not ORM objects. Its explicit `cohort-build-context-v1` receipt
separates scope, selectors and semantic generation fingerprints. Validation
state remains in the existing cohort/domain statuses rather than mutating the
captured object. There is no process-global, request-global or thread-local
context override.

The receipt is appended as a `build_context` input in `input_manifest_json`.
Its fingerprint is also indexed in `DerivedCohortInput`; the structured context
stays in the manifest and raw copied dashboard/comparison payloads stay in
memory. It is not named or treated as complete input closure. Existing manifest
and cohort schema versions are not rewritten.

The same context instance reaches the default domain executor and CU-06. CU-06
uses private dashboard copies and captured comparison resolvers. The legacy
comparison algorithm is still `resolve_latest_team_state_comparison`; its
selected result is captured, including current/previous delta snapshot IDs and
a semantic fingerprint. What Changed receives that result without selecting
another current comparison. Unknown/missing comparison outcomes are retained.
This does not change to atomic predecessor authority or implement F05.

Before semantic completion, existing lease fencing runs, pending domain evidence
is flushed, and the ORM cache is expired before input/selector revalidation.
`cohort_inputs_are_current` compares the recorded receipt with a new capture.
Drift takes the existing stale path, records `CohortInputDrift` on domains,
does not persist final candidate snapshots, and does not enqueue publication.
The stale cohort/input/domain history remains. A changed selector identity can
create a distinct retry cohort. No historical context is refreshed in place.

Current attempts are checked for reuse before predecessor reselection. During
revalidation the attempt itself is excluded from the comparable-predecessor
query; older attempts retain the existing comparability rules. This avoids a
completed cohort treating itself as a new predecessor and generating work on
every identical retry. It does not substitute a new comparison authority.

SP-11 admission and cutover revalidation reports now use the same manifest
recapture function, including recorded context when present. Legacy manifests
without a context keep their existing historical contract. No B4 rejection or
new certification guarantee is applied to them. The custom diagnostic executor
path still creates the previous manifest form; that path has not been integrated
into one universal context protocol.

### 15.2 Selector inventory and remaining B1 work

| Selector | Current B1 handling | Remaining proof/work |
| --- | --- | --- |
| Trusted dashboard | Capture once; copy-safe source; ID and semantic digest persisted; revalidate before completion | Trusted-provider production proof remains; late commit-window failure reproduced locally |
| Rotation/workload/rest sidecars | All CU-06 sidecars receive the same dashboard resolver | Existing supplied-source proof passes; not separate readiness/fatigue closure |
| Publication baseline | Capture current publication ID and coverage-derived baseline boolean | Completion drift/retry tested with separate PostgreSQL pointer writer |
| Cohort predecessor | Capture once; reuse in cohort and emitted candidate metadata; revalidate excluding only self | Separate writer advancement and no-op/retry tested |
| Legacy comparison | Capture selected legacy comparison result per requested/baseline team and pass explicitly | Consumer no-reselection test added; realistic persisted sidecar advancement race remains |
| Additional teams reached during CU-05 | A missing captured comparison raises rather than selecting a newer value | Full effective scope belongs to B3; B1 cannot silently resolve an uncaptured selector |
| Current Final/pregame/live selectors | Existing conditional canonical manifest checks still run | Not all actual consuming paths are pinned through the new context |
| Latest fatigue/current workload rows | Independent selector calls remain | Row selection needs B1 integration; field-level content closure stays B2 |
| Latest roster-status/readiness evidence | Independent selector calls remain | Selector integration remains B1; content/failure closure stays B2/B3 |
| Latest transaction window | Independent selection remains | Capture selected window identity without changing event semantics |
| Current published Team State/share-artifact selection | Some legacy listing/fallback helpers still select independently | Capture/reuse actual selected artifact identities |
| Latest sync metadata and product-date fallbacks | Not universally passed through context | Capture/reuse semantic selector outcomes; do not substitute arbitrary clock noise |

Consequently this is **not** the required guarantee that every selector used in
a complete cohort is captured and checked. A selector commit after the final
revalidation query but before semantic commit can still produce a complete
cohort with an obsolete captured selector, as reproduced below. These are
B1 blockers, not grounds for declaring B1 PASS while deferring them as content.

### 15.3 Local proof boundaries

PostgreSQL lifecycle tests replace only payload computation and the trusted
snapshot provider to isolate lifecycle behavior from B2 content. They persist
real cohort/input/domain/snapshot rows. Separate connections advance dashboard,
publication baseline, and comparable predecessor selections. The old attempt
becomes stale; a retry completes on the new receipt; old manifest evidence is
unchanged. The unchanged-selector case completes and reuses the same attempt.

A separate two-worker test captures S1, commits S2 on another connection, lets
worker B complete using S2, then resumes worker A. B completes and A becomes
stale. The test uses local unpublished dashboard fixtures and does not claim
natural production evidence or full default public-payload generation.

Existing private-copy/canonical-order tests still apply. A new What Changed
consumer test makes any independent latest-comparison lookup fail, then serves
the captured unknown comparison successfully. This proves explicit resolver
plumbing, not F05 correctness or the remaining realistic comparison race.

The original `Pitcher.roster_status: NULL -> injured_list` diagnostics are
retained. The old content manifest still misses this value. Default-executor
receipts now include context, but that does not make roster-status content part
of the governed identity. The diagnostic custom executor deliberately remains
under its original manifest contract; its persisted complete-cohort reproduction
must not be presented as corrected default-executor proof.

No B2 roster/FatigueScore field closure, B3 readiness or full scope closure, B4
certification, R3-C reader contracts or R3-D authority change is implemented.
SP-14 G/H remain blocked. No commit, PR, merge, deployment, main change, Render
change, migration change or production activation is authorized by the current
local verdict. An exact B2 base is not yet established: B1 must finish first.

### 15.4 Final continuation receipts and demonstrated blocker

The final selected regression run passed **442 tests in 231.03 seconds**,
including R1 (39), R2 (23), migration authority (77), SP-10 (24), CU-06 (21),
atomic publication/read/cutover/route boundary (45), full chain (1),
certification (16), shadow (8), impact (10), repair (10), and existing Team
Changes/delta substrate coverage (168). Existing datetime deprecation warnings
were reported. Six tests were added in this B1 continuation; intermediate runs
overlap the final run and are not additional tests.

Shard accounting passed: **447 files, 10,038 nodes, zero missing/extra or
duplicate assignments**. `git diff --check` passed. New receipts are
`r3b1-lifecycle-baseline.xml`, `r3b1-selector-proof.xml`,
`r3b1-final-lifecycle-proof.xml`, `r3b1-regressions.xml`, and
`r3b1-blocker-diagnostics.xml` beside the existing local receipts. The first
baseline-pointer fixture used `id` instead of `singleton_id`; that local fixture
error was corrected. It was not an implementation assertion failure.

The four diagnostic assertions passed in 4.60 seconds: three retained F03/F05
probes and a new commit-window probe. **These passing assertions confirm defects,
not corrected behavior.** The new source is retained in
`backend/reports/r3b1_commit_window_probe.py`. Its ordering is:

1. Capture dashboard S1 and build an S1 payload with the default context path.
2. Pass the real selector revalidation.
3. Inside the subsequent snapshot-persistence boundary, use a separate
   PostgreSQL connection to commit S2 while the cohort is still `running`.
4. Persist S1 candidate evidence and complete/commit the cohort.
5. Confirm `cohort_inputs_are_current` is false for that complete cohort.

This is a coherent S1 payload, not evidence of mixed field content. It violates
the user's stronger B1 rule that a selector advance before semantic completion
must prevent complete status. No production write, race or publication was
manufactured. Safe source-writer coordination or another proven completion
protocol remains necessary; adding another unconstrained check alone would
merely move the race window.

**Final B1 verdict: BLOCKED.** Selector integration and the demonstrated
completion window must be resolved before B1 can be committed as PASS. F03
remains separately unresolved for B2/B3/B4. No B2 base, commit or PR was created.

## 16. R3-B1.1 — Atomic Completion Fence

**Status: BLOCKED. No completion-fence implementation is certified or added by
this continuation.** The existing B1 code, exact commit-window diagnostic, and
all earlier investigation sections remain intact. This section records the
transaction/lock investigation and new PostgreSQL counterexamples. It does not
claim that the defect was repaired because diagnostic assertions passed.

### 16.1 Current transaction map

| Step | Transaction / protection in the ordinary successful path |
| --- | --- |
| Worker run setup | Earlier control-plane transactions commit before plan execution |
| Context capture | Queries start/use the scoped Session's outer transaction; selector rows/predicates are not fenced |
| Cohort creation | `begin_nested()` is a savepoint inside that outer transaction; releasing it is not semantic completion |
| Artifact computation | Default execution uses the same Session, with copied dashboard/comparison values and other current reads |
| Final flush | Pending domain evidence is flushed; the worker heartbeat fence is invoked before revalidation |
| ORM refresh | `expire_all()` follows the flush, then plan/source selectors are reread; this handles cached objects, not concurrent commits |
| Revalidation | Plain source queries in the outer transaction compare captured versus current manifest; there is no shared selector-writer fence |
| Snapshot/status writes | Candidate persistence, complete/partial status, and optional publication job creation occur after that comparison |
| Commit | `Session.commit()` commits the outer transaction; with `commit=False`, the caller still owns the eventual commit |

Legacy source readers such as `get_latest_dashboard_snapshot` can call
`Session.rollback()` on a database error. A future fence must verify that its
owning transaction is still the transaction being completed; Session identity
alone is insufficient after rollback. No successful-lock guarantee is inferred
from a prior ORM object or a prior query.

R2's `semantic_write_fencing.validate_worker_claim` performs a Core SELECT of
the immutable claim credentials, locks the job row with `FOR UPDATE`, and checks
lease expiry using PostgreSQL time. Its `before_commit` listener protects the
outer semantic commit. That job lock prevents a replacement claim; it does not
prevent a dashboard insert or another selector writer's commit. Those are
different semantic resources. No R2 mechanism was removed or replaced.

### 16.2 Captured-selector writer map

| Captured selector | Persisted selection / competing mutation | Fence implication |
| --- | --- | --- |
| Dashboard and CU-06 sidecars | Ordered valid `DashboardSnapshot` query; insert, publication-state change, or source-row mutation can affect it | Locking selected S1 cannot prevent insertion of S2; an empty selector also has no row to lock |
| Publication baseline | `AtomicPublicationCurrent.singleton_id=1`, selected publication and coverage result | Existing SP-11 publication advisory key `711000001` protects its owner path; a pointer-row lock alone does not protect initial pointer absence or independent writers |
| Cohort predecessor | Complete/partial cohorts in comparable authority classes, globally limited to 100 before scope intersection | Status transitions, insertion, deletion or scope mutation may change selection; even unrelated cohorts can change the global candidate window |
| Legacy comparison | Selected sidecar snapshots, active ShareArtifact lifecycle, and underlying frozen-rest source snapshots | Selected endpoints alone do not lock possible new endpoints or lifecycle/absence changes; all selection-affecting writers need participation |

CU-06 rotation/workload/rest sidecars reuse the dashboard selector; they do not
require three unrelated global locks. Current fatigue/readiness/window/clock
selector coverage remains B1.2 work. Their semantic content remains B2/B3 work.

Concrete concurrent writer paths include
`dashboard_snapshot.store_dashboard_snapshot` / `publish_dashboard_snapshot`,
`team_board_delta_substrate.stamp_prospective_snapshot`,
`share_artifacts.publish_share_artifact` / `supersede_share_artifact` /
`withdraw_share_artifact`, other `execute_derived_intelligence_plan` completions,
and `atomic_publication.publish_derived_cohort`. Sidecar staging flushes into
its caller's transaction; several dashboard paths accept `commit=False`.
Protection must last until the actual owning transaction commits, not merely
until these helper functions return.

### 16.3 Mechanisms evaluated

**Selected-row locks alone are insufficient.** A PostgreSQL probe holds
`FOR UPDATE` on dashboard S1 while a separate connection inserts and commits S2.
The insert succeeds while the S1 lock is held. This is the absent/new-row case
that a completion-only row lock would miss.

**An advisory lock held only by the cohort is insufficient.** Every source
mutation capable of changing the selector must use the conflicting lock or a
database-enforced equivalent. Existing game/roster locks are not that boundary
for dashboard inserts, sidecar lifecycle or cohort predecessor transitions.

**A conditional UPDATE alone does not establish the requested commit boundary.**
It can validate at statement time, but another writer may still commit after
that statement and before the outer transaction commits unless the statement
also establishes conflicting writer protection. Moving the comparison closer
to commit is not the required proof.

**Serializable isolation alone does not establish real-time commit currentness.**
A local test uses separate SERIALIZABLE transactions: completion reads S1, a
writer commits S2, completion still reads S1 and commits its complete-state
update successfully. That execution has a valid serialization ordering without
a conflict cycle; the completion's physical commit can still follow the source
writer. This is a specific PostgreSQL counterexample, not a claim that every
serializable interleaving succeeds. No global isolation setting was changed.

**A global cohort/table fence would violate the required concurrency scope.**
The current predecessor query has a concrete global dependency: after 100
unrelated complete cohorts are inserted, the same target loses its previously
selected predecessor. A game/team-only lock would miss that event, while a
global exclusive predecessor fence would unnecessarily coordinate unrelated
cohort completion. Changing that selector's scope/limit contract must be made
explicit and tested, rather than hidden inside a locking patch.

The remaining design requires a bounded selector-generation boundary with
writer participation, including insert/absence and lifecycle transitions, and
resolution of the predecessor's global-window dependency. No new lock hierarchy
was installed without that proof. Existing R2 order remains: orchestration lock
outermost where applicable, sorted semantic resource locks before mutable rows,
non-waiting fallback for reverse-order legacy paths, and claim validation at
outer commit. A new fence must account for writers already holding row locks;
blindly waiting for another advisory lock from those paths risks inversion.

### 16.4 PostgreSQL evidence

`backend/reports/r3b11_fence_design_probe.py` preserves three additional design
counterexamples. Alongside the unchanged `r3b1_commit_window_probe.py`, the final
run passed four diagnostic assertions in 5.13 seconds:

1. S2 insertion commits while S1 is row-locked.
2. Both SERIALIZABLE transactions commit in the described stale-at-physical-
   completion ordering.
3. Unrelated cohort insertion changes the target's predecessor selection.
4. The exact original SP-10 completion-window defect still reproduces.

These are **negative design evidence**, not four passing fence regressions.
The measured S2 insertion took 63.141 ms in the final row-lock probe; this is
not completion-fence acquisition overhead or a representative production metric.
No fence exists to report acquisition SQL counts, protected crash behavior,
overlapping-cohort deadlock avoidance, or unrelated-cohort performance as proven.

Docker Desktop was initially stopped, then local PostgreSQL performed startup
recovery. Early fixture setup attempts failed before any assertions. After
readiness succeeded, one new bulk-fixture fingerprint collision was corrected
using fixed-width unique identifiers. These environment/fixture failures are
separate from the successful counterexample assertions. The final receipt is
`r3b11-fence-design-final.xml` in the existing local receipt directory.

The historical post-commit distinction is preserved: a coherent complete S1
cohort may later become non-current after an S2 commit, without rewriting its
history. The unresolved defect is specifically S2 committing before completion
while SP-10 still commits complete against S1. No production event or mutation
was manufactured.

**B1.1 remains BLOCKED.** No runtime or migration code was changed in this
continuation, no commit was created, and B1.2 has not begun. Existing uncommitted
B1 runtime work is preserved. F03 roster-status/content closure remains
unresolved; SP-14 G/H and all production authority settings are unchanged by
this work. The next work is still the atomic completion fence within B1.1,
followed by B1.2 only after B1.1 passes.

### 16.5 Preservation validation

The current PostgreSQL regression rerun passed **442 tests in 253.03 seconds**
(`r3b11-regressions.xml`): R1 39, R2 23, migration authority 77, atomic
publication/read/cutover/route boundary 45, full chain 1, and the remaining
SP-09/SP-10/CU-06/certification/shadow/repair/comparison suites listed in section
15.4. The 118 existing datetime deprecation warnings do not constitute assertion
failures. Three retained F03/F05 diagnostics separately passed in 3.55 seconds
(`r3b11-retained-diagnostics.xml`), confirming those defects remain. The four
design counterexamples are separate negative evidence, not fence correctness
tests added to the regression total.

Shard accounting passed with 447 files and 10,038 nodes, zero missing/extra or
duplicate assignments. `git diff --check` passed. This continuation changes
only this document and adds the fence-design diagnostic; all prior uncommitted
runtime/test/evidence changes are retained. Branch and HEAD remain
`fix/audit-r3-input-closure` at
`f6d493aacb95fd62ff064c14e810ab1d45186d20`. No B1.1 PASS, commit, PR, deployment,
production read/write, authority activation, or migration operation is claimed.

## 17. R3-B1.1 — Coordinated Selector Generation Fence

This section continues, rather than replaces, sections 13–16. The two retained
negative probe scripts are unchanged. Their assertions describe the unfenced
implementation and are not positive certification tests for the new protocol.
In particular, the old predecessor probe's expected failure is now superseded
by a permanent regression requiring the correct predecessor to survive 105
unrelated cohort insertions.

### 17.1 Boundary and writer inventory

The row-lock experiment failed because a newer row can be inserted. The
SERIALIZABLE experiment admitted a serial ordering that did not satisfy the
required physical completion boundary. Ordinary final revalidation had no
writer exclusion through commit. The correction therefore coordinates both
participants around semantic resources, including empty selectors.

| Domain / semantic scope | Captured reader | Writers and backstop |
| --- | --- | --- |
| Dashboard generation, `bullpen_dashboard` | Default executor's selected dashboard and CU-06's copied rotation/workload/rest source | `store_dashboard_snapshot`, `publish_dashboard_snapshot` (including bulk unpublication), `mark_dashboard_snapshot_failed`; daily/continuous/manual builders call these owners. Database guard covers INSERT/UPDATE/DELETE from older binaries and direct SQL. |
| Comparison generation, MLB team ID | `resolve_latest_team_state_comparison`, including legacy rest fallback source snapshots | `stamp_prospective_snapshot` through `share_artifact_generation`; `publish_share_artifact`, `publish_new_share_artifact`, `supersede_share_artifact`, `withdraw_share_artifact`. Database guards cover sidecar insertion, artifact lifecycle, draft/direct helper writes, and actual source-snapshot references. |
| Atomic baseline, singleton | Current publication identity and uncached reader-coverage decision | `publish_derived_cohort`; database guards on publication rows, pointer, artifact manifest, and referenced cohort snapshots cover bulk/direct mutation and inherited source dependencies. |
| Comparable predecessor, authority group + game/team/pitcher ID | `_latest_comparable_cohort` | SP-10 complete/partial transitions, including repair/replay dispatch through SP-10; old/new eligible scope is guarded on every cohort INSERT/UPDATE/DELETE. |

Final and corrected-final share one predecessor authority group. Live, roster,
and pregame have distinct groups. The predecessor predicate remains the union
of overlapping games, teams, or pitchers, with no invented date restriction.
Scope filtering now happens in PostgreSQL before ordering and selecting one
row. SQLite's compatibility path has no global pre-filter cutoff.

The isolated `incremental_publication.stage_candidate` namespace is not selected
as a bullpen dashboard. `run_cu01p_proof._seed_historical_sentinel` writes only a
disposable proof database. Neither is silently treated as a public writer;
database guards nevertheless cover any matching semantic resource it inserts.
Existing orchestration/repair paths reuse the named owners. No separate SP-13
completion path was added.

The fallback comparison resolver reads source dashboard IDs without checking
their snapshot type. Consequently the database resource resolver also follows
actual sidecar `source.snapshot_id` references, including an unusual historical
source type or a previously missing source row. Artifact lifecycle resources
also follow actual sidecar references rather than assuming artifact team and
sidecar team always agree. Two partial expression indexes bound those reverse
reference lookups. These are selector ownership checks, not F05 changes.

### 17.2 Protocol and key contract

`selector_generation_fencing.py` defines a two-integer PostgreSQL advisory-key
protocol. It uses integer subject IDs without hashing or truncation:

| Namespace | Subject |
| --- | --- |
| `510000001` | `0`: dashboard generation |
| `510000002` | Team ID: comparison generation |
| `510000003` | `0`: atomic baseline |
| `510000100 + authority_group * 3 + offset` | Game, team, or pitcher ID; offsets 0, 1, 2 |

Authority groups are live=0, final/corrected-final=1, roster=2, pregame=3.
These keys do not overlap R2's one-integer game namespace, two-integer
transaction namespace 509000000, roster keys, SP-11 publisher lock, or legacy
orchestration locks. Resources are normalized, deduplicated, and sorted by
namespace and integer subject. Out-of-range subjects fail closed.

Completion acquires transaction-scoped **shared** locks. Writers acquire
transaction-scoped **exclusive** locks. Shared readers coexist. A writer cannot
advance the same resource while a completion holds its shared lock. Unrelated
team resources remain concurrent. The two global shared resources reflect
actual global selectors, not a global exclusive cohort lock. Builds that do
not consult read-model selectors do not lock dashboard or baseline resources.

Existing writer paths may already own an R2 lock, orchestration lock, or row
lock. Their selector acquisition therefore uses nonblocking `pg_try_*` calls,
following R2's reverse-order rejection convention. Conflict requires rollback
of the owner transaction. The database backstop raises SQLSTATE `40001`; the
Python helper raises `SelectorFenceConflict`. SP-02's existing handler failure
path rolls back and records retry work. No new status vocabulary was introduced.

Waiting acquisition is only allowed explicitly at transaction entry before
other semantic/row locks. The reader-first race test uses this legal writer
path to prove waiting through the outer commit. Older binaries reach row-level
triggers after acquiring row locks, so the backstop rejects contention instead
of waiting backwards. Rejection is an allowed conflict/retry outcome, not a
claim that old binaries have learned the new Python helper.

SP-11 retains its existing publisher serialization lock **before** attempting
the nonblocking selector fence. An early implementation put the selector lock
first and broke concurrent publisher convergence; three regression failures
identified that error. The corrected order preserves R3-A. Completion never
waits for SP-11's publisher lock while holding selector locks.

Completion itself advances the predecessor selector. After shared validation,
it upgrades its own predecessor resources with nonblocking exclusive attempts.
Overlapping completions cannot wait on each other's shared locks: contention
rolls back/retries, and a surviving transaction may complete. This is distinct
from plain shared reader/reader coexistence.

### 17.3 Protected transaction map

1. Capture immutable `cohort-build-context-v1` selector values and copies.
2. Build domains and stage the cohort/input/domain rows. The nested creation
   savepoint does not end the outer owner transaction.
3. Flush domain evidence; acquire the captured selector shared locks.
4. Require the database backstop and READ COMMITTED semantics. A historical
   REPEATABLE READ snapshot cannot be presented as a fresh revalidation read.
5. Expire ORM identity state, refresh the plan, and recapture selector identities
   under the shared locks. Baseline coverage bypasses the process LRU cache.
6. Verify that no helper rolled back/restarted the completion transaction.
7. Validate the original worker claim through R2's Core `FOR UPDATE` check.
8. On mismatch, record existing `stale` domain/cohort evidence and no artifacts
   or publication job. On a match, obtain the predecessor writer fence, persist
   snapshots, and set complete/partial/failed using existing semantics.
9. Check transaction identity again. Commit while locks remain held, or flush
   and return with the locks still held when the caller owns `commit=False`.
   R2's existing outer `before_commit` claim validation remains active.

A selector advancing after a successful completion commit makes the cohort
non-current for later checks; it does not rewrite its complete historical row,
manifest, or artifacts. A fence conflict aborts the transaction and uses queue
attempt/retry evidence. An observed identity mismatch preserves a stale cohort
row. These are different existing recovery outcomes.

### 17.4 Database backstop and operational boundary

Migration `f4a7b0c3d6e9`, descending from `e3f6a9b2c5d8`, installs the resource
resolver, seven row-write guards, seven TRUNCATE refusals, and two sidecar
reference indexes. It changes no baseball rows, flags, publication pointer, or
historical manifests. The guard computes both OLD and NEW resources and fences
before mutation. Inserts cannot bypass protection merely by using a new row ID.

The migration is necessary because legacy production dashboard/share writers
do not run this topic branch's Python code. Application-only instrumentation
would not meet the stated coexistence requirement. New context completion fails
closed if the guard is absent; there is no runtime DDL installer. Disposable
test schema setup explicitly installs the reviewed migration's guards because
SQLAlchemy `create_all` alone cannot represent migration-owned triggers.

**Nothing in this package deploys this migration or changes migration authority.**
Operational protection for older binaries requires reviewed owner promotion of
this migration before integration adoption. Integration remains verify-only;
its expected-head check must not be bypassed to adopt the code prematurely.
SP-14's exact expected schema target advances to `f4a7b0c3d6e9` with the new
migration; otherwise no database could satisfy both the required guard and the
old pinned head. This changes the required schema identity, not migration
ownership, startup modes, activation controls, or Gate G/H proof. The migration
graph remains one linear chain with one head. Production is not claimed to be
at this new head.
The local migration round-trip test is not authorization for production
downgrade, stamping, or any modification of `alembic_version`.

### 17.5 Proof and remaining boundary

Permanent PostgreSQL tests exercise the real executor's completion window,
including its caller-owned commit. Reader-first blocks S2 until commit;
writer-first sees S2, preserves the stale attempt, and lets a new attempt
complete. Separate-session tests cover lock compatibility, raw old-binary
insertion rejection, overlapping shared-to-exclusive upgrade, stale ORM
objects, reclaimed worker claims, hidden transaction restart, rollback after
validation/persistence/status flush, writer rollback, and post-commit historical
drift. Resource keys are checked against the database resolver for all five
authority classes. A contract test inventories named owners and enabled guards.

The first broad run found 13 implementation regressions: three publication lock
order failures and ten scoped-session adapter failures. Both causes were fixed;
no assertion was weakened. The next focused run passed 206 tests in 92.35 seconds.
At that checkpoint, a baseline context's fence required 36 SQL statements and
14.977 ms; uncontended exclusive acquisition took 0.773 ms. An intentionally
held reader made its writer wait 168.962 ms. Independent compatible acquisition
plus commit took 8.109–33.807 ms. These are local PostgreSQL fixture measurements,
not production latency claims or full cohort-content closure benchmarks.

Final regression receipts and verdict are recorded below when validation ends.
The original roster-status diagnostic remains required negative evidence:
`Pitcher.roster_status NULL -> injured_list` still changes public content while
the old/custom-executor manifest remains `[]`. The selector context does not
close roster, workload, or readiness content.

Remaining B1.2 selectors: fatigue, readiness, transaction windows, remaining
artifact selection, clock fallback authority, and canonical-version consumer
paths. In particular, this database fence does not freeze the passage of product
time. B1.2 must establish that selector context separately. Then B2 closes
roster/workload semantics, B3 the remaining semantic inputs, and B4 certifies
complete closure. R3-C reader contracts and R3-D comparison authority remain
separate packages. **F03 remains CONFIRMED and UNFIXED. SP-14 G/H remain blocked.**

### 17.6 Final local receipts and verdict

**PASS — R3-B1.1 COMPLETE; R3-B1.2 MAY BEGIN (local implementation proof).**
This is not an operational deployment verdict or an F03 PASS.

| Receipt / scope | Result |
| --- | --- |
| `r3b11-coordinated-final.xml`, expanded PostgreSQL regression run | 679 passed, one shared migration-head pin failure, 452.87 seconds |
| `r3b11-coordinated-final-followup.xml`, final completion/certification/shadow/migration and failed-head checks | 155 passed, 74.33 seconds |
| Union of expanded run and final follow-up, latest result per test | 683 distinct tests passed; no unresolved failures |
| SP-10, including new permanent fence cases | 51 passed; 27 cases added in B1.1 |
| R1 roster isolation/authority/health | 39 passed |
| R2 shared writer fencing | 23 passed, including existing numerical regression |
| SP-02 queue/worker claims | 18 passed |
| SP-11/R3-A publication, cutover, reads, route boundary | 45 passed |
| Full chain | 1 passed |
| Migration authority | 77 passed |
| SP-14 certification / shadow | 17 / 8 passed; G/H still blocked without proof |
| Preserved F03/F05 diagnostic, `r3b11-coordinated-retained-diagnostics.xml` | 3 diagnostic assertions passed, 3.66 seconds; defects remain reproduced |
| Shard/accounting | 447 files, 10,066 nodes, zero missing/extra/duplicate assignments |
| Whitespace validation | `git diff --check` passed |

The migration-head failure in the expanded run was an explicit shared test pin
still expecting `e3f6a9b2c5d8`. Updating that pin to the reviewed successor and
rerunning the affected graph checks preserved the one-head assertion; no test
was relaxed to accept multiple or arbitrary heads. The final graph is exactly
`f4a7b0c3d6e9`. The follow-up also added proof that the old head fails Gate A and
the new head alone does not advance G/H.

Final measured PostgreSQL timings: 36 SQL statements / **14.345 ms** for shared
completion fence acquisition on a baseline context containing 30 comparison
resources plus dashboard, publication, and three predecessor resources;
**0.747 ms** for uncontended exclusive acquisition; **169.326 ms** writer wait
including the deliberate 150 ms hold; **111.549 ms** for an entire unrelated
cohort to build and commit while the first cohort remained inside its protected
completion boundary. The latter test requires both cohorts to persist complete.
These measurements are bounded local fixtures, not production benchmarks.

The original persisted roster-status diagnostic still produced complete cohort
IDs 2 and 4, different `pitcher_snapshot.pitcher.roster_status` values, and the
same two-byte `[]` manifests. The sparse/injected-executor measurement is not
reused as a performance claim for the fence. An exact copy is now retained at
`backend/reports/r3b_input_closure_probe.py`; the original external diagnostic
and the two earlier worktree probes remain preserved.

The package remains on `fix/audit-r3-input-closure`, based exactly on
`f6d493aacb95fd62ff064c14e810ab1d45186d20`. The local commit contains the coherent
captured-context/fence slice and its accumulated diagnostic history. No push,
PR, merge, deployment, Render change, production database operation, or public
authority activation is part of this completion. B1.2 has not begun.
