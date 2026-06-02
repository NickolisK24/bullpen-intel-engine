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

## Recommendation Engine V2 Strategy and Phase 10 Status

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
layout remediation work.

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
surfaces beyond the governed Phase 10 rendering layer and Phase 10B Bullpen
selected-pitcher layout remediation, pitcher ranking, pitcher ordering,
scoring, or final pitcher selection.
