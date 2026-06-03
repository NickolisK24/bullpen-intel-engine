# BaseballOS V3 Phase 8 - Team Operations Bullpen Readiness Frontend Integration Plan

## Decision

Phase 8 decision:

```text
V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN_COMPLETE
FRONTEND_IMPLEMENTATION = NOT_STARTED
PRODUCTION_CERTIFICATION = NOT_GRANTED
INTERNAL_ROUTE_STATUS = INTERNAL_NON_PRODUCTION_UNCERTIFIED
```

Phase 8 defines the governed frontend integration plan for Team Operations
Bullpen Readiness. It does not add UI, client code, route exposure changes, or
production certification.

## Phase Purpose

BaseballOS V3 Phase 8 plans how the future Team Operations Bullpen Readiness
payload should be presented on the Dashboard after the Phase 7 route
certification-readiness review.

The phase converts route readiness into frontend integration requirements:

- frontend client strategy
- API normalization strategy
- component architecture
- Dashboard placement
- summary-first presentation
- expand-on-demand details
- trust, freshness, refusal, fail-closed, and governance metadata visibility
- accessibility and mobile behavior
- neutral language rules
- prohibited UI patterns
- frontend tests required before certification

The plan preserves the user as the decision maker.

## Scope

In scope:

- planning for frontend client/API normalization
- planning for Dashboard placement
- planning for future component architecture
- planning for summary-first and expand-on-demand rendering
- planning for trust, freshness, refusal, fail-closed, and governance metadata
  display
- planning for accessibility, keyboard, screen-reader, and mobile behavior
- planning for frontend tests and certification requirements

Out of scope:

- frontend implementation
- frontend route calls
- Dashboard component changes
- CSS changes
- backend changes
- API contract changes
- public route certification
- production rollout
- recommendation logic changes
- fatigue formula changes
- ranking, selection, prediction, or pitcher-level guidance

## Relationship To V3 Phases 2-7

V3 Phase 2 defines the Team Operations Bullpen Readiness capability as a
governed intelligence layer that summarizes bullpen operational state without
ranking pitchers, selecting pitchers, recommending pitchers, predicting
outcomes, or telling the user who to use.

V3 Phase 3 defines the implementation plan, including a separate Team
Operations backend/API path, summary-first Dashboard presentation, metadata
visibility, and certification gates.

V3 Phase 4 defines the formal API contract and certification requirements for:

```text
GET /api/team-operations/bullpen-readiness
```

V3 Phase 5 implements the backend domain foundation and deterministic
team-level readiness assembly.

V3 Phase 6 registers the route as internal, non-production, and uncertified.

V3 Phase 7 reviews the internal route and classifies it as:

```text
READY_FOR_FRONTEND_INTEGRATION_PLANNING
```

V3 Phase 8 plans frontend integration only. It does not change the internal
route status and does not mark the route production-certified.

## Frontend Integration Goals

Frontend integration goals:

- present bullpen readiness as team-level context only
- make trust, freshness, refusal, fail-closed, and governance metadata visible
- keep readiness status qualified by data state and source limitations
- summarize workload pressure, constraints, coverage inventory, handedness
  coverage, and availability distribution without pitcher ordering
- preserve neutral count and distribution language
- avoid visual priority cues that imply pitcher rank
- keep high-volume evidence collapsed by default
- make expanded detail available for review
- preserve accessible headings, buttons, focus order, and status messaging
- provide testable frontend contract normalization before any visible UI

## Frontend Non-Goals

Phase 8 and the future governed UI must not:

- rank pitchers
- recommend pitchers
- select pitchers
- imply hidden pitcher priority
- present matchup advice
- predict game outcomes
- predict injuries
- predict saves
- predict pitcher performance
- label a pitcher as best, preferred, or recommended
- use visual hierarchy to imply who should be used
- reuse the Recommendation Engine V2 panel as a hidden recommendation surface
- mark the internal route production-certified

## Dashboard Placement Strategy

Future Dashboard placement should be near existing trust and bullpen context
surfaces, not inside individual pitcher tables.

Recommended placement:

1. Keep `SyncStatusContent` near the top as the global data trust strip.
2. Keep `AvailabilityDashboardSummary` as the existing availability summary.
3. Keep `RecommendationV2BullpenStatePanel` as the certified V2 recommendation
   intelligence surface.
4. Add a future Team Operations Bullpen Readiness panel after the availability
   summary and before or near the V2 governed panel.

Rationale:

- the readiness surface is team-level/context-level
- the user can read data trust first
- the availability summary remains the existing operational baseline
- the V2 recommendation panel remains separate and certified
- Team Operations readiness does not appear as a pitcher-selection workflow

The future panel should not be placed inside:

- the high-fatigue pitcher table
- the pitcher detail panel
- the Prospect Pipeline snapshot
- candidate evaluation surfaces

## Client/API Normalization Strategy

The next frontend implementation milestone should create a client contract layer
before rendering UI.

Likely future files:

```text
frontend/src/utils/api.js
frontend/tests/teamOperationsBullpenReadinessApi.test.mjs
```

Future client work should:

- define a `TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE` constant
- call `/team-operations/bullpen-readiness` through the existing API base path
- allow only safe query parameters from the frontend
- normalize successful, degraded, refused, and unavailable states
- reject or mark unavailable any response missing required metadata
- reject or mark unavailable any response with forbidden fields
- preserve `ranking_applied === false`
- preserve `selection_made === false`
- expose route metadata showing internal/non-production/uncertified status
- deduplicate safe GET requests using the existing GET request dedupe pattern
- keep the certified Recommendation Engine V2 client unchanged

Required normalized state fields should include:

- endpoint
- contract state
- route status
- readiness status
- trust metadata
- freshness metadata
- refusal metadata
- fail-closed metadata
- governance metadata
- limitations
- explanations
- constraints
- workload pressure
- availability distribution
- coverage inventory
- handedness coverage
- missing fields
- malformed fields
- forbidden field paths

## Component Architecture Plan

Future component work should be separate from Recommendation Engine components.

Likely future files:

```text
frontend/src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx
frontend/src/components/teamOperations/teamOperationsBullpenReadinessView.js
frontend/src/components/teamOperations/index.js
frontend/tests/teamOperationsBullpenReadinessRendering.test.mjs
```

The component architecture should include:

- a view-model helper for contract-safe normalization into display sections
- a panel component for Dashboard rendering
- reusable metadata cells for trust/freshness/governance fields
- collapsible detail sections for evidence-heavy areas
- refusal and fail-closed rendering states
- prohibited-language guardrails in tests

The component should not share state with pitcher selection, candidate
evaluation, or Recommendation Engine V2 ranking/selection concepts.

## Summary-First Rendering Plan

The default collapsed view should show:

- readiness status
- route status
- high-level readiness summary
- constraint count summary
- workload pressure summary
- availability distribution summary
- coverage inventory summary
- handedness coverage summary
- trust state
- freshness state
- refusal/fail-closed state when present
- governance flags

The default view should avoid:

- full pitcher lists
- pitcher ordering by status, quality, risk, score, or suggested use
- long evidence lists
- expanded nested metadata by default
- dense payload dumps

Recommended visible copy patterns:

- "Bullpen readiness context"
- "Team-level readiness summary"
- "Coverage inventory"
- "Workload pressure"
- "Constraints"
- "Availability distribution"
- "Data limitations"
- "Readiness withheld"

## Expand-On-Demand Detail Plan

The future panel should use expand-on-demand controls for:

- constraints
- workload pressure detail
- availability distribution rows
- coverage inventory rows
- handedness coverage rows
- explanations
- limitations
- refusal details
- fail-closed evidence
- trust metadata
- freshness metadata
- route metadata

Expansion behavior should:

- use semantic buttons
- expose `aria-expanded`
- keep focus on the triggering control
- preserve stable section IDs
- avoid layout shifts for metadata grids
- keep mobile sections short by default

Expanded detail may include pitcher counts and source evidence. It must not
display pitcher lists in an order that implies priority.

## Trust Metadata Presentation Plan

Trust metadata should be visible in the default panel summary and fully
inspectable on demand.

Default trust fields:

- confidence
- data state
- source evidence state
- governance state

Expanded trust fields:

- confidence reasons
- trust limitations
- trust explanations
- trust validation errors
- route/internal status
- `ranking_applied`
- `selection_made`

Trust presentation rules:

- low or unknown confidence must qualify the readiness summary
- missing trust metadata must render unavailable/refused state
- trust metadata must not be hidden behind only color
- trust copy must not imply a recommendation

## Freshness Metadata Presentation Plan

Freshness metadata should be visible near the readiness status and metadata
summary.

Default freshness fields:

- freshness state
- data through
- latest workload date
- latest sync status
- latest successful sync where available

Expanded freshness fields:

- latest fatigue calculated at
- generated at
- stale warning
- missing data warning
- freshness limitations

Freshness presentation rules:

- stale, missing, historical, or incomplete data must visibly qualify the
  readiness summary
- freshness warnings must be readable on mobile
- freshness state must not be converted into a confidence score
- current data must not be claimed when the response says stale or missing

## Refusal/Fail-Closed Presentation Plan

Refusal and fail-closed states should render as valid governed states, not as
generic application errors.

Default refused/fail-closed view should show:

- state label
- reason code
- reason summary
- recovery note
- trust state where available
- freshness state where available
- governance flags

Expanded refused/fail-closed view should show:

- refusal identifier
- applies-to field
- source limitations
- fail-closed metadata
- route metadata
- explanations

The future UI must not render withheld readiness details as if they are current
team context. It may show safe degraded context only when the normalized
contract marks it safe.

## Governance Metadata Presentation Plan

The panel must explicitly preserve and expose:

```text
ranking_applied === false
selection_made === false
```

Default governance presentation should include a compact metadata row showing:

- `ranking_applied: false`
- `selection_made: false`

Expanded governance presentation should include:

- route status
- contract identity
- contract version
- internal/non-production/uncertified status
- prohibited behavior summary

The UI must never convert governance flags into marketing copy or use them as a
substitute for actual anti-ranking and anti-selection validation.

## Accessibility Plan

Future accessibility requirements:

- use a proper heading hierarchy inside the Dashboard
- provide keyboard-operable expand/collapse controls
- use `aria-expanded` and stable control labels
- provide visible focus states
- expose refused/fail-closed transitions through a status region when loaded
- avoid relying on color alone for trust, freshness, or refusal status
- make metadata labels programmatically associated with values
- preserve reading order from summary to details
- keep expanded details reachable without keyboard traps
- ensure loading and error states are announced consistently with existing
  Dashboard patterns

Screen-reader labels should describe the surface as team-level readiness
context, not pitcher advice.

## Mobile/Responsive Plan

Future mobile behavior should follow the existing summary-first pattern used by
the governed V2 panel.

Mobile requirements:

- single-column layout by default
- compact summary cards
- metadata grids that wrap without horizontal scroll
- collapsed evidence sections by default
- large enough touch targets for expand/collapse controls
- no dense table layout for readiness evidence
- no side-by-side comparisons that imply pitcher priority
- no fixed-height container that clips refusal or metadata text

Desktop behavior may use multi-column metadata grids only when labels and
values remain readable.

## Loading/Error/Degraded State Plan

Loading state:

- use existing Dashboard loading conventions
- state that readiness context is loading
- do not show stale previous readiness details unless explicitly cached and
  labeled as stale in a later approved milestone

Error state:

- use existing retry conventions
- distinguish application fetch errors from governed refusal states
- do not present backend refusal as a frontend crash

Degraded state:

- show available safe context only when the normalized contract marks it safe
- show trust/freshness limitations
- keep refusal/fail-closed metadata visible
- avoid hiding governance flags

Unavailable state:

- show missing/malformed/forbidden contract evidence
- withhold readiness details
- preserve route and governance metadata where available

## Neutral Language Rules

Allowed language:

- "readiness context"
- "team-level summary"
- "constraints"
- "coverage"
- "distribution"
- "workload pressure"
- "availability state"
- "data limitations"
- "refused"
- "fail-closed"
- "source evidence"

Required language properties:

- describe context, not decisions
- describe counts and distributions, not pitcher quality
- describe limitations before interpretation when data is stale or missing
- use "withheld" when readiness is refused
- keep the user as decision maker

