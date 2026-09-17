# BaseballOS Supabase Egress P0 Closeout

## 1. Final Status

**RESOLVED**

The runaway Supabase egress condition is no longer active. Settled production
usage fell from approximately 106 GB on September 15 to 21.524 GB on September
16, a reduction of approximately 79.7%. September 16 included representative
game-day and final-authority processing, so the recovery is not based on an idle
day. The incident-level remediation is complete.

The remaining approximately 20–22 GB/day Shared Pooler baseline is not an
unresolved P0. It is a bounded operational optimization item described in
Section 8.

## 2. Incident Summary

The sync-pipeline shadow service repeatedly retrieved the same immutable
historical Dashboard payloads while building and revalidating derived
intelligence across all 30 teams. A representative historical set contained
eight payloads totaling 44,593,768 bytes, but the old execution shape
retransmitted that set at team-loop scale and again during same-identity
revalidation.

Daily Supabase egress repeatedly reached approximately 50–100+ GB/day, with
September 15 settling near 106 GB. That consumption materially exceeded the
Pro-plan included allowance and created immediate cost and capacity risk. The
measured traffic was dominated by database/Shared Pooler transfer rather than
normal public traffic.

Work on `feat/sync-pipeline` was frozen so investigation and remediation could
proceed without adding more read paths or obscuring attribution. The affected
execution surface was the non-publishing Render sync-pipeline shadow service and
its Supabase database reads. Public baseball semantics and publication authority
were not transferred or relaxed during the incident.

## 3. Timeline

| Date | Milestone |
| --- | --- |
| September 13, 2026 | Initial P0 investigation began after recurring daily egress in the approximately 50–100+ GB range. Sync-pipeline feature work was halted. Phase 1 attributed the traffic to database/Shared Pooler activity and ruled out normal public traffic as an explanation for the scale. |
| September 15, 2026 | Phase 2 identified the dominant source: repeated team-multiplied reads of eight immutable historical Dashboard payloads totaling approximately 44.59 MB per unique set. Retained cohorts reconstructed approximately 64.2 GB from this path; higher log-derived estimates were treated as directional rather than exact billing. |
| September 15, 2026 | PR #847 merged into `feat/sync-pipeline` at `470e9f373a575c57c51d7fa4bdc736692c353ff7`. It introduced operation-scoped historical payload reuse without changing selection or validation. |
| September 16, 2026 | Production proved #847 with snapshot IDs `[452, 483, 514, 564, 595, 626, 657, 688]`, eight database payload fetches, 232 reuse hits, 30 team consumers, 44,593,768 bytes loaded, and zero additional same-ID completion-revalidation fetches. |
| September 16, 2026 | Investigation of repeated failed cohorts found stale pre-final live work surviving final-authority takeover. The fail-closed `live_selector_superseded_by_final` guard was correct; authority needed to be rechecked before cohort creation. |
| September 16, 2026 | PR #848 merged at `d94c21514ae713a86ad505c1fff2349c850f0994`. Controlled production proof on 10 real jobs produced 10 final-owner detections, 10 superseded plans, 10 successful no-work jobs, no new cohort, no publication job, and no new selector failure. |
| September 16, 2026 | The controlled #848 exercise exposed two separate operational issues: a legitimate final-authority 30-team path exceeded the 512 MiB Render limit, and INFO telemetry was filtered because the shadow entrypoint had not enabled INFO logging. |
| September 16, 2026 | PR #849 merged at `67bc6527042980baa58db7e718fefa13791dc548`. It removed avoidable deep copies, streamed the historical Dashboard projection, shortened large-object lifetimes, enabled INFO logging, and added bounded RSS telemetry. |
| September 16, 2026 | A legitimate final-authority 30-team path completed without OOM. Container peak memory was approximately 475.512 MiB, leaving approximately 36.488 MiB / 7.13% headroom under the 512 MiB limit. |
| September 16, 2026 | Settled egress measured 21.524 GB versus approximately 106 GB on September 15, a reduction of approximately 79.7%. No OOM or `live_selector_superseded_by_final` storm recurred. The P0 was closed. |

## 4. Root Causes

### Primary egress cause

The shadow derived-intelligence path loaded the same immutable historical
Dashboard payloads repeatedly inside team iteration and completion
revalidation. The database therefore transmitted a roughly 44.59 MB historical
set at a multiplicative rate rather than once per compatible operation.

### Contributing correctness and operational defects

- **Stale live authority:** pre-final live plans could remain executable after a
  current `FinalGameVersion` took ownership. The correct fail-closed selector
  then rejected those cohorts, causing repeated invalid work rather than
  incorrect publication.
- **Peak working set:** the valid 30-team capture/revalidation path held several
  large representations concurrently, including avoidable deep copies of the
  historical payloads. This was a single-operation peak problem, not proven to
  be a cross-job leak.
- **Missing INFO bootstrap:** the shadow entrypoint did not enable INFO logging,
  so structured INFO events were discarded before Render could receive them.

These defects were related through the shadow execution path but were not one
root cause. The historical refetch pattern caused the dominant egress; stale
authority, peak memory, and logging visibility required separate corrections.

## 5. Remediations

### PR #847 — Historical Dashboard payload reuse

- **Purpose:** stop retransmitting identical immutable historical payloads for
  every team and during same-ID revalidation.
- **Behavior changed:** each unique historical snapshot is loaded once per
  compatible `execute_derived_intelligence_plan` operation and reused from an
  operation-scoped immutable representation. Changed IDs still load normally.
  Historical selection and every validation remain unchanged.
- **Production evidence:** eight selected IDs; eight payload fetches; 232 reuse
  hits; 30 team consumers; 44,593,768 bytes loaded; zero additional same-ID
  completion-revalidation fetches.
