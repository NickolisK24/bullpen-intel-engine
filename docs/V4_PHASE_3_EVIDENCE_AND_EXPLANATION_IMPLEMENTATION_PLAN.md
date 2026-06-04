# BaseballOS V4 Phase 3 - Evidence And Explanation Implementation Plan

## Phase Status

Phase status:

```text
V4_PHASE_3_EVIDENCE_AND_EXPLANATION_IMPLEMENTATION_PLAN_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
PLANNING_ONLY
```

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_4_BACKEND_DOMAIN_FOUNDATION
```

This document is the authoritative implementation roadmap for V4. It defines
how future implementation phases should build the Evidence and Explanation
Layer without changing runtime behavior in this phase.

## 1. Implementation Overview

V4 should be implemented as a deterministic explanation layer over existing
governed BaseballOS states.

Implementation philosophy:

```text
Explanation over recommendation.
Evidence over advice.
Deterministic output over inference.
Governance-first delivery over feature speed.
```

V4 should not recalculate or override existing BaseballOS decisions. It should
explain states that already exist:

- availability states
- workload states
- readiness states
- freshness states
- trust states
- coverage states
- risk or availability distributions
- refusal and fail-closed states

The implementation should proceed in small, separately certifiable increments.
Backend domain foundations should come first, followed by deterministic
builders, narrow integration with one existing state surface, route planning and
exposure only after contract stability, frontend rendering after client
normalization, then certification and rollout planning.

Mandatory platform invariants:

```text
ranking_applied === false
selection_made === false
```

Future V4 implementation must also preserve:

```text
recommendation_made === false
prediction_made === false
```

V4 may explain.

V4 may not decide.

## 2. Proposed Phase Breakdown

Recommended implementation sequence:

| Phase | Name | Objective | Runtime authorization |
| --- | --- | --- | --- |
| V4 Phase 4 | Backend Domain Foundation | Create internal contracts, constants, validators, and object assembly primitives. | Backend domain only, no public API route. |
| V4 Phase 5 | Explanation Builder | Implement deterministic builder functions over safe internal fixture inputs. | Backend builder only, no user-facing integration. |
| V4 Phase 6 | Availability Explanation Integration | Attach V4 explanation assembly to existing availability evidence internally. | Backend integration only; no public route unless separately approved. |
| V4 Phase 7 | Readiness Explanation Integration | Attach V4 explanation assembly to Team Operations Bullpen Readiness evidence internally. | Backend integration only; preserve V3 readiness behavior. |
| V4 Phase 8 | API Contract And Route Integration | Define and expose a guarded internal explanation route or additive payload strategy. | Internal/non-production route only if certification gates support it. |
| V4 Phase 9 | Frontend Explanation Surface | Add client normalization and governed UI presentation for explanation objects. | Frontend only after route/client contract exists. |
| V4 Phase 10 | Certification Readiness Review | Review backend, route, client, UI, accessibility, and governance evidence. | Documentation/certification review only. |
| V4 Phase 11 | Formal Certification Review | Execute formal certification and determine certified status. | Certification review only, no rollout approval unless separately justified. |
| V4 Phase 12 | Controlled Rollout Planning | Define controlled rollout scope, monitoring artifacts, rollback, and observation requirements. | Rollout planning only. |

Rationale for this sequence:

- V4 needs stable internal contracts before any route or UI.
- Reason codes and evidence items must be testable before user-facing display.
- Availability explanations are a safer first integration than a broad
  multi-surface rollout because the availability engine already exposes
  reasons, confidence, data state, and limitations.
- Readiness explanations should follow only after the V4 domain model proves it
  can preserve no-ranking and no-selection behavior.
- API and frontend work should wait until backend contracts are deterministic
  and governance-safe.

## 3. Backend Implementation Plan

Likely backend areas involved, based on current repository structure:

- `backend/services/availability.py`
- `backend/services/availability_explanations.py`
- `backend/services/availability_summary.py`
- `backend/recommendation/contracts.py`
- `backend/recommendation/v2.py`
- `backend/recommendation/v2_assembly.py`
- `backend/team_operations/contracts.py`
- `backend/team_operations/bullpen_readiness.py`
- `backend/api/recommendations.py`
- `backend/api/team_operations.py`
- `backend/tests/`

Potential new backend package:

```text
backend/explanations/
backend/explanations/__init__.py
backend/explanations/contracts.py
backend/explanations/reason_codes.py
backend/explanations/limitations.py
backend/explanations/evidence.py
backend/explanations/governance.py
backend/explanations/builders.py
backend/explanations/validators.py
```

Potential backend tests:

```text
backend/tests/test_explanations_contracts.py
backend/tests/test_explanations_reason_codes.py
backend/tests/test_explanations_evidence_items.py
backend/tests/test_explanations_governance.py
backend/tests/test_explanations_builders.py
backend/tests/test_availability_explanation_integration.py
backend/tests/test_readiness_explanation_integration.py
backend/tests/test_explanations_api_contract.py
```

What should be added in future implementation:

- explanation domain objects or dictionaries
- explanation scope constants
- evidence item structures
- reason code constants or enums
- limitation structures
- governance payload helpers
- freshness payload helpers
- trust payload helpers
- deterministic builder functions
- validators for required fields
- validators for prohibited behavior
- fail-closed/degraded handling for unsafe metadata
- tests for deterministic assembly
- tests for governance invariants

Backend implementation rules:

- V4 builders must consume existing governed outputs, not replace the engines
  that produce them.
- V4 must not alter fatigue calculations.
- V4 must not alter availability calculations.
- V4 must not alter Recommendation Engine V1 or V2 behavior.
- V4 must not alter Team Operations Bullpen Readiness calculations.
- V4 must not alter trust or freshness logic.
- V4 must not alter API contracts until a future route/contract phase
  explicitly authorizes that work.

Recommended first backend build:

```text
V4 Phase 4 - Backend Domain Foundation
```

Scope for Phase 4 should be limited to:

- internal explanation contract objects
- allowed scope constants
- evidence item contract objects
- reason code constants
- limitation contract objects
- governance helper with required false flags
- validators for missing or malformed governance metadata
- focused tests

Phase 4 should not integrate with availability, readiness, API routes, or
frontend surfaces.

## 4. Frontend Implementation Plan

Likely frontend areas involved, based on current repository structure:

- `frontend/src/utils/api.js`
- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/src/components/dashboard/OperationalReadinessSection.jsx`
- `frontend/src/components/dashboard/AvailabilityDashboardSummary.jsx`
- `frontend/src/components/bullpen/PitcherDetail.jsx`
- `frontend/src/components/bullpen/AvailabilitySummary.jsx`
- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
- `frontend/src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx`
- `frontend/src/components/UI/`
- `frontend/tests/` if future tests follow the existing frontend test layout

