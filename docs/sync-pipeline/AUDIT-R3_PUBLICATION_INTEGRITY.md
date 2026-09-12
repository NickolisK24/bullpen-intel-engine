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
