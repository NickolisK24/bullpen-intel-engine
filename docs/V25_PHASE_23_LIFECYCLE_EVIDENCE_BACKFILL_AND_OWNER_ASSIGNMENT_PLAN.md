# BaseballOS V2.5 Phase 23 - Lifecycle Evidence Backfill and Owner Assignment Plan

## Decision

Status:

```text
PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN_COMPLETE
```

BaseballOS V2.5 Phase 23 converts the Phase 22 lifecycle review log and
adoption audit findings into an ownership and evidence acquisition framework.
Phase 21 defines the enforcement checklist. Phase 22 proves checklist adoption
through review logging and audit requirements. Phase 23 defines the evidence
that must be backfilled before prototype, experimental, or legacy surfaces can
move to a new lifecycle state.

This phase is governance and documentation only. It does not change
Recommendation Engine behavior, fatigue formulas, API contracts, ranking
behavior, selection behavior, prediction behavior, frontend runtime behavior,
or certified production behavior.

## Phase Purpose

The purpose of Phase 23 is to eliminate ambiguity around lifecycle evidence.

Every surface that seeks promotion, demotion, deprecation, or removal must have
a clear owner, evidence package, review path, and remaining-gap record before a
classification change can be accepted.

Phase 23 establishes:

- who owns evidence collection
- what evidence is required
- which evidence is currently missing
- which surfaces are blocked from promotion
- which legacy surfaces require migration evidence before deprecation
- which evidence should be acquired first
- how future lifecycle review records should prove evidence completeness

## Scope

Phase 23 applies to:

- certified production surfaces
- supported governance, API, script, and frontend helper surfaces
- prototype surfaces
- experimental surfaces
- legacy surfaces
- future deprecated or removed surfaces
- intelligence, recommendation, fatigue, availability, prospect, report, and
  operational tooling surfaces

Phase 23 does not reclassify any surface.

Phase 23 does not authorize:

- new Recommendation Engine endpoints
- new fatigue calculations
- new public contracts
- new ranking behavior
- new pitcher selection behavior
- new prediction behavior
- new best, preferred, or recommended option behavior
- frontend runtime behavior changes

## Summary Of Phase 22 Findings

Phase 22 established the lifecycle review log and adoption audit layer.

Phase 22 found:

- certified V2 production remains limited to `GET
  /api/recommendations/v2/bullpen-state` and the Dashboard V2 Bullpen State
  panel
- accepted production surfaces remain production unless their scope changes
- supported surfaces require lifecycle review before production eligibility
- prototype surfaces lack complete ownership, purpose, maintenance, and
  evidence packages
- experimental surfaces lack complete metadata, test, limitation, and
  governance evidence packages
- legacy surfaces are not ready for deprecation because consumer review,
  migration, and replacement evidence remain incomplete
- no prototype or experimental surface is currently promotion-ready

Phase 23 turns those findings into a backfill plan.

## Current Lifecycle Classifications

The current lifecycle classifications remain unchanged from Phase 22.

| Surface | Current Classification | Phase 23 Classification Decision |
|---------|------------------------|----------------------------------|
| Dashboard | PRODUCTION | Unchanged. |
| Bullpen | PRODUCTION | Unchanged. |
| V2 bullpen-state API | PRODUCTION | Unchanged certified scope. |
| V2 Bullpen State panel | PRODUCTION | Unchanged certified scope. |
| V1 candidate API and panel | PRODUCTION | Unchanged candidate-level scope. |
| Bullpen fatigue APIs | PRODUCTION | Unchanged. |
| Bullpen read APIs | PRODUCTION | Unchanged. |
| Methodology | SUPPORTED | Unchanged. |
| Admin sync and recalculation | SUPPORTED | Unchanged. |
| Frontend API normalizers | SUPPORTED | Unchanged. |
| Availability governance reports and scripts | SUPPORTED | Unchanged. |
| Prospect Pipeline UI | PROTOTYPE | Not promotion-ready. |
| Prospect APIs | PROTOTYPE | Not promotion-ready. |
| Dashboard Pipeline Snapshot | PROTOTYPE | Not promotion-ready. |
| Fatigue-to-ERA insight | EXPERIMENTAL | Not promotion-ready for Supported. |
| Latest-workload snapshot mode | EXPERIMENTAL | Not promotion-ready for Supported. |
| MLB passthrough helpers | EXPERIMENTAL | Not promotion-ready for Supported. |
| Threshold experimentation tooling | EXPERIMENTAL | Not promotion-ready for Supported. |
| Metadata-less fatigue array response | LEGACY | Not ready for deprecation. |
| Standalone fatigue recalculation script | LEGACY | Not ready for deprecation. |
| Deprecated production surfaces | DEPRECATED | None currently discovered. |