Potential future frontend module structure:

```text
frontend/src/components/explanations/
frontend/src/components/explanations/ExplanationDrawer.jsx
frontend/src/components/explanations/EvidencePanel.jsx
frontend/src/components/explanations/ExplanationSummary.jsx
frontend/src/components/explanations/LimitationList.jsx
frontend/src/components/explanations/GovernanceStrip.jsx
frontend/src/components/explanations/index.js
```

Potential UI surfaces:

- `Why this state?` affordance
- explanation drawer
- evidence panel
- compact reason summary
- limitation list
- governance strip
- freshness and trust summary
- refusal/fail-closed detail panel

Frontend implementation rules:

- use summary-first rendering
- keep details behind accessible disclosure controls
- preserve visible governance metadata
- preserve visible freshness and trust metadata
- preserve visible limitations
- avoid visual ordering that implies pitcher priority
- avoid best/preferred/recommended labels for bullpen choice
- avoid matchup advice
- avoid pitcher-level instruction
- avoid prediction language

Recommended frontend sequence:

1. Add client normalization only after a backend contract exists.
2. Add component tests for successful, degraded, and refused explanations.
3. Add prohibited-language tests.
4. Add accessible disclosure tests.
5. Integrate into one narrow surface first.
6. Keep the Dashboard compact by using progressive disclosure.

No frontend UI should be implemented in this phase.

## 5. Contract Plan

V4 should separate internal contracts from future API-facing contracts.

Internal-only first:

- explanation scope
- explanation object
- evidence item
- reason code
- limitation object
- governance object
- freshness object
- trust object
- refusal/fail-closed metadata object
- explanation builder result
- validation result

