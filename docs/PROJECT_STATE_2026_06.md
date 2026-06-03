# Project State: June 2026

## Executive Summary

BaseballOS has completed the Availability Engine trust foundation and
Recommendation Engine V1. The platform now moves beyond a fatigue dashboard
into explainable bullpen availability intelligence and certified
candidate-level decision support while preserving clear limits around what
public workload data can and cannot prove.

The current product identity is:

```text
BaseballOS: trust-first bullpen intelligence for workload, availability, and
freshness-aware decision support.
```

The repository remains `bullpen-intel-engine`. Repository structures, package
names, imports, and deployment configuration should not be renamed solely for
branding.

## Completed Foundations

### Bullpen Intelligence

BaseballOS ingests MLB Stats API rosters and pitching game logs, computes
fatigue scores, and exposes team, pitcher, and dashboard workload views.

### Fatigue Engine

The Fatigue Engine remains the deterministic workload base. It produces a
transparent 0-100 workload score from pitch-count load, rest days, appearance
frequency, and innings load.

### Availability Engine V1

Availability Engine V1 is implemented. It translates fatigue, rest, recent
workload, appearance compression, and data state into:

- `Available`
- `Monitor`
- `Limited`
- `Avoid`
- `Unavailable`

The classifier is centralized in the backend availability service and is not
embedded directly in routes. API responses remain backward-compatible by adding
availability objects rather than replacing fatigue fields.

### Explainability

Availability output includes:

- status
- confidence
- data state
- reasons
- limitations
- deterministic inputs

Every non-Available classification must expose reasons. Missing, stale, or
incomplete data must lower confidence, alter display, or make limitations
visible.

### Dashboard Integration

The dashboard now includes:

- current-mode availability summary
- status distribution
- confidence distribution
- data-state distribution
- stale/missing-data trust notes
- dashboard trust strip for data status, sync date, data-through date, and
  refresh coverage

### Status Reachability

Frontend fixture coverage verifies that all five availability statuses render
correctly even when the current local dataset does not naturally contain all
statuses at once. Fixture validation is for UI correctness only, not threshold
validation.

### Governance Framework

Availability threshold governance is implemented through:

- repeatable threshold audit tooling
- latest-workload snapshot validation mode
- explanation quality audit
- threshold tuning plan
- boundary review process
- adoption records
- readiness certification reports

Threshold changes must be evidence-based, single-variable where possible, and
reviewed before adoption.

### Recommendation Engine V1

Recommendation Engine V1 is complete, certified, and production-ready for
candidate-level evaluation. It translates trusted availability, confidence,
freshness, explanation, limitation, and refusal evidence into structured
candidate-level recommendation or refusal output.

The certified V1 system includes:

- backend recommendation foundation contracts and schemas
- eligibility and exclusion gates
- category eligibility assignment
- response builder/composer
- candidate-level engine integration
- candidate API route
- frontend recommendation API client
- Recommendation Panel UI
- controlled success, caution, refusal, loading, error, and empty states
- pitcher detail dashboard integration
- UI polish and regression certification

Recommendation Engine V1 remains bounded to one pitcher candidate at a time.
It does not rank the bullpen or select the final pitcher.

## Current Capabilities

| Capability | Status |
| --- | --- |
| Bullpen Intelligence | ✓ Complete |
| Fatigue Engine | ✓ Complete |
| Availability Engine | ✓ Complete |
| Explainability | ✓ Complete |
| Trust Layer | ✓ Complete |
| Freshness Transparency | ✓ Complete |
| Governance Framework | ✓ Complete |
| Recommendation Engine V1 | ✓ Complete / Certified / Production Ready |
| Recommendation Engine V1 Candidate Evaluation Layout Remediation | Complete |
| Dashboard and Bullpen Loading Performance Remediation | Complete |
| Recommendation Engine V2 Strategy | Scope Definition Active |
| Recommendation Engine V2 Governance Boundaries | Documented |
| Recommendation Engine V2 Architecture | Documented |
| Recommendation Engine V2 API Contract | Documented |
| Recommendation Engine V2 Frontend Contract | Documented |
| Recommendation Engine V2 Certification Requirements | Documented |
| Recommendation Engine V2 Implementation Readiness Review | Complete |
| Recommendation Engine V2 Implementation Plan | Complete |
| Recommendation Engine V2 Phase 1 Domain Foundation | Complete |
| Recommendation Engine V2 Phase 2 Context Assembly | Complete |
| Recommendation Engine V2 Phase 3 Neutral Intelligence | Complete |
| Recommendation Engine V2 Phase 4 Inventory Visibility | Complete |
| Recommendation Engine V2 Phase 5 Team Bullpen Context | Complete |
| Recommendation Engine V2 Phase 6 Trust Metadata Integration | Complete |
| Recommendation Engine V2 Phase 7 Refusal Fail-Closed Integration | Complete |
| Recommendation Engine V2 Phase 8 API Contract Exposure | Complete |
| Recommendation Engine V2 Phase 9 Frontend Client Integration | Complete |
| Recommendation Engine V2 Phase 10 Governed Frontend Rendering | Complete |
| Recommendation Engine V2 Phase 10A Desktop Layout Remediation | Complete |
| Recommendation Engine V2 Phase 10B Bullpen Selected Pitcher Layout Remediation | Complete |
| Recommendation Engine V2 Phase 11 Mobile Accessibility Validation | Complete |
| Recommendation Engine V2 Phase 12 Certification Readiness Validation | Ready for Formal Certification Review |
| Recommendation Engine V2 Phase 13 Formal Certification Review | Certified / Production Ready |
| BaseballOS V2.5 Phase 14 Inventory Presentation Optimization | Complete |
| BaseballOS V2.5 Phase 15 Intelligence Presentation Optimization | Complete |
| BaseballOS V2.5 Phase 16 Production Rollout Decision | Approved for Production Rollout |
| BaseballOS V2.5 Phase 17 Post-Rollout Monitoring and Boundary Review | Complete |
| BaseballOS V2.5 Phase 18 Maintenance Warning Remediation Review | Complete |
| BaseballOS V2.5 Phase 19 Prototype Surface Maintenance Review | Complete |
| BaseballOS V2.5 Phase 20 Prototype Promotion and Deprecation Policy | Complete |
| BaseballOS V2.5 Phase 21 Lifecycle Enforcement Checklist | Complete |
| BaseballOS V2.5 Phase 22 Lifecycle Review Log and Adoption Audit | Complete |
| BaseballOS V2.5 Phase 23 Lifecycle Evidence Backfill and Owner Assignment Plan | Complete |
| BaseballOS V2.5 Phase 24 Lifecycle Evidence Packet Template and Initial Backfill | Complete |
| BaseballOS V2.5 Phase 25 Lifecycle Evidence Packet Review and Backfill Execution | Complete |
| Prospect Pipeline | Prototype |

## Trust & Governance Status

Trust-first rules currently in force:

- No black-box availability labels.
- Every status must expose reasons when workload or data-state constraints are
  present.
- Stale data must not be presented as current availability.
- Missing data must reduce confidence or alter display.
- `Unavailable` means workload-unavailable from public data, not injured,
  medically unavailable, or team-reported unavailable.
- Recommendation wording must not imply private clubhouse, medical, travel, or
  manager-intent knowledge.
