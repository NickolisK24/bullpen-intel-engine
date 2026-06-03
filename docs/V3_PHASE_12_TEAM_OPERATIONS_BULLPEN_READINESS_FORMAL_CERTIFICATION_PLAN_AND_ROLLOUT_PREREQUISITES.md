# BaseballOS V3 Phase 12 - Team Operations Bullpen Readiness Formal Certification Plan And Rollout Prerequisites

## Decision

Phase 12 decision:

```text
V3_PHASE_12_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_PLAN_AND_ROLLOUT_PREREQUISITES_COMPLETE
FORMAL_CERTIFICATION_PLAN = COMPLETE
PRODUCTION_CERTIFICATION = NOT_GRANTED
PRODUCTION_ROLLOUT = NOT_GRANTED
INTERNAL_ROUTE_STATUS = INTERNAL_NON_PRODUCTION_UNCERTIFIED
DASHBOARD_UI_STATUS = IMPLEMENTED_INTERNAL_UNCERTIFIED
```

Phase 12 creates the formal certification plan and rollout prerequisite
checklist for Team Operations Bullpen Readiness. It does not certify the route,
does not certify the Dashboard UI, does not authorize production rollout, and
does not change the certified Recommendation Engine V2 contract.

## Phase Purpose

BaseballOS V3 Phase 12 converts the Phase 11 readiness decision into a concrete
certification plan.

The purpose is to define exactly what must be proven before the internal,
non-production, uncertified Team Operations Bullpen Readiness route and
Dashboard UI can move into a later formal certification review and production
rollout decision.

This phase makes the next gate auditable. It records the evidence that must be
assembled, the test coverage that must pass, the accessibility and browser
reviews that must be documented, and the rollout conditions that must remain
blocked until formal certification is complete.

## Scope

In scope:

- formal certification plan
- backend certification checklist
- frontend certification checklist
- accessibility certification checklist
- governance certification checklist
- data freshness certification checklist
- trust metadata certification checklist
- refusal and fail-closed certification checklist
- V2 regression certification checklist
- monitoring artifact requirements
- lifecycle evidence packet requirements
- production rollout prerequisites
- certification stop conditions
- recommended next milestone

Out of scope:

- production certification
- production rollout approval
- public route certification
- runtime behavior changes
- backend route changes
- frontend implementation changes
- Recommendation Engine V2 contract changes
- fatigue formula changes
- availability threshold changes
- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

## Current Feature Status

Current route:

```text
GET /api/team-operations/bullpen-readiness
```

Current implementation status:

| Surface | Status |
| --- | --- |
| Backend domain foundation | Implemented |
| Internal API route | Implemented / internal / non-production / uncertified |
| Frontend client normalization | Implemented |
| Dashboard UI panel | Implemented / internal UI / uncertified |
| Formal certification | Not granted |
| Production rollout | Not approved |

Current certification gate:

```text
READY_FOR_FORMAL_CERTIFICATION_PLANNING
```

Phase 12 does not advance the feature beyond that gate. It defines what must be
proven before the next gate can be attempted.

## Relationship To V3 Phases 4-11

Phase 4 defines the official Team Operations Bullpen Readiness API contract and
certification requirements.

Phase 5 implements the backend domain foundation, governed contract objects,
deterministic readiness assembly, and fail-closed behavior.

Phase 6 registers the internal route and keeps it marked internal,
non-production, and uncertified.

Phase 7 reviews the route and classifies it as:

```text
READY_FOR_FRONTEND_INTEGRATION_PLANNING
```

Phase 8 defines the governed frontend integration plan.

Phase 9 implements frontend client normalization and contract tests.

Phase 10 implements the Dashboard panel as an internal, uncertified UI surface.

Phase 11 reviews that Dashboard panel and classifies it as:

```text
READY_FOR_FORMAL_CERTIFICATION_PLANNING
```

Phase 12 uses those records as the evidence baseline and defines the checklist
that a future formal certification phase must complete.

## Certification Objective

The certification objective is to prove that Team Operations Bullpen Readiness
is safe to evaluate for production certification as a governed team-level
readiness context surface.

Formal certification must prove:

- the backend route preserves the Phase 4 contract
- the route remains separate from certified Recommendation Engine V2
- trust metadata is present, visible, and contract-safe
- freshness metadata is present, visible, and contract-safe
- refusal metadata is present when readiness is withheld
- fail-closed behavior remains intact
- the Dashboard UI renders safe, degraded, refused, and unavailable states
- browser, mobile, keyboard, and screen-reader reviews are documented
- production rollout monitoring artifacts are defined before rollout approval
- lifecycle evidence packets include exact proof, not broad assertions
- governance boundaries remain intact

## Certification Non-Goals