## Surface Ownership Requirements

Every surface must have ownership evidence before lifecycle movement.

Ownership evidence must include:

- maintainer of record
- owning area
- escalation path
- review approver
- maintenance expectation
- evidence collection owner
- follow-up due date when evidence is incomplete

Ownership states:

| Ownership State | Meaning | Lifecycle Impact |
|-----------------|---------|------------------|
| Assigned | Maintainer and owning area are documented. | Eligible for next evidence review. |
| Partial | Owning area exists, but maintainer or approver is incomplete. | Blocked from promotion. |
| Missing | No owner evidence exists. | Blocked from all upward movement. |
| Retiring | Owner is assigned for migration, deprecation, or removal only. | Eligible only for legacy/deprecation review. |

Nikko remains the maintainer of record for BaseballOS governance records. Each
surface still needs an owning area and evidence collection owner before its
classification can move upward.

## Runbook Requirements

Every supported, production, experimental-intelligence, or legacy-retirement
surface must have runbook evidence appropriate to its lifecycle tier.

Runbook evidence must define:

- normal operation
- refresh or recalculation expectations
- source data requirements
- failure modes
- stale-data behavior
- refusal behavior where applicable
- fail-closed behavior where applicable
- manual recovery or rollback expectations
- consumer communication expectations
- maintenance cadence

Prototype surfaces need a lightweight operating note before moving to
Experimental. Experimental surfaces need a complete runbook before moving to
Supported. Legacy surfaces need a migration and retirement runbook before
moving to Deprecated.

## Metadata Evidence Requirements

Metadata evidence is mandatory for intelligence surfaces and any surface whose
output depends on freshness, trust, refusal, or governance boundaries.

Required metadata evidence:

- trust metadata fields and meaning
- freshness metadata fields and meaning
- data-through timestamp expectations
- generated-at timestamp expectations
- stale-data threshold and display behavior
- refusal metadata fields and reasons
- fail-closed conditions
- unsupported-state behavior
- missing-data behavior
- malformed-data behavior
- public display requirements where metadata is user-facing

Metadata evidence must be documented before Experimental -> Supported or
Supported -> Production movement for intelligence surfaces.

## Testing Evidence Requirements

Testing evidence must match the lifecycle tier requested.

Required testing evidence:

- backend tests for route, service, metadata, refusal, and fail-closed behavior
  where applicable
- frontend tests for display, limitation copy, metadata rendering, and refusal
  rendering where applicable
- script or report tests for governance tooling where applicable
- regression tests proving certified V2 boundaries remain unchanged
- stale, missing, malformed, and unsupported data tests where applicable
- migration tests before deprecation or removal where applicable

Passing validation alone is not promotion evidence unless the tests explicitly
cover the requested lifecycle behavior.

## Governance Evidence Requirements

Governance evidence must prove the requested lifecycle movement preserves
BaseballOS boundaries.

Required governance evidence:

- current classification
- requested classification
- Phase 21 checklist used
- Phase 22 lifecycle review log entry
- Phase 23 evidence gap status
- affected backend routes
- affected frontend routes
- affected scripts and reports
- affected public contracts
- current limitations
- public copy review
- ranking behavior review
- selection behavior review
- prediction behavior review
- best, preferred, and recommended behavior review
- decision and remaining-risk record

## Certification Evidence Requirements

Certification evidence is required before production eligibility.

Required certification evidence:

- owner acceptance
- runbook evidence
- contract review
- trust metadata evidence where intelligence is shown
- freshness metadata evidence where intelligence is shown
- refusal metadata evidence where refusal can occur
- fail-closed evidence where unsafe output could otherwise be exposed
- anti-ranking validation
- anti-selection validation
- anti-prediction validation
- test evidence
- limitation evidence
- rollout readiness evidence
- rollback or contingency evidence
- final certification decision