- Recommendation Engine V1 must preserve candidate-level evaluation only.
- Recommendation Engine V1 must preserve `ranking_applied=false` and
  `selection_made=false`.
- Recommendation Engine V1 must keep confidence, freshness, explanations,
  limitations, and refusal reasons visible.
- Threshold changes require audit evidence and before/after comparison.

The first governed threshold adoption is complete:

```text
Unavailable 3-day pitch threshold: 80 -> 90
```

This adoption allows 80-89 pitches in three days to classify as `Avoid` unless
another Unavailable rule fires. 90+ pitches in three days remains
`Unavailable`.

Reference artifacts:

- `docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md`
- `backend/reports/availability_threshold_adoption_candidate_c.md`
- `backend/reports/availability_unavailable_boundary_review.md`
- `backend/reports/availability_post_adoption_readiness_certification.md`

## Freshness & Sync Status

Durable sync metadata is implemented through the `sync_runs` persistence model.
The backend can separately expose:

- last sync attempt
- last successful sync
- latest baseball game-log date
- latest workload date
- latest fatigue calculation timestamp
- sync status
- freshness limitations

The dashboard distinguishes:

```text
Synced:
June 1, 2026

Data Through:
May 31, 2026
```

This distinction matters because a sync timestamp is operational metadata, while
data-through date is baseball data coverage. BaseballOS should never substitute
one for the other.

If sync metadata is unavailable but data exists, the dashboard should say so and
still show the data-through date. If the latest sync fails, the dashboard should
preserve the latest known data-through date and disclose the failed sync state.

Reference artifacts:

- `backend/reports/durable_sync_metadata_implementation.md`
- `backend/reports/durable_sync_metadata_deployment_certification.md`
- `frontend/docs/dashboard_trust_strip_polish.md`

## Availability Engine Status

Availability Engine V1 is complete as a deterministic, explainable
classification framework. Current public UI surfaces consume backend output
instead of recreating classification logic in the browser.

Implemented public-facing surfaces:

- bullpen row availability badges
- availability filter
- pitcher detail availability summary
- dashboard availability summary
- dashboard data trust strip

Implemented validation/governance surfaces:

- frontend fixtures for all five statuses
- backend status tests
- stale and missing data tests
- threshold audit
- snapshot validation
- explanation audit
- boundary review tooling
- adoption reports

The Availability Engine remains bounded by public workload data. It does not
claim team-reported availability, injury status, warm-up activity, travel
status, or manager intent.

## Known Limitations

- No injury, transaction/news, or team-reported availability feed is integrated.
- No private clubhouse, medical, travel, or manager-intent data is available.
- No Statcast, Hawk-Eye biomechanics, Stuff+, or pitch-quality modeling is used.
- Role-aware starter/reliever handling remains limited.
- Warm-up workload and bullpen phone activity are not modeled.
- Prospect Pipeline remains a prototype with sample data, not a live
  minor-league data product.
- Recommendation Engine V1 is complete, certified, and production-ready for
  candidate-level evaluation only. Bullpen ranking, pitcher ordering, final
  pitcher selection, performance forecasting, injury prediction, save
  prediction, matchup guidance, and black-box or generated baseball opinions
  remain outside V1. V2 now has backend-only Phase 1 domain objects, Phase 2
  context assembly, Phase 3 neutral internal intelligence, and Phase 4
  inventory visibility, Phase 5 team bullpen context, Phase 6 trust metadata
  integration, Phase 7 refusal/fail-closed integration, and Phase 8 backend
  API contract exposure for grouped bullpen and team-level visibility without
  ranking or automated selection.
- Latest-workload snapshot mode is validation/admin only and must not be treated
  as current availability.

## Recommendation Engine V1 Completion Status

The completed major initiative is:

```text
Recommendation Engine V1
```

Status:

```text
Completed
Certified
Production Ready
```

Mission achieved:

```text
Move BaseballOS from availability intelligence to decision-support intelligence.
```

Recommendation Engine V1 is certified for:

- fail-closed behavior
- candidate-level evaluation
- trust visibility
- freshness visibility
- confidence visibility
- explanation visibility
- limitation visibility
- refusal visibility

The official completion certification is:

- `docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md`

Supporting governance documents:

- `docs/RECOMMENDATION_ENGINE_V1_POLICY.md`
- `docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md`
- `docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md`
- `docs/RECOMMENDATION_ENGINE_V1_FRONTEND_CONTRACT.md`
- `docs/RECOMMENDATION_ENGINE_V1_UI_IMPLEMENTATION_PLAN.md`
- `docs/RECOMMENDATION_ENGINE_V1_DASHBOARD_INTEGRATION_PLAN.md`

The implemented candidate-level route evaluates one candidate at a time. The
frontend API client calls that route for one-candidate evaluation only. The
selected-pitcher detail workflow builds one candidate payload from existing
pitcher detail, availability, and workload fields and displays the controlled
Recommendation Panel response after a user-triggered evaluation.

The certified display keeps confidence, data freshness, availability,
explanations, limitations, category eligibility, refusal reasons,
`ranking_applied=false`, and `selection_made=false` visible. The integration
does not perform ranking, scoring, bullpen comparison, route navigation, or
final pitcher selection.

## Recommendation Engine V2 Strategy and Phase 13 Status

Recommendation Engine V2 has completed strategy, governance boundaries,
architecture, contracts, certification planning, implementation readiness,
implementation planning, Phase 1 backend domain object foundation work, Phase
2 backend context assembly work, Phase 3 backend-only neutral intelligence
expansion work, Phase 4 backend-only inventory visibility work, and Phase 5
backend-only team bullpen context work, Phase 6 backend-only trust metadata
integration work, and Phase 7 backend-only refusal/fail-closed integration
work, Phase 8 backend-only API contract exposure work, Phase 9 frontend
client integration work, Phase 10 governed frontend rendering work, and Phase
10A desktop layout remediation work, and Phase 10B Bullpen selected-pitcher
layout remediation work, and Phase 11 mobile/accessibility validation work,
Phase 12 certification readiness validation work, and Phase 13 formal
certification review work. BaseballOS V2.5 Phase 14 inventory presentation
optimization and V2.5 Phase 15 intelligence presentation optimization are also
complete as post-certification usability milestones. BaseballOS V2.5 Phase 16
production rollout decision is complete and approves the current certified V2
Dashboard experience for production rollout within the implemented scope only.
BaseballOS V2.5 Phase 17 post-rollout monitoring and boundary review is also
complete and preserves the approved V2 production boundary. BaseballOS V2.5
Phase 18 maintenance warning remediation review is complete and removes the
current backend validation warning debt without changing certified
Recommendation Engine behavior. BaseballOS V2.5 Phase 19 prototype surface
maintenance review is complete and classifies production, supported,
prototype, experimental, legacy, and deprecated surfaces without expanding
Recommendation Engine behavior. BaseballOS V2.5 Phase 20 prototype promotion
and deprecation policy is complete and defines the official lifecycle gates
for promotion, support, production approval, legacy classification,
deprecation, removal, and intelligence-surface governance. BaseballOS V2.5
Phase 21 lifecycle enforcement checklist is complete and converts those gates
into operational pass/fail checklists for lifecycle movement, production
eligibility, deprecation, removal, and future intelligence-surface review.
BaseballOS V2.5 Phase 22 lifecycle review log and adoption audit is complete
and adds the auditable record layer for checklist usage, evidence requirements,
surface-by-surface readiness findings, and remaining adoption risks.
BaseballOS V2.5 Phase 23 lifecycle evidence backfill and owner assignment plan
is complete and converts those adoption findings into a structured owner,
runbook, metadata, test, governance, certification, and migration-evidence
framework before any future lifecycle movement.
BaseballOS V2.5 Phase 24 lifecycle evidence packet template and initial
backfill is complete and introduces standardized evidence packets plus initial
packet stubs for selected production, prototype, experimental, and legacy
surfaces.
BaseballOS V2.5 Phase 25 lifecycle evidence packet review and backfill
execution is complete and performs the first formal packet review, evidence
readiness scoring, readiness classification, and known-evidence backfill pass
across governed packet stubs.