Potential API-facing later:

- explanation response envelope
- explanation route metadata
- explanation contract identity
- route certification status
- internal/non-production status where applicable
- safe degraded response
- refusal response

### Explanation Object

Internal fields:

```text
explanation_id
scope
subject_type
subject_id
state_explained
summary
primary_reasons
supporting_evidence
limitations
freshness
trust
confidence
governance
generated_at
```

Implementation requirements:

- `scope` must be constrained to approved scope constants.
- `summary` must be derived from reason codes and evidence.
- `primary_reasons` must use stable reason code objects.
- `supporting_evidence` must use evidence item objects.
- `limitations` must remain visible when present.
- `governance` must preserve required false flags.

### Evidence Item

Internal fields:

```text
evidence_id
evidence_type
label
value
unit
source
freshness
trust_status
impact
limitation
```

Implementation requirements:

- evidence must be source-attributed
- evidence must carry freshness and trust context where available
- evidence `impact` must remain explanatory, not advisory
- evidence must not encode hidden priority

### Reason Code

Internal fields:

```text
code
scope
label
summary
display_safe
certification_required
```

Implementation requirements:

- codes should be uppercase snake case
- labels should be display-safe
- codes should be stable across releases
- code changes should require certification review

### Limitation Object

Internal fields:

```text
limitation_type
severity
summary
affected_scopes
requires_refusal
```

Implementation requirements:

- limitations must never hide unsafe evidence
- limitations must be visible in rendered output
- `requires_refusal` must trigger refusal/fail-closed behavior when true

### Governance Object

Required fields and values:

```text
ranking_applied: false
selection_made: false
recommendation_made: false
prediction_made: false
decision_scope: explanation_only
advice_scope: none
```

Implementation requirements:

- missing governance should degrade or refuse explanation output
- malformed governance should degrade or refuse explanation output
- values other than required false flags should fail certification

### Freshness Object

Potential fields:

```text
status
data_through
last_sync_at
source_updated_at
freshness_failure
summary
```

Implementation requirements:

- sync time must not substitute for baseball data-through date
- stale or missing freshness must be visible
- unsafe freshness must degrade or refuse as required

### Trust Object

Potential fields:

```text
status
source
contract
certification_status
trust_failure
summary
```

Implementation requirements:

- trust failures must remain visible
- uncertified sources must not be presented as certified
- missing trust must degrade or refuse as required

## 6. Testing Strategy

Testing should scale with each implementation phase.

Backend domain tests:

- explanation object validation
- evidence item validation
- reason code stability
- limitation object validation
- governance object validation
- freshness object validation
- trust object validation

Builder tests:

- deterministic output for identical inputs
- stable reason code mapping
- evidence attribution accuracy
- limitation visibility
- degraded handling when optional evidence is missing
- refusal/fail-closed handling when required evidence is unsafe

Governance tests:

- `ranking_applied === false`
- `selection_made === false`
- `recommendation_made === false`
- `prediction_made === false`
- no ranking fields
- no selection fields
- no best/preferred arm fields
- no hidden priority fields
- no pitcher-level advice
- no matchup advice

API tests when routes are added:

- response envelope shape
- contract identity
- route internal/non-production status when applicable
- governance metadata visibility
- freshness metadata visibility
- trust metadata visibility
- refusal/fail-closed response shape
- unsafe query intent refusal
- V1/V2/V3 regression safety

Frontend tests when UI is added:

- successful explanation rendering
- degraded explanation rendering
- refused/fail-closed rendering
- evidence panel rendering
- limitation list rendering
- governance strip rendering
- accessible disclosure behavior
- mobile-safe rendering
- prohibited-language scan
- no ranking/selection/prediction/advice language

Regression tests:

- Availability Engine tests still pass.
- Recommendation Engine V1 tests still pass.
- Recommendation Engine V2 tests still pass.
- Team Operations Bullpen Readiness tests still pass.
- Existing Dashboard rendering tests still pass.

## 7. Certification Strategy

V4 certification must prove that explanation remains explanation.