No Supported -> Production transition can proceed without a certification
record and rollout review record.

## Legacy Migration Evidence Requirements

Legacy surfaces cannot move to Deprecated or Removed until consumer impact is
understood and a migration path exists.

Required legacy migration evidence:

- consumer inventory
- replacement surface or retirement rationale
- migration path
- migration period
- notice plan
- rollback or contingency plan
- compatibility risk review
- docs update plan
- test update plan
- governance approval
- final deprecation or removal decision

Current legacy surfaces are not ready for deprecation.

## Evidence Acquisition Framework

Evidence acquisition uses a staged framework.

1. Classify the surface.
2. Assign maintainer and owning area.
3. Identify the requested lifecycle movement.
4. Attach the applicable Phase 21 checklist.
5. Create or update a Phase 22 lifecycle review log entry.
6. Inventory routes, UI surfaces, scripts, reports, contracts, and consumers.
7. Backfill owner evidence.
8. Backfill runbook evidence.
9. Backfill metadata evidence where applicable.
10. Backfill test evidence.
11. Backfill governance evidence.
12. Backfill certification or migration evidence where applicable.
13. Reassess promotion, demotion, deprecation, or removal readiness.
14. Record decision, blockers, and next owner action.

Evidence status values:

| Status | Meaning |
|--------|---------|
| Complete | Evidence exists and is attached to the lifecycle record. |
| Partial | Some evidence exists but gaps remain. |
| Missing | Evidence is not yet documented. |
| Not Applicable | Evidence is not required for this surface or transition. |
| Blocked | Evidence cannot be completed until another decision or owner action occurs. |

## Surface-By-Surface Evidence Gap Inventory

| Surface | Current Classification | Owner Evidence | Runbook Evidence | Metadata Evidence | Test Evidence | Governance / Certification / Migration Gap |
|---------|------------------------|----------------|------------------|-------------------|---------------|--------------------------------------------|
| Dashboard | PRODUCTION | Complete | Partial | Partial | Complete | Needs review only if production scope changes. |
| Bullpen | PRODUCTION | Complete | Partial | Partial | Complete | Needs review only if production scope changes. |
| V2 bullpen-state API | PRODUCTION | Complete | Complete | Complete | Complete | Certified scope unchanged; expansion requires new certification. |
| V2 Bullpen State panel | PRODUCTION | Complete | Complete | Complete | Complete | Certified scope unchanged; expansion requires new certification. |
| V1 candidate API and panel | PRODUCTION | Complete | Partial | Partial | Complete | Candidate-level scope must not become bullpen ranking or final selection. |
| Bullpen fatigue APIs | PRODUCTION | Complete | Partial | Partial | Complete | Legacy review required before any contract retirement. |
| Bullpen read APIs | PRODUCTION | Complete | Partial | Partial | Complete | Consumer review required before removal or contract replacement. |
| Methodology | SUPPORTED | Complete | Partial | Not Applicable | Partial | Production classification would require runbook and evidence review. |
| Admin sync and recalculation | SUPPORTED | Partial | Partial | Partial | Complete | Needs complete operational runbook before production classification. |
| Frontend API normalizers | SUPPORTED | Partial | Partial | Not Applicable | Complete | Needs owner and contract evidence before production classification. |
| Availability governance reports and scripts | SUPPORTED | Partial | Partial | Partial | Partial | Needs report runbook and evidence retention rules before promotion. |
| Prospect Pipeline UI | PROTOTYPE | Partial | Missing | Missing | Partial | Blocked from Experimental until owner, purpose, runbook, and limitation evidence are complete. |
| Prospect APIs | PROTOTYPE | Partial | Missing | Missing | Partial | Blocked from Experimental until owner, purpose, maintenance, contract, and test evidence are complete. |
| Dashboard Pipeline Snapshot | PROTOTYPE | Partial | Missing | Missing | Partial | Blocked from Experimental until snapshot purpose, freshness, display, and limitation evidence are complete. |
| Fatigue-to-ERA insight | EXPERIMENTAL | Partial | Missing | Missing | Partial | Blocked from Supported until metadata, limitation, test, and governance evidence are complete. |
| Latest-workload snapshot mode | EXPERIMENTAL | Partial | Missing | Partial | Partial | Blocked from Supported until freshness, runbook, fail-closed, and test evidence are complete. |
| MLB passthrough helpers | EXPERIMENTAL | Partial | Missing | Partial | Partial | Blocked from Supported until source, freshness, fallback, and contract evidence are complete. |
| Threshold experimentation tooling | EXPERIMENTAL | Partial | Missing | Not Applicable | Partial | Blocked from Supported until experiment ownership, limits, tests, and retention rules are complete. |
| Metadata-less fatigue array response | LEGACY | Partial | Missing | Missing | Partial | Not ready for Deprecated until consumers and migration path are documented. |
| Standalone fatigue recalculation script | LEGACY | Partial | Missing | Not Applicable | Partial | Not ready for Deprecated until replacement, runbook, and migration evidence are documented. |