The official strategy foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`

The governance-boundary decision filter is:

- `docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`

The architecture foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`

The API contract foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`

The frontend contract foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md`

The certification requirements foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`

The implementation-readiness review is:

- `docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_READINESS_REVIEW.md`

The implementation plan is:

- `docs/RECOMMENDATION_ENGINE_V2_IMPLEMENTATION_PLAN.md`

The Phase 1 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_1_DOMAIN_FOUNDATION.md`

The Phase 2 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_2_CONTEXT_ASSEMBLY.md`

The Phase 3 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_3_NEUTRAL_INTELLIGENCE.md`

The Phase 4 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_4_INVENTORY_VISIBILITY.md`

The Phase 5 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_5_TEAM_BULLPEN_CONTEXT.md`

The Phase 6 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_6_TRUST_METADATA_INTEGRATION.md`

The Phase 7 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_7_REFUSAL_FAIL_CLOSED.md`

The Phase 8 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_8_API_CONTRACT_EXPOSURE.md`

The Phase 9 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md`

The Phase 10 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md`

The Phase 10A completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md`

The Phase 10B completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md`

The Phase 11 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_11_MOBILE_ACCESSIBILITY.md`

The Phase 12 certification readiness record is:

- `docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md`

The Phase 13 formal certification record is:

- `docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md`

The V2.5 Phase 14 inventory presentation optimization record is:

- `docs/V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md`

The V2.5 Phase 15 intelligence presentation optimization record is:

- `docs/V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md`

The Dashboard V2 collapsible remediation record is:

- `docs/V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md`

The V2.5 Phase 16 production rollout decision record is:

- `docs/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md`

The V2.5 Phase 17 post-rollout monitoring and boundary review record is:

- `docs/V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md`

The V2.5 Phase 18 maintenance warning remediation review record is:

- `docs/V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md`

The V2.5 Phase 19 prototype surface maintenance review record is:

- `docs/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md`

The V2.5 Phase 20 prototype promotion and deprecation policy record is:

- `docs/V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md`

The V2.5 Phase 21 lifecycle enforcement checklist record is:

- `docs/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md`

The V2.5 Phase 22 lifecycle review log and adoption audit record is:

- `docs/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md`

The V2.5 Phase 23 lifecycle evidence backfill and owner assignment plan is:

- `docs/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md`

The V2.5 Phase 24 lifecycle evidence packet template and initial backfill
record is:

- `docs/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md`

The V2.5 Phase 25 lifecycle evidence packet review and backfill execution
record is:

- `docs/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md`

V2 planning may explore bullpen-level intelligence, bullpen inventory
visibility, bullpen stress awareness, leverage resource visibility, workload
distribution visibility, grouped eligibility reporting, bullpen readiness
reporting, and broader recommendation explainability.

This milestone does not authorize pitcher rankings, pitcher ordering,
automated pitcher selection, game outcome prediction, injury prediction, save
prediction, performance forecasting, opaque recommendation scores, unsupported
baseball opinions, additional Recommendation Engine API exposure, frontend
rendering behavior changes, or new recommendation logic.

The governance-boundary milestone documents allowed, restricted, and forbidden
V2 behaviors; preserves the active `ranking_applied=false` and
`selection_made=false` trust guarantees; and requires documented architecture,
API contract, frontend contract, certification criteria, and explicit user
approval before implementation may begin.

The architecture milestone defines the proposed V2 object model, service flow,
metadata model, fail-closed path, API and frontend architecture concepts,
governance enforcement points, testing architecture, certification
architecture, and implementation-readiness criteria. It does not authorize
backend, frontend, API, or Recommendation Engine V1 behavior changes.

The API contract milestone defines the proposed V2 response shape, provisional
bullpen-state endpoint scope, required trust metadata, response objects,
anti-ranking rules, success and refusal examples, testing requirements,
certification requirements, and implementation gate. The contract itself did
not implement or modify endpoints; the separately completed Phase 8 milestone
implemented the approved endpoint.

The frontend contract milestone defines future V2 display rules for allowed,
restricted, and forbidden UI patterns; candidate groups, inventory, bullpen
state, team context, trust metadata, freshness, limitations, refusal states,
mobile rendering, accessibility language, visual hierarchy, testing, and
certification. It does not create or modify frontend components.

The certification requirements milestone defines the evidence standards,
trust guarantees, explainability guarantees, freshness guarantees, fail-closed
guarantees, backend/API/frontend/mobile/accessibility certification
requirements, refusal-state requirements, anti-ranking and anti-selection
audits, documentation requirements, test categories, production-readiness
requirements, certification failure conditions, implementation admission gate,
and final approval requirements. It does not authorize implementation.

The implementation-readiness review evaluates the complete V2 planning package
and finds no remaining governance blockers. The final readiness determination
is `READY_FOR_IMPLEMENTATION`. The review does not implement or certify
runtime behavior.

The implementation plan converts the approved V2 governance package into a
phased roadmap covering repo hygiene, backend domain objects, bullpen state,
candidate grouping, inventory visibility, team bullpen context, trust metadata,
refusal and fail-closed behavior, API implementation, frontend integration,
mobile/accessibility validation, test expansion, certification review, and
production rollout decision. It remains the sequencing authority for future
phases after Phase 10B.

Recommendation Engine V2 Phase 1 implements backend-only domain objects:

- `RecommendationContext`
- `BullpenState`
- `CandidateGroup`
- `TeamBullpenContext`

The Phase 1 foundation represents trust, freshness, limitation, explanation,
refusal, bullpen inventory, readiness, workload, stress, neutral candidate
group, and team bullpen context metadata. It does not expose V2 API support,
frontend support, runtime bullpen-state calculation, candidate grouping logic,
ranking, selection, prediction, or user-visible behavior.

Recommendation Engine V2 Phase 2 implements backend-only context assembly:

- `assemble_v2_context`
- `V2ContextAssembly`

The Phase 2 assembler maps existing availability, workload, freshness,
limitation, explanation, and refusal evidence into `RecommendationContext`,
`BullpenState`, `TeamBullpenContext`, and neutral `CandidateGroup` collections.
It can summarize bullpen inventory, readiness distribution, workload evidence,
stress indicators, and leverage evidence availability. It fails closed when
required evidence is missing or source evidence includes forbidden ranking or
selection fields.

