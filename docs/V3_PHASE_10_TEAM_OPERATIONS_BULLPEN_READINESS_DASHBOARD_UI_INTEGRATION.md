# BaseballOS V3 Phase 10 - Team Operations Bullpen Readiness Dashboard UI Integration

## Decision

Phase 10 decision:

```text
V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION_COMPLETE
PRODUCTION_CERTIFICATION = NOT_GRANTED
INTERNAL_ROUTE_STATUS = INTERNAL_NON_PRODUCTION_UNCERTIFIED
DASHBOARD_UI_STATUS = IMPLEMENTED_INTERNAL_UNCERTIFIED
```

Phase 10 adds the first governed Dashboard UI integration for Team Operations
Bullpen Readiness. The panel consumes only the Phase 9 normalized frontend
payload, displays the route as internal, non-production, and uncertified, and
does not alter the certified Recommendation Engine V2 contract.

## Phase Purpose

BaseballOS V3 Phase 10 makes the internal Team Operations Bullpen Readiness
capability visible in the Dashboard while preserving the governance boundary
that the user remains the decision maker.

The phase converts the Phase 8 frontend integration plan and Phase 9 client
normalization layer into a bounded Dashboard panel that presents readiness as
team-level context only.

## Scope

In scope:

- Dashboard panel for Team Operations Bullpen Readiness
- Dashboard integration using `getTeamOperationsBullpenReadiness`
- summary-first rendering for readiness status and summary
- expand-on-demand sections for context details, evidence, and metadata
- visible internal, non-production, uncertified route status
- visible trust metadata
- visible freshness metadata
- visible refusal metadata
- visible fail-closed metadata
- visible governance metadata
- safe unavailable, degraded, and refused rendering states
- frontend rendering tests for the new panel

Out of scope:

- production certification
- public certification of the internal route
- backend route changes
- Recommendation Engine V2 contract changes
- fatigue formula changes
- Dashboard V2 recommendation behavior changes
- pitcher ranking
- pitcher selection
- pitcher recommendation
- outcome, injury, save, or performance prediction
- matchup advice
- pitcher-level advice

## Files Created/Modified

Created:

- `docs/V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION.md`
- `frontend/src/components/teamOperations/TeamOperationsBullpenReadinessPanel.jsx`
- `frontend/src/components/teamOperations/index.js`
- `frontend/tests/teamOperationsBullpenReadinessRendering.test.mjs`

Modified:

- `frontend/src/components/dashboard/Dashboard.jsx`
- `README.md`
- `docs/PROJECT_STATE_2026_06.md`
- `docs/V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS.md`

## Dashboard UI Summary

Phase 10 adds `TeamOperationsBullpenReadinessPanel` and mounts it on the
Dashboard below the certified V2 bullpen-state panel.

The Dashboard now fetches the normalized Phase 9 readiness view through:

```text
getTeamOperationsBullpenReadiness({ include_details: true })
```

The panel identifies itself as:

```text
Team Operations Bullpen Readiness
Bullpen Readiness Context
Internal / Non-production / Uncertified
```

The panel is deliberately framed as a context surface, not as a decision or
instruction surface.

## Rendering Behavior

The panel renders:

- readiness contract state
- readiness status
- readiness summary
- team or bullpen context label
- workload pressure
- availability distribution
- coverage inventory
- handedness coverage
- constraints
- explanations
- limitations
- trust metadata
- freshness metadata
- refusal metadata
- fail-closed metadata
- governance metadata

The default presentation is summary-first. High-detail context is kept behind
keyboard-operable expand/collapse sections:

- `Context Details`
- `Evidence`
- `Metadata`

This keeps the Dashboard readable while allowing reviewers and operators to
inspect the evidence that shaped the team-level context.

## Refused/Degraded/Unavailable Behavior

The panel renders safe non-happy paths:

- degraded payloads remain visibly degraded
- refused payloads show refusal and fail-closed metadata
- unavailable payloads with missing, malformed, or unsafe contract metadata
  withhold readiness details and show contract-safety counts