## Owner Assignment Matrix

| Surface | Maintainer Of Record | Owning Area | Evidence Collection Owner | Immediate Owner Action |
|---------|----------------------|-------------|---------------------------|------------------------|
| Dashboard | Nikko | Frontend product surface | Frontend governance | Maintain production scope record. |
| Bullpen | Nikko | Frontend product surface | Frontend governance | Maintain production scope record. |
| V2 bullpen-state API | Nikko | Recommendation governance | Backend governance | Preserve certification boundary evidence. |
| V2 Bullpen State panel | Nikko | Recommendation governance | Frontend governance | Preserve certification boundary evidence. |
| V1 candidate API and panel | Nikko | Recommendation governance | Backend and frontend governance | Preserve candidate-level limitation evidence. |
| Bullpen fatigue APIs | Nikko | Availability and fatigue data | Backend governance | Inventory consumer and contract retirement evidence. |
| Bullpen read APIs | Nikko | Baseball data access | Backend governance | Inventory consumer and contract replacement evidence. |
| Methodology | Nikko | Product documentation | Documentation governance | Backfill maintenance and review cadence evidence. |
| Admin sync and recalculation | Nikko | Operations tooling | Backend operations governance | Backfill operational runbook evidence. |
| Frontend API normalizers | Nikko | Frontend shared client | Frontend governance | Backfill owner and contract evidence. |
| Availability governance reports and scripts | Nikko | Governance tooling | Documentation and backend governance | Backfill report runbook and retention evidence. |
| Prospect Pipeline UI | Nikko | Prospect prototype | Frontend governance | Backfill purpose, owner, limitation, and maintenance evidence. |
| Prospect APIs | Nikko | Prospect prototype | Backend governance | Backfill contract, owner, maintenance, and test evidence. |
| Dashboard Pipeline Snapshot | Nikko | Prospect prototype | Frontend governance | Backfill snapshot purpose, freshness, and limitation evidence. |
| Fatigue-to-ERA insight | Nikko | Experimental fatigue insight | Governance review | Backfill metadata, limitation, and test evidence. |
| Latest-workload snapshot mode | Nikko | Experimental workload snapshot | Backend governance | Backfill freshness and fail-closed evidence. |
| MLB passthrough helpers | Nikko | Experimental data access helper | Backend governance | Backfill source, freshness, and fallback evidence. |
| Threshold experimentation tooling | Nikko | Experimental tuning tool | Governance review | Backfill experiment limits and retention evidence. |
| Metadata-less fatigue array response | Nikko | Legacy fatigue contract | Backend governance | Backfill consumer inventory and migration evidence. |
| Standalone fatigue recalculation script | Nikko | Legacy operations script | Backend operations governance | Backfill replacement and retirement runbook evidence. |

## Promotion-Readiness Evidence Matrix