The Phase 2 assembler does not expose V2 API support, frontend support,
user-facing V2 recommendation behavior, ranking, selection, prediction, or
route changes.

Recommendation Engine V2 Phase 3 expands backend-only neutral intelligence:

- eligibility distribution
- refusal distribution
- freshness distribution
- readiness distribution
- workload distribution
- neutral candidate groups across availability, eligibility, refusal,
  freshness, readiness, and workload categories

The Phase 3 expansion preserves source input order inside groups, documents
category ordering as a static taxonomy, propagates trust/freshness/refusal and
explanation support, and fails closed when evidence is missing or unsafe.

The Phase 3 expansion does not expose V2 API support, frontend support,
user-facing V2 recommendation behavior, ranking, selection, prediction, or
route changes.

Recommendation Engine V2 Phase 4 expands backend-only inventory visibility:

- availability inventory
- eligibility inventory
- refusal inventory
- freshness inventory
- readiness inventory
- workload inventory
- evidence inventory
- limitation inventory
- explanation inventory
- trust metadata

The Phase 4 expansion preserves source input order inside inventory
categories, exposes deterministic counts and member references, propagates
trust/freshness/refusal/limitation/explanation metadata, and fails closed when
evidence is missing or unsafe.

The Phase 4 expansion does not expose V2 API support, frontend support,
user-facing V2 inventory UI, user-facing V2 recommendation behavior, ranking,
selection, prediction, or route changes.

Recommendation Engine V2 Phase 5 expands backend-only team bullpen context:

- team bullpen status
- team availability distribution
- team eligibility distribution
- team refusal distribution
- team freshness and data-state distribution
- team readiness distribution
- team workload distribution
- team limitation context
- team explanation context
- team trust metadata

The Phase 5 expansion preserves source input order in team member references,
uses the existing Phase 4 inventory visibility layer as source evidence,
propagates trust/freshness/refusal/limitation/explanation metadata, and fails
closed when evidence is missing or unsafe.

The Phase 5 expansion does not expose V2 API support, frontend support,
user-facing V2 team context UI, user-facing V2 recommendation behavior,
ranking, selection, prediction, or route changes.

Recommendation Engine V2 Phase 6 enforces backend-only trust metadata
integration:

- confidence metadata
- freshness metadata
- limitation metadata
- explanation metadata
- refusal metadata
- data-state metadata
- source evidence state
- governance state
- no-ranking and no-selection governance metadata

The Phase 6 expansion adds mandatory trust metadata validation across
`RecommendationContext`, `BullpenState`, `CandidateGroup`,
`TeamBullpenContext`, `V2ContextAssembly`, neutral intelligence summaries,
inventory visibility summaries, and team bullpen context summaries. Missing or
unsupported trust metadata now produces explicit fail-closed/refusal metadata
instead of silently passing incomplete context.

The Phase 6 expansion does not expose V2 API support, frontend support,
user-facing V2 trust UI, user-facing V2 recommendation behavior, ranking,
selection, prediction, or route changes.

Recommendation Engine V2 Phase 7 expands backend-only refusal and fail-closed
integration:

- Phase 7 refusal/fail-closed summary
- deterministic degraded-output state
- missing evidence handling
- incomplete evidence handling
- stale evidence handling
- unsupported evidence handling
- malformed evidence handling
- unsafe ranking source-field handling
- unsafe selection source-field handling
- unsafe prediction source-field handling

The Phase 7 expansion adds explicit internal `refusal_fail_closed` metadata to
context assembly, neutral intelligence, inventory visibility, and team bullpen
context summaries. It distinguishes passed, degraded, and failed-closed states,
suppresses candidate output for malformed or unsupported source-shape evidence,
and preserves trust/freshness/refusal/limitation/explanation metadata.

The Phase 7 expansion does not expose V2 API support, frontend support,
user-facing V2 refusal UI, user-facing V2 recommendation behavior, ranking,
selection, prediction, or route changes.

Recommendation Engine V2 Phase 8 exposes the approved backend API contract:

```text
GET /api/recommendations/v2/bullpen-state
```

The Phase 8 endpoint returns V2 bullpen-state contract output with:

- top-level no-ranking and no-selection metadata
- trust metadata
- freshness metadata
- limitations
- explanations
- refusal reasons
- fail-closed metadata
- descriptive bullpen state when evidence is safe
- neutral candidate groups when grouping is safe
- inventory summaries
- team bullpen context

The Phase 8 endpoint fails closed or degrades explicitly when evidence is
missing, stale, incomplete, unsupported, malformed, or governance-unsafe.

The Phase 8 expansion does not expose frontend support, user-facing V2 UI,
ranking, selection, prediction, or changes to Recommendation Engine V1.

Recommendation Engine V2 Phase 9 adds frontend client integration for the
approved V2 endpoint:

```text
GET /api/recommendations/v2/bullpen-state
```

The Phase 9 client integration is implemented in:

- `frontend/src/utils/api.js`

The client consumes the endpoint and normalizes V2 responses into explicit
contract states:

- `available`
- `fail_closed`
- `unavailable`

The client preserves trust metadata, freshness metadata, limitation metadata,
explanation metadata, refusal metadata, and no-ranking/no-selection governance
flags. Missing, malformed, governance-unsafe, or forbidden
ranking/selection/prediction fields are represented as unavailable instead of
being treated as valid future UI state.

The Phase 9 expansion does not expose user-facing V2 UI, ranking UI, selection
UI, prediction UI, new V2 routes, backend V2 behavior changes, or changes to
Recommendation Engine V1.

Recommendation Engine V2 Phase 10 adds governed dashboard rendering for the
normalized V2 frontend client output.

The Phase 10 rendering paths are:

- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/src/components/recommendations/index.js`

The Phase 10 panel renders:

- bullpen state
- trust metadata
- freshness metadata
- governance metadata
- inventory visibility
- team context
- neutral candidate groups
- limitations
- explanations
- refusal metadata
- fail-closed state
- unavailable contract state

The panel renders fail-closed and unavailable states explicitly. When the
client reports unavailable contract state, the panel withholds bullpen-state
details and avoids rendering unsafe candidate, inventory, or team-context
output.

The Phase 10 expansion does not introduce ranking UI, selection UI, prediction
UI, best/preferred/recommended pitcher UI, backend V2 behavior changes, new
backend routes, or changes to Recommendation Engine V1.

Recommendation Engine V2 Phase 10A remediates the desktop layout defect in the
governed Phase 10 panel.

The Phase 10A remediation updates:

- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
- `frontend/src/index.css`
- `frontend/tests/recommendationV2Rendering.test.mjs`

The panel now uses container-aware internal grids so trust, freshness,
inventory, team-context, limitation, explanation, refusal, fail-closed, and
neutral-group sections remain readable when rendered inside desktop layouts
with constrained panel width.

The Phase 10A remediation does not introduce ranking UI, selection UI,
prediction UI, best/preferred/recommended pitcher UI, backend V2 behavior
changes, new backend routes, or changes to Recommendation Engine V1.

Recommendation Engine V2 Phase 10B remediates the Bullpen selected-pitcher
detail layout.

The Phase 10B remediation updates:

- `frontend/src/components/bullpen/Bullpen.jsx`
- `frontend/src/components/bullpen/PitcherDetail.jsx`
- `frontend/src/components/recommendations/RecommendationPitcherDetailSection.jsx`
- `frontend/src/components/recommendations/RecommendationPanel.jsx`
- `frontend/src/index.css`
- `frontend/tests/recommendationPitcherDetailSection.test.mjs`

The Bullpen selected-pitcher layout now avoids the cramped fixed desktop split
that squeezed the detail card and recommendation trust surface on common
desktop widths. The selected-pitcher detail surface remains full width in
constrained desktop layouts and becomes a readable fixed-width rail only on
wider desktop screens.

The embedded recommendation detail surface now uses container-aware internal
grids and text wrapping safeguards so trust, freshness, refusal, explanation,
limitation, and metadata sections remain readable inside the selected-pitcher
detail card.

The Phase 10B remediation does not introduce ranking UI, selection UI,
prediction UI, best/preferred/recommended pitcher UI, backend V2 behavior
changes, new backend routes, or changes to Recommendation Engine V1.

Recommendation Engine V1 Candidate Evaluation Layout Remediation fixes the
embedded Candidate Evaluation article rendered inside the Bullpen
selected-pitcher detail surface.

The V1 layout remediation updates:

- `frontend/src/components/recommendations/RecommendationPanel.jsx`
- `frontend/src/index.css`
- `frontend/tests/recommendationPitcherDetailSection.test.mjs`

The embedded V1 Candidate Evaluation article now has an explicit embedded
layout path and remains single-column. Standalone Recommendation Engine V1
panels may still use the wider container-aware layout, but the embedded
selected-pitcher article no longer inherits the standalone two-column grid.

The V1 layout remediation preserves Recommendation Status, Trust And
Freshness, Eligible Categories, Blocked Categories, Explanation, Limitation,
Refusal Reason, and Metadata visibility.

The V1 layout remediation does not introduce ranking UI, selection UI,
prediction UI, best/preferred/recommended pitcher UI, backend behavior
changes, API changes, or Recommendation Engine V1 logic changes.

The active V1 and V2 governance guarantees remain:

```text
ranking_applied = false
selection_made = false
```

Dashboard and Bullpen Loading Performance Remediation improves the loading
paths that affected Dashboard and Bullpen perceived production quality before
Phase 11 mobile/accessibility validation.

The performance remediation updates:

- `backend/services/availability_snapshot.py`
- `backend/api/bullpen.py`
- `backend/api/recommendations.py`
- `backend/tests/test_availability_snapshot_mode.py`
- `backend/tests/test_recommendation_v2_api_contract.py`
- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/src/utils/api.js`
- `frontend/tests/recommendationV2Api.test.mjs`
- `frontend/tests/syncStatus.test.mjs`

The root cause was repeated per-pitcher availability evidence queries for
broad bullpen views, full internal V2 context serialization before public API
response shaping, and a duplicate Dashboard sync-status request.

The remediation batches availability evidence reads, uses lean public V2 API
serialization, reuses the Dashboard sync-status request for the trust strip,
and de-duplicates concurrent identical frontend GET requests.

Measured local endpoint averages improved from 470.4 ms to 42.5 ms for
Dashboard overview, 490.7 ms to 54.1 ms for stale-included Bullpen fatigue
data, and 1625.1 ms to 419.0 ms for V2 bullpen-state output.

The performance remediation does not change recommendation logic, fatigue
formulas, V1 behavior, V2 governance behavior, API route shape, ranking,
selection, prediction, or best/preferred/recommended pitcher behavior.

Recommendation Engine V2 Phase 11 Mobile Accessibility Validation validates
and improves the governed frontend surfaces after the Phase 10, Phase 10A,
Phase 10B, V1 Candidate Evaluation layout, and loading-performance
remediations.

The Phase 11 validation updates:

- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
- `frontend/src/components/recommendations/RecommendationPitcherDetailSection.jsx`
- `frontend/src/components/recommendations/RecommendationPanel.jsx`
- `frontend/src/components/bullpen/Bullpen.jsx`
- `frontend/src/components/bullpen/PitcherDetail.jsx`
- `frontend/src/components/UI/LoadingPane.jsx`
- `frontend/src/components/UI/ErrorState.jsx`
- `frontend/src/index.css`
- `frontend/tests/recommendationV2Rendering.test.mjs`
- `frontend/tests/recommendationPitcherDetailSection.test.mjs`

Phase 11 validates the Dashboard V2 panel, Bullpen selected-pitcher detail
surface, and embedded Recommendation Engine V1 Candidate Evaluation surface
at mobile and tablet widths. It adds or preserves explicit V2 section
headings, status and alert semantics, fail-closed announcements, visible
focus treatment, keyboard access to selected-pitcher detail, focus transfer
when the detail surface opens, and embedded V1 trust/freshness/refusal
metadata labeling.

The Phase 11 validation does not change recommendation logic, fatigue
formulas, backend behavior, API behavior, V1 behavior, V2 governance behavior,
ranking, selection, prediction, or best/preferred/recommended pitcher
behavior.

Recommendation Engine V2 Phase 12 Certification Readiness Validation compiles
backend, API, frontend, governed rendering, mobile, accessibility, trust,
freshness, refusal, fail-closed, and V1 regression evidence for the
implemented V2 system.

The Phase 12 readiness record is:

- `docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_READINESS_VALIDATION.md`

Phase 12 validation ran:

```text
npm test
```

Result:

```text
69 passed, 0 failed
```

Phase 12 validation also ran:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v2-certification
```

Result:

```text
278 passed, 0 failed
```

The Phase 12 readiness classification is:

```text
READY_FOR_CERTIFICATION_REVIEW
```

This means V2 is ready to enter formal certification review. It does not mean
V2 is production certified, does not approve production rollout, and does not
add product behavior.

Recommendation Engine V2 Phase 13 Formal Certification Review certifies the
implemented and governed V2 scope as production-ready.

The Phase 13 formal certification record is:

- `docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md`

Phase 13 validation ran:

```text
npm test
```

Result:

```text
69 passed, 0 failed
```

Phase 13 validation also ran:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v2-formal-certification
```

Result:

```text
278 passed, 0 failed
```

The Phase 13 formal certification decision is:

```text
CERTIFIED_PRODUCTION_READY
```

This certifies the implemented and governed V2 scope only. Production rollout
still requires a separate governed rollout decision.

BaseballOS V2.5 Phase 14 Inventory Presentation Optimization reduces the
Dashboard V2 inventory surface from full membership by default to
summary-first category cards with expansion on demand.

The Phase 14 inventory presentation record is:

- `docs/V25_PHASE_14_INVENTORY_PRESENTATION_OPTIMIZATION.md`

Phase 14 validation ran:

```text
npm test
```

Result:

```text
72 passed, 0 failed
```

Phase 14 did not touch backend files, API contracts, recommendation logic,
trust logic, freshness logic, refusal logic, ranking behavior, selection
behavior, prediction behavior, or Recommendation Engine V1 behavior.

BaseballOS V2.5 Phase 15 Intelligence Presentation Optimization audits the
full Dashboard V2 intelligence surface and reduces raw-structure exposure
beyond inventory. Candidate groups, team context distributions and indicators,
limitations, explanations, and refusal details now render summary-first by
default with full detail available through expansion.