Mandatory certification invariants:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
```

Certification must prove:

- explanation evidence is attributed correctly
- reason codes are stable
- limitations are visible
- explanations do not become advice
- explanations do not rank candidates
- explanations do not choose pitchers
- explanations do not produce matchup guidance
- explanations do not predict performance, injury, saves, or outcomes
- explanations do not create hidden priority ordering
- freshness metadata remains visible
- trust metadata remains visible
- refusal and fail-closed metadata remain visible
- V1 candidate-only boundaries remain intact
- V2 bullpen-state behavior remains unchanged
- V3 readiness behavior remains unchanged

Certification evidence should include:

- backend domain validation results
- builder test results
- route contract tests if route work exists
- frontend rendering tests if UI work exists
- prohibited-language review
- accessibility review for disclosure controls
- evidence traceability review
- retained certification-readiness review
- retained formal certification review

Recommended certification sequence:

1. Certification requirements document.
2. Certification readiness review.
3. Formal certification review.
4. Controlled rollout planning only if certification supports it.

## 8. Rollout Strategy

V4 rollout should be gradual and evidence-retained.

Suggested flow:

```text
Implementation
Internal certification
Dashboard/API review
Controlled rollout approval
Observation readiness
Observation review
```

Rollout principles:

- no full production rollout without formal certification
- no public route exposure before contract review
- no Dashboard exposure before frontend language and accessibility review
- no expansion beyond the first certified explanation scope without a new
  review
- retained monitoring artifacts for rollout and observation
- rollback conditions for governance, trust, freshness, refusal, or usability
  issues

Potential first rollout scope:

- availability explanation for one existing availability state surface
- internal or controlled Dashboard explanation disclosure
- no API exposure beyond a certified route or certified additive contract

Stop conditions:

- governance metadata missing or unsafe
- `ranking_applied` not false
- `selection_made` not false
- recommendation or prediction flags not false
- explanation copy implies advice
- UI implies pitcher priority
- trust/freshness limitations hidden
- V1/V2/V3 regression failure

This phase does not approve rollout.

## 9. Documentation Requirements

Future V4 phases should create or update:

- V4 backend foundation document
- V4 explanation builder document
- V4 availability integration document
- V4 readiness integration document
- V4 API contract document
- V4 frontend integration document
- V4 certification requirements document
- V4 certification-readiness review
- V4 formal certification review
- V4 rollout planning document
- V4 monitoring artifact records if exposed in controlled rollout
- `README.md`
- `docs/PROJECT_STATE_2026_06.md`
- `docs/INDEX.md`
- `docs/ROADMAP.md`
- `docs/governance/CERTIFICATION_LEDGER.md` if certification state changes
- `docs/operations/OPERATIONAL_REVIEWS.md` if operational review is required

Documentation requirements for each implementation phase:

- identify files created and modified
- record validation results
- preserve governance confirmation
- state what is not authorized
- record next milestone
- avoid claiming certification or rollout until reviewed separately

## 10. Implementation Readiness Decision

Decision:

```text
READY_FOR_V4_PHASE_4_BACKEND_DOMAIN_FOUNDATION
```

Rationale:

- V4 Phase 1 defined the capability and governance boundaries.
- V4 Phase 2 defined architecture, scopes, object shapes, evidence items,
  reason codes, limitations, governance contract, API candidates, frontend
  candidates, and certification requirements.
- Phase 3 defines the implementation roadmap, backend plan, frontend plan,
  contract plan, testing strategy, certification strategy, rollout strategy,
  documentation requirements, and first implementation milestone.

This readiness decision authorizes only the next planning-approved build step:

```text
V4 Phase 4 - Backend Domain Foundation
```

Recommended V4 Phase 4 milestone:

```text
V4 Phase 4 - Evidence And Explanation Backend Domain Foundation
```

Phase 4 should create internal backend domain contracts, reason code constants,
evidence item structures, limitation structures, governance helpers, validators,
and focused backend tests. It should not add public API routes, frontend UI,
database migrations, or production rollout authorization.

## Final Boundary

This document authorizes implementation planning only.

It does not authorize:

- backend implementation
- frontend implementation
- database migration
- runtime behavior changes
- API route creation
- API contract exposure
- fatigue calculation changes
- availability calculation changes
- recommendation behavior changes
- readiness calculation changes
- trust logic changes
- freshness logic changes
- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred arm behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation
