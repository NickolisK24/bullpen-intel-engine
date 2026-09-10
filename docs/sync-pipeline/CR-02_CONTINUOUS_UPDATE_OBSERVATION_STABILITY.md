# CR-02 Continuous Update Observation Stability

## 1. Objective

CR-02 makes continuous-update health describe unresolved required truth, not harmless concurrency or transport repetition. It preserves every finality and live monotonicity guard while separating safe no-ops from blocking acquisition, authority, and canonicalization failures.

## 2. Starting Integration SHA

`679a06e73c156d5189e08cff866686d9571369ec`

## 3. Production Failure Cases

The production database was inspected read-only from the existing manual `shadow_sp` GitHub Actions lane. SyncRuns `6498`, `6499`, and `6500` were all `partial` with `records_failed=2` and no `SyncFailure` rows.

| Case | Current classification | Current run effect | Correct meaning | Correct run effect | Retryable |
| --- | --- | --- | --- | --- | --- |
| game `823172` | `stale_observation`, `older_upstream_observation` | appeared beside partial run logs | older evidence was safely prevented from replacing current state | success/no-op, stale counter | no |
| game `824226` | `ambiguous_observation`, `equal_revision_with_different_material_content` | appeared beside partial run logs | current accepted state remained valid while equal-revision content was rejected | success with warning | no |
| job `328`, game `823090` | `plan_authorization`, `ValueError`, `plan_fingerprint_derivation_failed` | poisoned runs `6498`-`6500` without consuming an attempt | accepted final work lacked a stable automatic plan date during that attempt | partial plus durable retry | yes |
| job `329`, game `823251` | same | poisoned runs `6498`-`6500` without consuming an attempt | same transient plan-authorization defect | partial plus durable retry | yes |

The later durable records prove the distinction: job `329` completed as `canonical_no_op`; job `328` progressed through canonical and downstream stages before a separate publication-equivalence terminal failure. The rejected observations did not cause either job failure.

## 4. Root Cause

Continuous execution previously summarized all rejected observations under one coarse label while separately rotating automatic plan-authorization failures without claiming the durable job. The compact production logs made those two facts look causal, and the unclaimed rotation did not consume retry attempts. Automatic plan fingerprint derivation also depended solely on the observation payload's official date even though the durable job already carried its governed baseball date.

CR-02 fixes the root causes by:

1. assigning a controlled outcome, severity, retry decision, and required-obligation flag to each observation;
2. deriving automatic plan identity with the durable job's `product_date` as a fail-closed fallback;
3. claiming production canonical work before automatic authorization, so superseded work is skipped before source reads and real authorization failures consume normal retry attempts;
4. retaining manual reviewed-plan behavior unchanged outside production modes.

## 5. Observation Outcome Vocabulary

| Outcome | Severity | Blocks required obligation | Retry |
| --- | --- | --- | --- |
| `accepted_change` | healthy | no | no |
| `accepted_no_change` | healthy | no | no |
| `duplicate` | healthy | no | no |
| `stale` | healthy | no | no |
| `superseded` | healthy | no | no |
| `safe_rejection` | warning | no | no |
| `ambiguous_nonblocking` | warning | no | no |
| `optional_partial` | warning | no | no |
| `ambiguous_blocking` | blocking | yes | yes |
| `malformed` | blocking | yes | yes |
| `source_failure` | blocking | yes | yes |
| `invariant_violation` | blocking | yes | no |

Source classification remains available separately; normalization does not erase the original classification or reason.

## 6. Stale Contract

`older_upstream_observation` is `stale`. `weaker_source_authority` is `superseded`. Both preserve the current `GameObservationState`, create no canonical mutation or downstream work, do not create `SyncFailure`, consume no retry, and leave the run successful unless another blocking condition exists.

## 7. Duplicate Contract

An exact material fingerprint replay is `duplicate`. The SP-03 fetch attempt remains observable, current state timestamps are not rewritten, canonical and downstream mutation counts stay zero, and the run succeeds.

## 8. Superseded Contract

Weaker observation authority and durable canonical work whose observation fingerprint is no longer current are superseded. Durable work is skipped before automatic plan authorization, preventing stale source reads, state regression, and false run failure.

## 9. Safe Rejection Contract

A newer live/pending payload that would regress accepted Final evidence is `safe_rejection`. State remains Final, no downstream work is created, and the run records a warning rather than a failure. A partial live projection is `optional_partial` only when an accepted current authority already exists; otherwise it is blocking.

## 10. Ambiguity Contract

Equal-revision material disagreement is `ambiguous_nonblocking` when a current accepted authority exists. It is recorded as a warning and cannot mutate state. Missing or incomparable authority without a satisfied required obligation is `ambiguous_blocking`, makes the run partial, and remains retryable.

