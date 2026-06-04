# BaseballOS V4 Phase 19 - Frontend Explanation Surface Implementation

## Phase Status

Phase status:

```text
V4_PHASE_19_FRONTEND_EXPLANATION_SURFACE_IMPLEMENTATION_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
FRONTEND_SURFACE_IMPLEMENTED
BACKEND_UNCHANGED
API_CONTRACTS_UNCHANGED
DASHBOARD_REDESIGN_NOT_PERFORMED
PRODUCTION_ROLLOUT_NOT_APPROVED
```

Recommended next milestone:

```text
V4 Phase 20 - Frontend Explanation Surface Certification Readiness Review
```

## Phase Purpose

V4 Phase 19 implements the first governed frontend surfaces for certified V4
explanation APIs. The goal is to let users ask why an existing state appears
without making BaseballOS longer, more audit-like, or advice-like.

The phase exposes certified explanations through compact progressive disclosure
only. It does not introduce new explanation categories, backend behavior, API
routes, Dashboard redesign, recommendation behavior, ranking behavior,
selection behavior, prediction behavior, or decision automation.

## Frontend Surfaces Implemented

Implemented surfaces:

- Operational Readiness section:
  - adds a compact `Why this state?` action
  - lazily fetches the certified Team Operations Readiness explanation
  - keeps detailed explanation evidence hidden until the action is opened
- Selected pitcher detail:
  - adds a compact `Why this availability?` action near the existing
    availability summary
  - lazily fetches the certified Availability explanation for the selected
    pitcher
  - keeps explanation detail out of bullpen list and Dashboard row stacks

Shared implementation:

- `frontend/src/components/explanations/ExplanationDisclosure.jsx`

The shared disclosure renders:

- Summary
- Reasons
- Evidence
- Limitations
- Freshness / Trust / Confidence
- Governance

## API Routes Consumed

The frontend client consumes only certified V4 explanation routes:

```text
GET /api/explanations/team-readiness
GET /api/explanations/team-readiness/<scope>
GET /api/explanations/availability/<pitcher_id>
```

The first implemented Operational Readiness UI uses the default certified
Team Operations Readiness explanation scope:

```text
readiness_state
```

The frontend client supports only certified readiness scopes:

- `readiness_state`
- `workload_state`
- `coverage_state`
- `freshness_state`
- `trust_state`

Unsupported scopes are stopped by the frontend client and normalized as
governed unavailable responses without calling uncertified endpoints.

## Client Normalization

Frontend explanation normalization was added to:

```text
frontend/src/utils/api.js
```

The normalizer handles:

- successful explanation envelopes
- fail-closed unavailable envelopes
- missing governance metadata
- malformed governance metadata
- unsupported readiness scopes
- certified explanation type checks
- internal route status preservation
- governance-safe display fields

Normalized output preserves:

- explanation type
- certification status
- route status
- summary
- primary reasons
- supporting evidence
- limitations
- freshness
- trust
- confidence
- refusal metadata
- governance metadata

## Progressive Disclosure Approach

Default Dashboard visibility remains compact.

Visible by default:

- `Certified V4 Explanation`
- concise `Explanation only` supporting text
- `Why this state?` action

Hidden until user action:

- explanation summary
- reasons
- evidence
- limitations
- freshness metadata
- trust metadata
- confidence metadata
- full governance detail

Within the opened explanation surface, evidence, limitations, metadata, and
governance remain grouped in detail sections. The Dashboard does not render
full explanation evidence blocks inline by default.

## Fail-Closed UI Behavior

Fail-closed explanation responses render as governed unavailable states.

The UI:

- does not fabricate explanation text
- shows returned limitations
- shows refusal reason codes when available
- preserves explanation-only governance language
- avoids fallback content that implies a recommendation or decision

Default fail-closed language:

```text
Explanation unavailable for this state.
```

## Governance UI Behavior

Governance remains visible in compact form.

The shared explanation surface displays:

```text
Explanation only. No ranking, selection, recommendation, or prediction applied.
```

Opened governance detail preserves:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The UI does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation

## Tests Added

Frontend tests added:

```text
frontend/tests/explanationApi.test.mjs
frontend/tests/explanationSurface.test.mjs
```

Coverage includes:

- successful explanation response normalization
- fail-closed response normalization
- missing governance handling
- malformed governance handling
- unsupported scope handling without route calls
- certified team readiness explanation route calls
- certified scoped team readiness route calls
- certified availability explanation route calls
- compact `Why this state?` rendering
- opened explanation detail rendering
- evidence and limitation rendering inside the detail surface
- fail-closed explanation rendering
- governance-safe messaging
- prohibited unsafe language checks
- Dashboard anti-regression checks for no inline full evidence by default
- selected pitcher detail availability explanation wiring

## Anti-Regression Protections

The implementation preserves the Phase 18 Dashboard anti-regression rules:

- no full explanation blocks directly on the Dashboard by default
- no full evidence lists inline by default
- no repeated large governance paragraphs
- no certification notes added to default Dashboard content
- no per-pitcher explanation stacks on the main Dashboard
- no explanation comparison tables
- no visual hierarchy that implies pitcher priority
- no Dashboard redesign

## Intentionally Deferred Surfaces

Deferred surfaces:

- availability explanation actions in every bullpen table row
- availability explanation comparison views
- scoped readiness selector UI for all certified scopes
- explanation drawer or modal infrastructure beyond the compact shared
  disclosure
- frontend certification review
- production rollout approval

These deferrals prevent the first frontend explanation phase from expanding
Dashboard length or creating ranking/comparison cues.

## Behavior Preservation

Phase 19 does not modify:

- backend behavior
- backend API contracts
- fatigue calculations
- availability calculations
- readiness calculations
- Recommendation Engine behavior
- Team Operations readiness governance logic
- database schema

Existing certified backend and frontend behavior remains governed by the
previous certification records.

## Recommended Next Milestone

The next milestone should be:

```text
V4 Phase 20 - Frontend Explanation Surface Certification Readiness Review
```

That review should evaluate whether the Phase 19 explanation surfaces are ready
for formal frontend certification planning, including progressive disclosure,
accessibility, fail-closed display, governance visibility, Dashboard
anti-regression, and V2/V3 behavior preservation.