- **Status:** fetch/reuse behavior is production-verified.

### PR #848 — Stale live-authority suppression

- **Purpose:** prevent pre-final live work from creating failed cohorts after
  final authority takes ownership.
- **Behavior changed:** execution rechecks final authority before live cohort
  creation. Stale plans become superseded and their jobs finish successfully
  with `cohort_status=no_work` and
  `zero_work_reason=live_authority_superseded_by_final`. The
  `live_selector_superseded_by_final` guard remains unchanged and fail-closed.
- **Production evidence:** 10/10 real stale jobs detected final ownership;
  10/10 plans were superseded; 10/10 jobs succeeded with no-work semantics; no
  cohort, publication job, or new selector failure was created.
- **Status:** functional behavior is production-proven. The specific
  `stale_live_derived_work` INFO event was not re-exercised after the logging fix
  because no claimable stale jobs remained; this visibility gap does not reopen
  the corrected authority behavior or the egress P0.

### PR #849 — Peak-memory and INFO-telemetry remediation

- **Purpose:** keep legitimate 30-team final-authority execution under the 512
  MiB limit and make structured INFO telemetry visible in Render.
- **Behavior changed:** unnecessary full-payload deep copies were removed,
  historical projection became incremental, large-object lifetimes were
  shortened, the normal shadow entrypoint enabled INFO logging, and bounded RSS
  phase telemetry was added.
- **Production evidence:** a legitimate final-authority 30-team path completed;
  no OOM occurred; container peak was approximately 475.512 MiB with
  approximately 36.488 MiB / 7.13% headroom. The #847 reuse event was visible
  and preserved the eight-fetch behavior.
- **Status:** memory remediation and INFO logging are production-verified.

## 6. Recovery Evidence

| Signal | Before / incident | After remediation |
| --- | ---: | ---: |
| Settled daily egress | September 15: approximately 106 GB | September 16: 21.524 GB |
| Daily reduction | — | approximately 79.7% |
| Workload representation | Game-day and final-authority processing | Representative processing also occurred on September 16 |
| Shadow OOM | Recurred on legitimate final-authority work | No recurrence after #849 |
| Stale-live selector storm | Repeated failed cohorts | No recurrence after #848 deployment |
| Measured egress category on September 16 | Database/Shared Pooler dominant | 100% Shared Pooler Egress |

The reduction is billing-level recovery evidence, while the PR-specific
telemetry proves the corrected execution shape. Neither signal substitutes for
the other.

## 7. What Was Not Changed

- No Supabase plan upgrade was required.
- No Render memory-tier upgrade was required.
- No integration-only sync-pipeline architecture was imported into `main`.
- The `live_selector_superseded_by_final` guard was not weakened or bypassed.
- Publication rules, authority gates, and public baseball semantics were not
  relaxed.
- No synthetic baseball mutation was required for final recovery proof.
- Shadow cadence, schedules, flags, environment variables, and publication
  configuration were unchanged.

## 8. Remaining Non-P0 Work

### Shared Pooler Baseline Optimization

**Priority:** non-P0 / operational optimization

Scope:

- understand the legitimate approximately 20–22 GB/day post-fix Shared Pooler
  baseline;
- identify the remaining highest-byte read paths;
- determine whether projected monthly usage is acceptable; and
- optimize only where measurement justifies it.

This work is not started by this closeout branch and is not an emergency
extension of the resolved P0.

## 9. Permanent Engineering Guardrails

- Every new sync or read-model path must document expected rows per execution,
  payload bytes, call frequency, team-wide versus league-wide multiplicative
  factor, and expected peak memory.
- Immutable league-wide data should be fetched once and reused many times within
  an explicitly compatible operation.
- Large JSON payloads must not be deep-copied casually; mutable consumers should
  receive the smallest required projection.
- Production proof must distinguish functional correctness from settled billing
  recovery.
- Infrastructure upgrades should follow measured optimization, not replace
  root-cause analysis.
- Fail-closed authority guards must remain intact.

## 10. Resume Decision

The Supabase egress P0 no longer blocks `feat/sync-pipeline`.

Development may resume from the exact pre-incident sync-pipeline checkpoint.
Incident branches must not be reopened for normal feature work.

## Sync Pipeline Resume Checkpoint

- **Authoritative integration SHA:**
  `67bc6527042980baa58db7e718fefa13791dc548` on `feat/sync-pipeline`.
- **Last completed milestone before the P0 interruption:** R3-B1.2-A,
  Reference Time and Canonical Version Capture, integrated through PR #842 at
  `0d34fdc0befb545739f7958c7dc3ecb9d2591525`. Its local/integration verdict is
  `R3-B1.2-A COMPLETE; R3-B1.2-B MAY BEGIN`. F03 remains confirmed and
  unresolved; SP-14 Gates G/H remain blocked.
- **Next planned milestone:** R3-B1.2-B. Do not skip ahead to B1.2-C, B2,
  R3-C, R3-D, or activation.
- **Incident-era branches that remain closed:** the merged branches for PR #847
  (`fix/shadow-historical-dashboard-reuse`), PR #848
  (`fix/final-authority-stale-live-suppression`), and PR #849
  (`fix/shadow-runner-peak-memory-and-info-telemetry`). Normal feature work must
  start from the authoritative integration line rather than reopening them.
- **Temporary monitoring state:** P0 emergency monitoring and repeated
  verification can stop. Ordinary usage observation may continue only within
  the non-P0 Shared Pooler Baseline Optimization follow-up. No temporary
  schedule, flag, environment, publication, or infrastructure state needs to
  remain active.

This checkpoint records the handoff only. It does not begin R3-B1.2-B or change
any production authority.