| Surface | Requested Upward Movement | Owner Complete | Runbook Complete | Metadata Complete | Test Evidence Complete | Governance Complete | Promotion Readiness |
|---------|---------------------------|----------------|------------------|-------------------|------------------------|--------------------|--------------------|
| Prospect Pipeline UI | Prototype -> Experimental | No | No | No | No | No | Fails. |
| Prospect APIs | Prototype -> Experimental | No | No | No | No | No | Fails. |
| Dashboard Pipeline Snapshot | Prototype -> Experimental | No | No | No | No | No | Fails. |
| Fatigue-to-ERA insight | Experimental -> Supported | No | No | No | No | No | Fails. |
| Latest-workload snapshot mode | Experimental -> Supported | No | No | No | No | No | Fails. |
| MLB passthrough helpers | Experimental -> Supported | No | No | No | No | No | Fails. |
| Threshold experimentation tooling | Experimental -> Supported | No | No | Not Applicable | No | No | Fails. |

No prototype or experimental surface currently has the complete evidence
package required for upward lifecycle movement.

## Certified V2 Governance Confirmation

Certified Recommendation Engine V2 governance remains unchanged:

```text
ranking_applied === false
selection_made === false
```

Phase 23 confirms:

- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best option behavior exists
- no preferred option behavior exists
- no recommended option behavior exists
- no new Recommendation Engine API exposure is authorized
- no fatigue formula change is authorized
- no API contract change is authorized
- no frontend runtime behavior change is authorized
- no certified production behavior change is authorized

## Risk Assessment

Remaining risks are evidence and process risks:

- prototype surfaces still require complete owner, purpose, maintenance,
  limitation, and test evidence
- experimental intelligence surfaces still require trust, freshness, refusal,
  fail-closed, limitation, and anti-ranking / anti-selection / anti-prediction
  evidence
- legacy surfaces still require consumer inventory and migration evidence
- supported operational and governance tooling still needs stronger runbook and
  evidence retention records before promotion
- future lifecycle reviews must attach Phase 23 evidence status instead of only
  citing policy or checklist documents

These risks do not change certified V2 production behavior.

## Explicit Promotion Readiness Statement

No prototype or experimental BaseballOS surface is currently promotion-ready.

Every current prototype or experimental surface has at least one missing or
partial owner, runbook, metadata, test, governance, limitation, certification,
or evidence-retention requirement. Upward lifecycle movement remains blocked
until the required evidence package is complete and reviewed.

## Recommended Evidence Acquisition Priorities

Priority 1:

- backfill owner and purpose evidence for Prospect Pipeline UI, Prospect APIs,
  and Dashboard Pipeline Snapshot
- backfill runbook and limitation evidence for all prototype surfaces
- backfill metadata and freshness evidence for prototype surfaces that display
  data snapshots

Priority 2:

- backfill trust, freshness, refusal, fail-closed, limitation, and test evidence
  for Fatigue-to-ERA insight, latest-workload snapshot mode, and MLB passthrough
  helpers
- backfill experiment limits, retention expectations, and test evidence for
  threshold experimentation tooling

Priority 3:

- inventory consumers of the metadata-less fatigue array response
- document migration path and replacement evidence for legacy fatigue surfaces
- document replacement and retirement runbook evidence for the standalone
  fatigue recalculation script

Priority 4:

- strengthen runbook and evidence retention records for supported methodology,
  admin sync, frontend normalizers, and governance reports/scripts
- prepare lifecycle review packets only after evidence gaps are closed

## Validation

Validation performed for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-phase-23-evidence-backfill
Result: 278 passed, 0 failed.

cd frontend
npm test
Result: 78 passed, 0 failed.

git diff --check
Result: Passed; reported only LF-to-CRLF warnings, including known unrelated
frontend generated/dependency drift.

git diff --cached --check
Result: Passed after targeted documentation staging.
```

Root `npm test` is not required for Phase 23. No root `package.json` exists,
which is expected and is not a project failure.

## Recommended Next Milestone

Completed follow-up layer:

```text
BaseballOS V2.5 Phase 24 Lifecycle Evidence Packet Template and Initial Backfill
```

Phase 24 converts the Phase 23 framework into the standard lifecycle evidence
packet template and creates first-generation packet stubs for selected
production, prototype, experimental, and legacy surfaces.

Recommended next milestone:

```text
BaseballOS V2.5 Phase 25 Lifecycle Evidence Packet Review and Backfill Execution
```

Phase 25 should review the Phase 24 packet stubs, add precise evidence
citations where existing records already satisfy packet sections, and begin the
first evidence backfill pass for high-priority prototype and experimental
surfaces without changing runtime behavior.