Unsafe normalized payloads are not silently treated as valid. If the Phase 9
normalizer marks the payload unavailable, the Phase 10 panel displays an
unavailable contract state and does not render readiness details as usable
context.

## Trust/Freshness/Governance Display Summary

Trust metadata is displayed on demand with:

- confidence
- data state
- source evidence state
- governance state
- generated timestamp

Freshness metadata is displayed on demand with:

- freshness state
- data-through date
- latest workload date
- last successful sync
- latest sync status
- latest fatigue calculation timestamp
- stale notice
- missing data notice

Governance metadata is displayed on demand and preserves:

```text
ranking_applied === false
selection_made === false
```

The panel also displays the trust metadata governance flags so frontend
reviewers can confirm that top-level and trust metadata remain aligned.

## Accessibility Coverage

Phase 10 implements accessibility requirements through:

- semantic section labeling
- stable panel heading
- keyboard-operable `button` expand/collapse controls
- `aria-expanded` state on each expandable section
- `aria-controls` references for expanded content
- focus-ring-compatible button styling
- screen-reader-safe loading status via existing `LoadingPane`
- alert behavior for existing `ErrorState`
- visible refused, degraded, and unavailable states
- responsive one-column to two-column layouts for mobile and desktop

## Testing Coverage

Phase 10 adds `frontend/tests/teamOperationsBullpenReadinessRendering.test.mjs`.

The tests cover:

- successful normalized payload rendering
- degraded normalized payload rendering
- refused/fail-closed normalized payload rendering
- internal, non-production, uncertified status visibility
- governance flag visibility
- trust metadata visibility
- freshness metadata visibility
- expand/collapse accessibility state
- absence of best/preferred/recommended display language
- absence of unsafe guidance language outside required governance fields
- Dashboard import and wiring safety with the existing V2 panel
- unavailable rendering for unsafe normalized payloads

Existing frontend tests continue to cover:

- Phase 9 client normalization
- certified V2 frontend API behavior
- certified V2 rendering behavior
- V1 candidate evaluation rendering behavior

## Governance Preservation

Phase 10 explicitly preserves:

```text
ranking_applied === false
selection_made === false
```

Phase 10 does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

The UI does not sort pitchers, choose pitchers, label pitchers as better than
others, or instruct the user who to use. Team Operations Bullpen Readiness
remains a team-level and context-level surface only.

## Validation Record

Required Phase 10 validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-10-dashboard-ui
Result: 299 passed, 0 failed.

cd frontend
npm test
Result: 101 passed, 0 failed.

git diff --check
Result: Passed with line-ending warnings only.

git diff --cached --check
Result: Passed after targeted Phase 10 staging.
```

Root `npm test` is not required when no root `package.json` exists.

## Non-Goals

Phase 10 does not:

- certify the readiness route for production
- certify the readiness UI for production
- expose a public production surface
- alter backend Team Operations readiness assembly
- alter backend route validation
- alter the Recommendation Engine V2 contract
- alter fatigue scoring
- alter availability classification
- add pitcher-level guidance
- add ranking, selection, prediction, or recommendation behavior

## Remaining Risks

| Risk | Status | Mitigation |
| --- | --- | --- |
| Internal UI could be mistaken for production-certified | Reduced | The panel visibly displays `Internal / Non-production / Uncertified`. |
| Real readiness payloads may be unavailable because source evidence is missing or unsafe | Expected | The panel renders unavailable and refused states without treating them as valid context. |
| Future UI additions could imply pitcher priority | Open | Keep future components summary-first, team-level, and covered by prohibited-language/rendering tests. |
| Production certification evidence is not complete | Open | Phase 10 intentionally does not grant certification or rollout approval. |

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 11 Team Operations Bullpen Readiness Dashboard UI Certification Readiness Review
```

The next milestone should review the new Dashboard panel, frontend rendering
tests, internal status labeling, accessibility behavior, metadata visibility,
refused/degraded/unavailable state handling, and V2 regression safety before
any production certification or rollout decision is considered.