Required governance confirmation:

```text
ranking_applied === false
selection_made === false
```

## Prohibited UI Patterns

The future UI must not include:

- ranked pitcher lists
- numbered pitcher priority order
- "best" labels
- "preferred" labels
- "recommended" labels
- "use this pitcher" copy
- matchup advice
- save prediction
- injury prediction
- performance prediction
- win/loss prediction
- hidden priority sorting
- quality-based ordering
- color intensity that implies pitcher quality or selection priority
- charts that visually rank individual pitchers
- badges that imply selection eligibility beyond neutral availability context

If a future implementation displays members of an inventory group, ordering
must be source order, alphabetical order, or another explicitly neutral order
that is documented and tested.

## Frontend Test Plan

Future frontend tests must be added before certification.

Recommended test files:

```text
frontend/tests/teamOperationsBullpenReadinessApi.test.mjs
frontend/tests/teamOperationsBullpenReadinessRendering.test.mjs
frontend/tests/teamOperationsBullpenReadinessAccessibility.test.mjs
```

Client/API tests should verify:

- route constant points to `/team-operations/bullpen-readiness`
- only safe frontend query parameters are sent
- successful response normalizes to team-level context
- degraded response preserves trust/freshness limitations
- refused response preserves refusal/fail-closed metadata
- missing required fields produce unavailable state
- malformed metadata produces unavailable state
- forbidden ranking fields produce unavailable state
- forbidden selection fields produce unavailable state
- forbidden prediction fields produce unavailable state
- `ranking_applied` must be `false`
- `selection_made` must be `false`

Rendering tests should verify:

- default view is summary-first
- details are collapsed by default
- expanded details expose evidence on demand
- trust metadata is visible
- freshness metadata is visible
- refusal metadata is visible in refused/fail-closed states
- governance metadata is visible
- no best/preferred/recommended language appears
- no ranking/selection/prediction language appears except negative governance
  disclaimers
- member rows are not visually prioritized
- V2 recommendation rendering remains unchanged

Accessibility tests should verify:

- heading hierarchy
- keyboard-operable expand/collapse controls
- `aria-expanded`
- stable accessible names
- visible focus path
- status messaging for loading/refused/unavailable states
- mobile-safe metadata layout classes

## Certification Readiness Requirements

Before frontend certification, BaseballOS must have:

- backend route tests passing
- backend domain tests passing
- frontend client normalization tests passing
- frontend rendering tests passing
- frontend prohibited-language tests passing
- accessibility tests passing
- mobile layout review complete
- V2 recommendation frontend tests passing
- route still marked internal/non-production/uncertified until rollout review
- no public production certification claim

Certification must explicitly confirm:

```text
ranking_applied === false
selection_made === false
```

Certification must also confirm absence of:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

## Validation Record

Required Phase 8 validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-8-frontend-plan
Result: 299 passed, 0 failed.

cd frontend
npm test
Result: 78 passed, 0 failed.

git diff --check
Result: Passed.

git diff --cached --check
Result: Passed after targeted documentation staging.
```

Root `npm test` is not required. No root `package.json` exists, which is
expected and is not a project failure.

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Readiness appears to recommend who to use | Keep all copy team-level and prohibit pitcher advice. |
| UI density hides metadata | Use summary-first rendering with visible trust/freshness/governance rows. |
| Expanded member lists imply priority | Require neutral source or alphabetical ordering and test the ordering label. |
| Refusal is mistaken for a broken route | Render refusal/fail-closed as governed states with reason metadata. |
| Internal route appears production-certified | Keep route status visible and avoid production-ready language. |
| Client normalization weakens backend guarantees | Reject missing, malformed, or forbidden payload fields before rendering details. |
| Mobile layout hides limitations | Collapse evidence but keep trust/freshness/refusal summary visible. |
| V2 recommendation UI is accidentally changed | Keep Team Operations components separate and require V2 regression tests. |

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 9 Team Operations Bullpen Readiness Frontend Client Normalization and Contract Tests
```

The next milestone should implement only the frontend client normalization layer
and focused tests for the internal readiness route. Dashboard UI rendering
should remain a later separately authorized milestone after the client contract
is proven safe.