## 11. Run-Level Status Rules

- `success`: every required observation or durable obligation changed, completed, or safely produced a no-op/rejection; warnings may exist.
- `partial`: at least one required observation or durable obligation remains unresolved while the cycle otherwise ran.
- `failed`: the cycle cannot perform its core responsibility or violates an internal invariant. The bounded command continues to use its established partial exit for per-item failures and a nonzero process exit.

Warnings alone do not set `records_failed`, `errors`, or partial status. Blocking outcomes and true durable-stage failures do.

## 12. Retry Rules

Duplicates, stale observations, superseded observations, safe rejections, and nonblocking ambiguity do not retry. Source failures, malformed required payloads, blocking ambiguity, and automatic plan-authorization failure retry through their existing owner/durable job policy. A claimed plan-authorization failure now advances the durable attempt count and can reach an inspectable terminal state instead of rotating forever.

## 13. SyncFailure Boundary

CR-02 does not create `SyncFailure` rows for observation no-ops or warnings. `SyncRun.outcome_json.observation_outcomes` stores aggregate controlled outcomes, and `observation_warnings` stores bounded game/classification/reason evidence. Existing real source, canonicalization, invariant, and blocking-obligation failure paths remain eligible for failure evidence.

## 14. CU / Shadow Coexistence

Both CU and production shadow may observe one game. The current observation fingerprint and source authority remain the arbitration point. A late older worker is stale/superseded and cannot derive or execute a plan. The manual `shadow_sp` proof lane now additionally runs one bounded `shadow_detect` CU observation cycle with production publication disabled; it does not change cadence or public authority.

## 15. Before / After Production Evidence

Before CR-02, runs `6498`-`6500` were partial with two plan-authorization failures, while nearby stale/ambiguous log lines obscured the cause.

The manual production-shadow run [34469053729](https://github.com/NickolisK24/bullpen-intel-engine/actions/runs/34469053729) executed commit `2707e3339f99591f41c7f0cc502c9aa13b15592a` against production data and created continuous SyncRun `6859`:

- game `823172`: `stale_observation` / `older_upstream_observation` normalized to healthy `stale`;
- game `824226`: `ambiguous_observation` / `equal_revision_with_different_material_content` normalized to warning `ambiguous_nonblocking`;
- games `823088`, `823413`, `823499`, `824550`, and `824872`: accepted as real changes with SP-03 SourceObservation IDs `79` through `83`;
- result: `complete`, zero blocking ambiguities, zero source failures, zero run failures, one warning, no publication target, and `production_authority_affected=false`.

The cycle made eight source requests, checked seven games, and completed in 8.851 seconds. Thus the same two naturally recurring rejected cases no longer poison the run, while five genuine mutations were retained rather than masked.

## 16. Health Impact

Operational health now exposes recent CU warning, stale, duplicate, safe-rejection, blocking-ambiguity, and unhealthy-run counts. Warning/no-op counters are visible but do not degrade health. Recent partial/failed continuous runs degrade health as `continuous_update_required_obligation_unresolved`. Existing dead jobs and authoritative completeness failures remain blockers.

The post-proof health report at `2026-09-10T11:16:17.597072` recorded one stale observation, one warning, zero blocking ambiguities, and the successful new run. It still counted 186 older unhealthy continuous runs inside the 24-hour lookback, plus the already-known missing atomic pointer and 30-team SP roster authority blockers. Those historical/other-package conditions correctly remain visible and are not relabeled healthy by CR-02.

## 17. Remaining Blockers

CR-02 does not resolve job `328`'s later `dashboard_snapshot_slate_coverage_incomplete` publication-equivalence failure. It does not cut over atomic publication, migrate readers, activate morning/nightly orchestration, or retire legacy execution. Those remain separate certification remediation work.

## 18. Validation

The focused suite covers stale, duplicate, superseded, safe-rejection, optional versus blocking ambiguity, malformed/source failures, finality regression, plan-date fallback, durable retry consumption, stale-work pre-authorization suppression, command counters, and health classification. Local focused validation passed 255 tests with one environment skip; workflow/isolation and CI-accounting validation passed 216 tests. PostgreSQL-backed CI remains the authority for concurrency and database behavior. The manual production-shadow workflow supplied natural lineage evidence without enabling publication.

## 19. CR-02 Verdict

CR-02 verdict: **PASS**. The post-change natural cycle remained healthy for the exact recurring stale and equal-revision cases, accepted five real changes, retained fail-closed blocking behavior in tests, and left publication authority untouched. Overall SP-14 certification remains NO-GO for the unrelated blockers listed above.