Formal certification planning does not authorize:

- public production exposure
- route promotion to production
- Dashboard UI promotion to certified production
- Recommendation Engine V2 contract changes
- broader Team Operations expansion
- pitcher ranking
- pitcher recommendation
- pitcher selection
- matchup advice
- outcome prediction
- injury prediction
- save prediction
- performance prediction

The user remains the decision maker. Readiness must remain team-level and
context-level only.

## Backend Certification Checklist

Formal backend certification must prove all of the following:

- [ ] `GET /api/team-operations/bullpen-readiness` is still separate from
  `GET /api/recommendations/v2/bullpen-state`.
- [ ] Route metadata still marks the surface internal, non-production, and
  uncertified until rollout approval.
- [ ] Allowed query parameters remain constrained to safe team/detail context.
- [ ] Unsupported query parameters return governed refusal or fail-closed
  payloads.
- [ ] Prohibited query intent is refused for ranking, selection,
  recommendation, matchup, prediction, injury, save, and performance requests.
- [ ] Response contract identity is present.
- [ ] Readiness status uses only approved vocabulary.
- [ ] Constraint categories and severities use only approved vocabulary.
- [ ] Trust metadata is present in available, degraded, refused, and
  unavailable states.
- [ ] Freshness metadata is present in available, degraded, refused, and
  unavailable states.
- [ ] Refusal metadata is present when output is refused.
- [ ] Fail-closed metadata is present in refused and unsafe states.
- [ ] Missing trust metadata fails closed.
- [ ] Missing freshness metadata fails closed.
- [ ] Explicit refusal input fails closed.
- [ ] Backend response payload contains no ranking fields.
- [ ] Backend response payload contains no selection fields.
- [ ] Backend response payload contains no prediction fields.
- [ ] Backend response payload contains no best/preferred/recommended labels.
- [ ] Backend tests record exact test files and test names in the evidence
  packet.

Required backend evidence sources:

- `backend/team_operations/contracts.py`
- `backend/team_operations/bullpen_readiness.py`
- `backend/api/team_operations.py`
- `backend/tests/test_team_operations_bullpen_readiness.py`
- `backend/tests/test_team_operations_bullpen_readiness_api.py`

## Frontend Certification Checklist

Formal frontend certification must prove all of the following:

- [ ] The Dashboard uses the Phase 9 normalized client payload.
- [ ] The Dashboard panel clearly identifies Team Operations Bullpen Readiness.
- [ ] Internal, non-production, uncertified status is visible.
- [ ] Readiness is presented as team-level context only.
- [ ] Summary-first rendering is preserved.
- [ ] Context details remain available on demand.
- [ ] Evidence remains available on demand.
- [ ] Metadata remains available on demand.
- [ ] Successful payloads render safely.
- [ ] Degraded payloads render visibly degraded.
- [ ] Refused and fail-closed payloads render as governed states.
- [ ] Unavailable or unsafe normalized payloads withhold readiness details.
- [ ] Trust metadata is visible.
- [ ] Freshness metadata is visible.
- [ ] Refusal metadata is visible when present.
- [ ] Fail-closed metadata is visible when present.
- [ ] Governance metadata is visible.
- [ ] No UI copy labels a pitcher best, preferred, or recommended.
- [ ] No UI copy tells the user who to use.
- [ ] No layout implies pitcher priority, ranking, selection, or hidden order.
- [ ] Existing certified V2 Dashboard rendering remains covered.

Required frontend evidence sources:

- `frontend/src/utils/api.js`
- `frontend/src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx`
- `frontend/src/components/teamOperations/index.js`
- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/tests/teamOperationsBullpenReadinessApi.test.mjs`
- `frontend/tests/teamOperationsBullpenReadinessRendering.test.mjs`
- `frontend/tests/recommendationV2Api.test.mjs`
- `frontend/tests/recommendationV2Rendering.test.mjs`

## Accessibility Certification Checklist

Formal accessibility certification must prove all of the following:

- [ ] Expand/collapse controls are keyboard-operable.
- [ ] Expand/collapse controls expose accurate `aria-expanded` states.
- [ ] Expand/collapse controls use stable accessible names.
- [ ] Expanded sections preserve readable focus order.
- [ ] Loading state uses existing accessible loading semantics.
- [ ] Error state uses existing accessible alert semantics.
- [ ] Refused, degraded, unavailable, and fail-closed states remain readable.
- [ ] Color is not the only signal for readiness, degradation, refusal, or
  fail-closed state.
- [ ] Mobile layout is reviewed at 320 px, 375 px, 390 px, and 768 px.
- [ ] Desktop layout is reviewed at common Dashboard widths.
- [ ] Expanded metadata does not overflow or hide critical labels on mobile.
- [ ] A manual keyboard walkthrough is recorded.
- [ ] A screen-reader smoke review is recorded.
- [ ] Browser screenshots or review notes are retained in the evidence packet.

Accessibility evidence must distinguish automated test coverage from manual
browser, keyboard, and screen-reader review. Automated tests alone are not
sufficient for production certification.

## Governance Certification Checklist

Formal governance certification must prove:

```text
ranking_applied === false
selection_made === false
```

It must also prove:

- [ ] no ranking behavior
- [ ] no selection behavior
- [ ] no prediction behavior
- [ ] no best/preferred/recommended behavior
- [ ] no hidden priority ordering
- [ ] no pitcher-level advice
- [ ] no matchup advice
- [ ] no outcome prediction
- [ ] no injury prediction
- [ ] no save prediction
- [ ] no performance prediction
- [ ] all readiness output remains team-level or context-level
- [ ] the route does not become a hidden recommendation engine
- [ ] the Dashboard panel does not become a hidden recommendation UI

Governance evidence must include backend payload scans, frontend rendering
language checks, and a manual copy review of visible UI strings.

## Data Freshness Certification Checklist

Formal data freshness certification must prove:

- [ ] freshness metadata is present in every contract state
- [ ] freshness state uses approved vocabulary
- [ ] data-through date is visible when available
- [ ] latest workload date is visible when available
- [ ] sync status is visible when available
- [ ] stale source evidence degrades or refuses output as required
- [ ] missing freshness metadata fails closed
- [ ] stale warnings are visible in the Dashboard when present
- [ ] missing-data warnings are visible in the Dashboard when present
- [ ] sync timestamp is not substituted for baseball data-through evidence

Freshness certification must preserve the V2 fail-closed communication lesson:
source freshness, aggregate freshness, sync status, and data-through evidence
must remain distinguishable.

## Trust Metadata Certification Checklist

Formal trust metadata certification must prove:

- [ ] trust metadata is present in every contract state
- [ ] trust confidence uses approved vocabulary
- [ ] trust data state uses approved vocabulary
- [ ] source evidence state is visible
- [ ] governance state is visible
- [ ] trust limitations are available when present
- [ ] trust validation errors are available when present
- [ ] missing trust metadata fails closed
- [ ] malformed trust metadata is treated as unsafe by frontend normalization
- [ ] top-level governance flags and trust metadata governance flags remain
  aligned

Trust metadata must not be used as a hidden score, rank, or recommendation
signal.

## Refusal/Fail-Closed Certification Checklist

Formal refusal and fail-closed certification must prove:

- [ ] unsupported query parameters are refused
- [ ] prohibited query intent is refused
- [ ] missing source inputs fail closed
- [ ] missing trust metadata fails closed
- [ ] missing freshness metadata fails closed
- [ ] explicit refusal input fails closed
- [ ] refused payloads include refusal state, reason code, reason summary, and
  recovery note
- [ ] fail-closed payloads include reason codes, critical-failure state, and
  safe-partial-output state
- [ ] refused and fail-closed Dashboard states are visible and readable
- [ ] refused and fail-closed states do not render withheld readiness as
  available context
- [ ] refusal and fail-closed behavior is tested at backend, client, and
  rendering layers

Fail-closed behavior must not be weakened to improve presentation.

## V2 Regression Certification Checklist

Formal certification must prove certified Recommendation Engine V2 behavior
remains unchanged.

Required checks:

- [ ] `/api/recommendations/v2/bullpen-state` remains stable.
- [ ] Recommendation Engine V2 response governance remains intact.
- [ ] Dashboard V2 panel still renders certified V2 metadata and fail-closed
  states.
- [ ] Recommendation Engine V2 tests pass.
- [ ] Team Operations route tests pass without modifying V2 tests.
- [ ] Team Operations Dashboard tests pass without changing V2 rendering
  behavior.

Certified V2 governance remains:

```text
ranking_applied === false
selection_made === false
```

Phase 12 does not authorize any V2 route, contract, ranking, selection,
prediction, or frontend behavior change.

## Monitoring Artifact Requirements

Before production rollout planning can proceed, BaseballOS must define and
retain monitoring artifacts for Team Operations Bullpen Readiness.

Required artifact fields:

- review date
- reviewer or owner
- route under review
- route status
- deployment environment
- contract state distribution
- refusal reason distribution
- fail-closed reason distribution
- freshness state distribution
- trust confidence distribution
- source evidence state distribution
- internal/non-production/uncertified status confirmation
- governance confirmation
- observed frontend rendering state
- operational notes
- remediation follow-ups

Required monitoring cadence before rollout:

- one pre-certification artifact from local validation
- one pre-rollout artifact from the intended deployment environment
- one post-rollout monitoring artifact if rollout is later approved

No production rollout should be approved without a retained monitoring artifact
format and owner.

## Evidence Packet Requirements

Formal certification must update the lifecycle evidence packet for Team
Operations Bullpen Readiness with exact evidence.

The packet must include:

- owner
- retention owner
- retention cadence
- route status
- Dashboard UI status
- API contract evidence
- backend test files and test names
- frontend test files and test names
- accessibility review evidence
- browser/mobile review evidence
- freshness metadata evidence
- trust metadata evidence
- refusal metadata evidence
- fail-closed metadata evidence
- governance metadata evidence
- V2 regression evidence
- monitoring artifact evidence
- certification decision
- rollout decision status

Evidence packet rules:

- do not fabricate evidence
- cite exact files, test names, sections, or artifacts
- mark missing evidence explicitly
- distinguish automated test evidence from manual review evidence
- distinguish certification approval from rollout approval

## Rollout Prerequisites

Production rollout planning may not begin until formal certification proves:

- backend certification checklist complete
- frontend certification checklist complete
- accessibility certification checklist complete
- governance certification checklist complete
- data freshness certification checklist complete
- trust metadata certification checklist complete
- refusal/fail-closed certification checklist complete
- V2 regression certification checklist complete
- evidence packet updated
- monitoring artifact format retained
- monitoring owner assigned
- deployment environment smoke review complete
- rollback plan documented
- post-rollout monitoring review scheduled

Production rollout approval remains a separate governed decision. Passing
formal certification does not automatically approve rollout.

## Certification Stop Conditions

Formal certification must stop and return remediation if any of the following
are found:

- `ranking_applied` is missing, malformed, or not false
- `selection_made` is missing, malformed, or not false
- route metadata no longer marks the surface internal/non-production before
  rollout approval
- required trust metadata is missing without fail-closed refusal
- required freshness metadata is missing without fail-closed refusal
- refusal metadata is missing for refused output
- fail-closed metadata is missing for fail-closed output
- UI uses best, preferred, recommended, ranking, selection, matchup, or
  prediction language outside negative governance explanations
- UI visually implies pitcher priority
- V2 regression tests fail
- browser/mobile/accessibility evidence is missing
- monitoring artifact requirements are not defined

## Validation Record

Required Phase 12 validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-12-certification-plan
Result: 299 passed, 0 failed.

cd frontend
npm test
Result: 101 passed, 0 failed.

git diff --check
Result: Passed with line-ending warnings only.

git diff --cached --check
Result: Passed after targeted Phase 12 documentation staging.
```