The Phase 15 intelligence presentation record is:

- `docs/V25_PHASE_15_INTELLIGENCE_PRESENTATION_OPTIMIZATION.md`

A later Dashboard V2 production UX remediation corrects the live collapsible
implementation without creating a new roadmap phase. It adds nested
member/detail controls for inventory and candidate groups, structured Team
Context indicator summaries for live count-object payloads, and validation
that high-volume names and details remain hidden until explicit expansion.

The Dashboard V2 collapsible remediation record is:

- `docs/V25_DASHBOARD_INTELLIGENCE_COLLAPSIBLE_REMEDIATION.md`

Phase 15 validation ran:

```text
npm test
```

Result:

```text
77 passed, 0 failed
```

Phase 15 did not touch backend files, API contracts, recommendation logic,
trust logic, freshness logic, refusal logic, ranking behavior, selection
behavior, prediction behavior, or Recommendation Engine V1 behavior.

Dashboard V2 collapsible remediation validation ran:

```text
npm test
```

Result:

```text
78 passed, 0 failed
```

Backend tests were not required for the remediation because no backend files
were touched.

BaseballOS V2.5 Phase 16 Production Rollout Decision evaluates the certified
V2 system, current Dashboard and Bullpen surfaces, performance remediation,
mobile/accessibility evidence, Phase 14 inventory presentation optimization,
and Phase 15 intelligence presentation optimization.

The Phase 16 production rollout decision record is:

- `docs/V25_PHASE_16_PRODUCTION_ROLLOUT_DECISION.md`

The Phase 16 rollout decision is:

```text
APPROVED_FOR_PRODUCTION_ROLLOUT
```

Phase 16 validation ran:

```text
npm test
```

Result:

```text
77 passed, 0 failed
```

Phase 16 validation also ran:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-rollout-decision
```

Result:

```text
278 passed, 0 failed
```

The backend run reported 139 existing deprecation warnings from SQLAlchemy and
datetime usage. The warnings are maintenance follow-up items, not rollout
blockers for the current V2 scope.

Phase 16 did not touch backend files, frontend source files, API contracts,
recommendation logic, trust logic, freshness logic, refusal logic, ranking
behavior, selection behavior, prediction behavior, or Recommendation Engine V1
behavior.

BaseballOS V2.5 Phase 17 Post-Rollout Monitoring and Boundary Review evaluates
the approved V2 production boundary after rollout approval. It reviews
governance drift, contract drift, UX drift, warning classes, existing
regression protection, and future monitoring requirements.

The Phase 17 post-rollout monitoring and boundary review record is:

- `docs/V25_PHASE_17_POST_ROLLOUT_MONITORING_AND_BOUNDARY_REVIEW.md`

The Phase 17 boundary review decision is:

```text
BOUNDARY_REVIEW_PASSED
```

Phase 17 validation ran:

```text
npm test
```

Result:

```text
77 passed, 0 failed
```

Phase 17 validation also ran:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-post-rollout
```

Result:

```text
278 passed, 0 failed, 139 warnings
```

Phase 17 did not discover a regression-protection gap. Existing frontend and
backend tests already cover anti-ranking, anti-selection, anti-prediction,
trust metadata, freshness metadata, refusal metadata, fail-closed behavior,
collapsed/expanded V2 inventory and intelligence presentation, and prohibited
decision-language rendering.

The warning review classifies SQLAlchemy and datetime deprecation warnings as
maintenance items to monitor, not current V2 governance blockers. Local
pytest cache/temp permission warnings and frontend generated/dependency drift
remain unstaged local artifacts.

Phase 17 did not touch backend source files, frontend source files, API
contracts, recommendation logic, trust logic, freshness logic, refusal logic,
ranking behavior, selection behavior, prediction behavior, fatigue formulas,
or Recommendation Engine V1 behavior.

BaseballOS V2.5 Phase 18 Maintenance Warning Remediation Review evaluates the
backend warning debt surfaced during Phase 17 post-rollout validation. It
classifies datetime warnings, SQLAlchemy warnings, pytest temp/cache
permission warnings, prototype route scan findings, and unrelated
generated/dependency drift.

The Phase 18 maintenance warning remediation review record is:

- `docs/V25_PHASE_18_MAINTENANCE_WARNING_REMEDIATION_REVIEW.md`

Phase 18 validation ran before remediation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-warning-review
```

Initial result:

```text
278 passed, 0 failed, 139 warnings
```

Phase 18 applied safe warning remediation:

- replaced deprecated UTC timestamp acquisition with a naive UTC helper that
  preserves existing `DateTime` storage shape
- replaced backend test fixture `datetime.utcnow()` calls with the same helper
- replaced the observed bullpen detail route legacy query lookup with
  `db.session.get()` and explicit 404 behavior

Phase 18 validation ran after remediation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-warning-review
```

Final result:

```text
278 passed, 0 failed, 0 warnings
```

Frontend validation was not required because Phase 18 did not touch frontend
files.

Phase 18 deferred local pytest temp/cache permission warnings, unrelated
frontend generated/dependency drift, and prototype Prospect API scan findings.
Those items are not part of the certified V2 behavior and should be handled
only in separate maintenance work if needed.

Phase 18 did not change API contracts, Recommendation Engine behavior, trust
logic, freshness logic, refusal logic, fatigue formulas, ranking behavior,
selection behavior, prediction behavior, frontend behavior, or Recommendation
Engine V1 behavior.

BaseballOS V2.5 Phase 19 Prototype Surface Maintenance Review evaluates
current backend routes, frontend routes, shared utilities, prototype surfaces,
experimental surfaces, legacy surfaces, and deprecated-surface status.

The Phase 19 prototype surface maintenance review record is:

- `docs/V25_PHASE_19_PROTOTYPE_SURFACE_MAINTENANCE_REVIEW.md`

Phase 19 classifications:

- PRODUCTION: Dashboard, Bullpen, certified V2 bullpen-state API and panel,
  certified V1 candidate API and panel, bullpen workload read APIs, sync
  status, and health.
- SUPPORTED: Methodology, admin sync/recalculation endpoints, frontend API
  normalizers, and availability governance tooling.
- PROTOTYPE: Prospect Pipeline UI, Prospect APIs, Prospect model, and Dashboard
  Pipeline Snapshot.
- EXPERIMENTAL: fatigue-to-ERA analysis, latest-workload snapshot mode, MLB
  passthrough helpers, and availability threshold experiment tooling.
- LEGACY: metadata-less fatigue array response and standalone fatigue
  recalculation script.
- DEPRECATED: none discovered.

Phase 19 applied safe presentation cleanup:

- renamed the Bullpen team view from ranking language to summary language
- defaulted the team summary to alphabetical order
- removed the team summary ordinal column
- renamed the Dashboard prototype pipeline highlight label away from top-style
  wording
- removed ordinal numbering from the Dashboard prototype pipeline highlights

Phase 19 validation:

```text
npm test
77 passed, 0 failed

.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-prototype-review
278 passed, 0 failed
```

Phase 19 did not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, selection behavior,
prediction behavior, or Recommendation Engine V1 behavior.

Prototype governance risk remains deferred to future policy work: the Prospect
Pipeline must not be promoted to production until it has an explicit
promotion contract covering provenance, freshness, limitations, refusal,
fail-closed behavior, and trust metadata.

BaseballOS V2.5 Phase 20 Prototype Promotion and Deprecation Policy creates
the official lifecycle policy for current and future surfaces.

The Phase 20 policy record is:

- `docs/V25_PHASE_20_PROTOTYPE_PROMOTION_AND_DEPRECATION_POLICY.md`

Phase 20 defines these lifecycle transitions:

```text
Prototype -> Experimental -> Supported -> Production
Production -> Legacy -> Deprecated -> Removed
```

Phase 20 promotion requirements include:

- defined purpose and ownership before prototype promotion
- documentation and limitations before experimental support
- test coverage and governance review before supported status
- API/frontend contract review where applicable
- certification review and production readiness review before production
- trust, freshness, refusal, fail-closed, anti-ranking, anti-selection, and
  anti-prediction review for intelligence surfaces

Phase 20 deprecation requirements include:

- replacement or strategic retirement before production becomes legacy
- documented migration path before legacy becomes deprecated
- completed migration window and governance approval before removal

Phase 20 current-surface review finds no classification correction is required.
Prospect Pipeline remains PROTOTYPE. Fatigue-to-ERA insight, latest-workload
snapshot mode, MLB passthrough helpers, and threshold experimentation
surfaces remain EXPERIMENTAL. Metadata-less fatigue array response and the
standalone fatigue recalculation script remain LEGACY.

Phase 20 validation:

```text
npm test
77 passed, 0 failed

.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-promotion-policy
278 passed, 0 failed
```

Phase 20 does not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, frontend behavior,
ranking behavior, selection behavior, prediction behavior, or Recommendation
Engine V1 behavior.

BaseballOS V2.5 Phase 21 Lifecycle Enforcement Checklist converts the Phase 20
policy into an operational checklist that must be completed before lifecycle
movement, production promotion, legacy classification, deprecation, or removal.

The Phase 21 enforcement record is:

- `docs/V25_PHASE_21_LIFECYCLE_ENFORCEMENT_CHECKLIST.md`

Phase 21 checklists cover:

- Prototype -> Experimental
- Experimental -> Supported
- Supported -> Production
- Production -> Legacy
- Legacy -> Deprecated
- Deprecated -> Removed
- intelligence-surface promotion readiness

Phase 21 requires promotion reviews to confirm:

- ownership and purpose are documented
- maintenance expectations are defined
- contracts are reviewed where applicable
- test coverage exists for the requested tier
- trust metadata is defined, visible, and tested where intelligence is shown
- freshness metadata is defined, visible, and tested where intelligence is shown
- refusal metadata and fail-closed behavior are defined and tested where
  applicable
- certification and rollout review are complete before production eligibility
- ranking, selection, prediction, best option, preferred option, and recommended
  option behavior are reviewed before promotion eligibility

Phase 21 conceptual readiness review finds no current prototype or experimental
surface is unexpectedly promotion-ready:

- Prospect Pipeline remains PROTOTYPE and does not pass Prototype ->
  Experimental readiness.
- Fatigue-to-ERA insight remains EXPERIMENTAL and does not pass Experimental ->
  Supported readiness.
- Latest-workload snapshot mode remains EXPERIMENTAL and does not pass
  Experimental -> Supported readiness.
- MLB passthrough helpers remain EXPERIMENTAL and do not pass Experimental ->
  Supported readiness.
- Threshold experimentation tooling remains EXPERIMENTAL and does not pass
  Experimental -> Supported readiness.

Phase 21 does not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, frontend behavior,
ranking behavior, selection behavior, prediction behavior, or Recommendation
Engine V1 behavior.

Phase 21 validation:

```text
npm test
ENOENT at repository root because no root package.json exists.

cd frontend
npm test
78 passed, 0 failed

.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-lifecycle-enforcement
278 passed, 0 failed
```

BaseballOS V2.5 Phase 22 Lifecycle Review Log and Adoption Audit establishes
the auditable adoption layer for Phase 21 checklist enforcement.

The Phase 22 audit record is:

- `docs/V25_PHASE_22_LIFECYCLE_REVIEW_LOG_AND_ADOPTION_AUDIT.md`

The Phase 22 adoption audit requires every future lifecycle change to retain:

- surface name and classification
- requested lifecycle transition
- applicable Phase 21 checklist
- owner or owning area
- purpose, audience, limitations, and maintenance expectations
- backend, frontend, script, report, and contract impact
- governance, trust, freshness, refusal, fail-closed, and anti-ranking /
  anti-selection / anti-prediction evidence where applicable
- test evidence
- certification and rollout evidence before production eligibility
- migration, notice, and approval evidence before deprecation or removal

Phase 22 surface-by-surface adoption review confirms:

- certified V2 production remains limited to `GET
  /api/recommendations/v2/bullpen-state` and the Dashboard V2 Bullpen State
  panel
- Dashboard, Bullpen, V1 candidate API and panel, bullpen fatigue APIs, and
  bullpen read APIs remain accepted production surfaces
- Methodology, admin sync and recalculation, frontend API normalizers, and
  availability governance reports/scripts remain supported surfaces
- Prospect Pipeline UI, Prospect APIs, and Dashboard Pipeline Snapshot remain
  PROTOTYPE and do not pass Prototype -> Experimental readiness
- Fatigue-to-ERA insight, latest-workload snapshot mode, MLB passthrough
  helpers, and threshold experimentation tooling remain EXPERIMENTAL and do
  not pass Experimental -> Supported readiness
- metadata-less fatigue array response and standalone fatigue recalculation
  script remain LEGACY and require consumer/replacement evidence before
  deprecation

Phase 22 explicitly confirms no current prototype or experimental surface is
promotion-ready.

The certified Recommendation Engine V2 governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

Phase 22 does not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, frontend behavior,
ranking behavior, selection behavior, prediction behavior, best option
behavior, preferred option behavior, recommended option behavior, or
Recommendation Engine V1 behavior.

Phase 22 validation:

```text
pytest
Result: Not available on PATH in this shell; no project failure recorded.

.\backend\venv\Scripts\python.exe -m pytest backend\tests
Result: 271 passed before 7 local temp/cache collection errors caused by
Windows access denial under C:\Users\nikko\AppData\Local\Temp\pytest-of-nikko.

.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-phase-22-lifecycle-audit
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

BaseballOS V2.5 Phase 23 Lifecycle Evidence Backfill and Owner Assignment Plan
converts the Phase 22 adoption audit findings into a structured evidence
acquisition framework.

The Phase 23 plan is:

- `docs/V25_PHASE_23_LIFECYCLE_EVIDENCE_BACKFILL_AND_OWNER_ASSIGNMENT_PLAN.md`

Phase 23 requires every future lifecycle movement to resolve or explicitly
record:

- surface owner and owning area
- evidence collection owner
- runbook and maintenance expectations
- trust, freshness, refusal, and fail-closed metadata evidence where applicable
- test evidence for normal, stale, missing, malformed, unsupported, and
  governance-unsafe behavior where applicable
- governance review evidence, including ranking, selection, prediction, and
  best/preferred/recommended behavior review
- certification evidence before production eligibility
- rollout evidence before production eligibility
- legacy consumer, migration, notice, and approval evidence before deprecation
  or removal

Phase 23 surface-by-surface evidence review confirms:

- certified V2 production remains unchanged
- supported surfaces need stronger runbook and evidence-retention records
  before any production classification
- Prospect Pipeline UI, Prospect APIs, and Dashboard Pipeline Snapshot remain
  PROTOTYPE and fail Prototype -> Experimental evidence readiness
- Fatigue-to-ERA insight, latest-workload snapshot mode, MLB passthrough
  helpers, and threshold experimentation tooling remain EXPERIMENTAL and fail
  Experimental -> Supported evidence readiness
- metadata-less fatigue array response and standalone fatigue recalculation
  script remain LEGACY and need consumer, replacement, migration, and retirement
  evidence before deprecation

Phase 23 explicitly confirms no current prototype or experimental surface is
promotion-ready.

The certified Recommendation Engine V2 governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

Phase 23 does not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, frontend runtime
behavior, ranking behavior, selection behavior, prediction behavior, best
option behavior, preferred option behavior, recommended option behavior, or
Recommendation Engine V1 behavior.

Phase 23 validation:

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

BaseballOS V2.5 Phase 24 Lifecycle Evidence Packet Template and Initial
Backfill creates the standard lifecycle evidence packet framework required by
the Phase 21 through Phase 23 lifecycle governance chain.

The Phase 24 packet framework record is:

- `docs/V25_PHASE_24_LIFECYCLE_EVIDENCE_PACKET_TEMPLATE_AND_INITIAL_BACKFILL.md`

Phase 24 defines required evidence packet sections for:

- owner evidence
- runbook evidence
- metadata evidence
- test evidence
- governance evidence
- certification evidence
- migration evidence
- evidence retention
- packet review
- promotion readiness
- demotion, deprecation, and removal readiness

Phase 24 creates initial packet stubs for:

- Dashboard V2 Bullpen Intelligence
- `/api/recommendations/v2/bullpen-state`
- Prospect Pipeline
- Fatigue-to-ERA Insight
- Snapshot Mode
- MLB Passthrough Helpers
- Threshold Experimentation
- metadata-less fatigue array response
- standalone recalculation script

Phase 24 explicitly avoids fabricating evidence. The initial packet stubs record
known evidence where existing certification, rollout, review, or governance
records already apply, and they mark missing evidence where owner, runbook,
metadata, test, governance, certification, migration, or retention proof is not
yet complete.

Phase 24 confirms:

- production packet stubs preserve the current certified V2 scope
- Prospect Pipeline remains PROTOTYPE and is not promotion-ready
- Fatigue-to-ERA Insight, Snapshot Mode, MLB Passthrough Helpers, and Threshold
  Experimentation remain EXPERIMENTAL and are not promotion-ready for Supported
- metadata-less fatigue array response and standalone recalculation script
  remain LEGACY and are not ready for deprecation or removal

The certified Recommendation Engine V2 governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

Phase 24 does not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, frontend runtime
behavior, ranking behavior, selection behavior, prediction behavior, best
option behavior, preferred option behavior, recommended option behavior, or
Recommendation Engine V1 behavior.

Phase 24 validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-phase-24-evidence-packets
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

Root `npm test` is not required for Phase 24. No root `package.json` exists,
which is expected and is not a project failure.

BaseballOS V2.5 Phase 25 Lifecycle Evidence Packet Review and Backfill
Execution performs the first formal review of the Phase 24 packet stubs.

The Phase 25 packet review record is:

- `docs/V25_PHASE_25_LIFECYCLE_EVIDENCE_PACKET_REVIEW_AND_BACKFILL_EXECUTION.md`

Phase 25 establishes:

- evidence packet review methodology
- evidence completeness criteria
- evidence readiness scoring
- owner evidence review
- runbook evidence review
- metadata evidence review
- test evidence review
- governance evidence review
- certification evidence review
- migration evidence review
- evidence retention review
- surface-by-surface packet assessment
- backfill execution inventory
- readiness classification framework

Phase 25 reviews packet status for:

- Dashboard V2 Bullpen Intelligence
- `/api/recommendations/v2/bullpen-state`
- Prospect Pipeline
- Fatigue-to-ERA Insight
- Snapshot Mode
- MLB Passthrough Helpers
- Threshold Experimentation
- metadata-less fatigue array response
- standalone recalculation script

Phase 25 readiness classifications are:

| Classification | Surfaces |
|----------------|----------|
| READY_FOR_STEWARDSHIP_REVIEW | Dashboard V2 Bullpen Intelligence; `/api/recommendations/v2/bullpen-state` |
| READY_FOR_REQUESTED_REVIEW | None |
| REVIEWABLE_WITH_MINOR_GAPS | None |
| BACKFILL_REQUIRED | Prospect Pipeline; Fatigue-to-ERA Insight; Snapshot Mode; MLB Passthrough Helpers; Threshold Experimentation |
| BLOCKED_BY_MISSING_EVIDENCE | metadata-less fatigue array response; standalone recalculation script |

Phase 25 does not promote, demote, deprecate, remove, or modify any surface.
The review records known evidence where current governance records already
apply and preserves missing evidence where packet sections remain incomplete.

The certified Recommendation Engine V2 governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

Phase 25 does not change backend recommendation logic, API contracts, trust
logic, freshness logic, refusal logic, fatigue formulas, frontend runtime
behavior, ranking behavior, selection behavior, prediction behavior, best
option behavior, preferred option behavior, recommended option behavior, or
Recommendation Engine V1 behavior.

Phase 25 validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-phase-25-evidence-review
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

Root `npm test` is not required for Phase 25. No root `package.json` exists,
which is expected and is not a project failure.

## Future Expansion Boundary

Future recommendation work belongs in Recommendation Engine V2 or later.

Possible future expansion areas include:

- bullpen-level intelligence
- team-level stress intelligence
- bullpen inventory visibility
- API-visible grouped eligibility reporting when separately authorized
- bullpen readiness reporting
- neutral planning support with explicit governance review
- advanced decision-support layers
- role-aware recommendation behavior
- simulator integration

This project state document does not authorize further Recommendation Engine
API exposure beyond the approved V2 bullpen-state endpoint, user-facing V2 UI
surfaces beyond the governed Phase 10 rendering layer, Phase 10B Bullpen
selected-pitcher layout remediation, Phase 11 mobile/accessibility validation,
Phase 12 certification readiness validation, and Phase 13 formal
certification review, V2.5 Phase 14 inventory presentation optimization, and
V2.5 Phase 15 intelligence presentation optimization, production rollout
within the Phase 16-approved current certified V2 experience, or Phase 17
post-rollout monitoring and boundary review, or Phase 18 maintenance warning
remediation review, or Phase 19 prototype surface maintenance review, or
Phase 20 prototype promotion and deprecation policy, or Phase 21 lifecycle
enforcement checklist, or Phase 22 lifecycle review log and adoption audit,
or Phase 23 lifecycle evidence backfill and owner assignment plan, or Phase 24
lifecycle evidence packet template and initial backfill, or Phase 25 lifecycle
evidence packet review and backfill execution.

This project state document also does not authorize pitcher ranking, pitcher
ordering, scoring, final pitcher selection, or new automated decision behavior.