Root `npm test` is not required when no root `package.json` exists.

## Remaining Risks

| Risk | Status | Certification impact |
| --- | --- | --- |
| Formal certification evidence is not yet assembled | Open | Blocks production certification, not certification planning. |
| Browser/mobile visual QA has not been recorded for certification | Open | Blocks production certification until recorded. |
| Manual keyboard and screen-reader review has not been recorded | Open | Blocks production certification until recorded. |
| Production monitoring artifacts are not yet captured | Open | Blocks rollout planning until format and owner are retained. |
| Deployment-environment smoke review is not complete | Open | Blocks rollout approval. |
| Future copy or layout changes could imply pitcher priority | Open | Must remain covered by prohibited-language and visual-review evidence. |

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 13 Team Operations Bullpen Readiness Formal Certification Review
```

The next milestone should execute this certification plan, assemble exact
evidence, record manual browser/mobile/accessibility review, verify monitoring
artifact readiness, and issue a certification decision without automatically
approving production rollout.

## Phase 13 Follow-Up

V3 Phase 13 Team Operations Bullpen Readiness Formal Certification Review is
complete.

The Phase 13 record is:

- `docs/V3_PHASE_13_TEAM_OPERATIONS_BULLPEN_READINESS_FORMAL_CERTIFICATION_REVIEW.md`

Phase 13 decision:

```text
CERTIFICATION_DECISION = CERTIFIED_WITH_NON_BLOCKING_OPERATIONAL_GAPS
PRODUCTION_ROLLOUT = NOT_APPROVED
```

Phase 13 executes the formal certification review described by this plan. It
reviews backend domain evidence, internal route evidence, frontend client
normalization evidence, Dashboard UI evidence, accessibility evidence,
governance evidence, freshness evidence, trust metadata evidence,
refusal/fail-closed evidence, V2 regression evidence, monitoring artifact
status, and evidence packet status.

Phase 13 preserves:

```text
ranking_applied === false
selection_made === false
```

Phase 13 does not approve production rollout. Remaining operational rollout
gaps include monitoring artifact capture, deployment smoke review, manual
browser/mobile evidence, manual screen-reader smoke review, and controlled
rollout planning.
