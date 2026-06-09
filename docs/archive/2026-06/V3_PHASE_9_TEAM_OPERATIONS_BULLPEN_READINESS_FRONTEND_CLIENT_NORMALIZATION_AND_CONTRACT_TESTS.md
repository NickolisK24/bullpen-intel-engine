# BaseballOS V3 Phase 9 - Team Operations Bullpen Readiness Frontend Client Normalization and Contract Tests

## Decision

Phase 9 decision:

```text
V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS_COMPLETE
DASHBOARD_UI_IMPLEMENTATION = NOT_STARTED
PRODUCTION_CERTIFICATION = NOT_GRANTED
INTERNAL_ROUTE_STATUS = INTERNAL_NON_PRODUCTION_UNCERTIFIED
```

Phase 9 adds frontend client/API normalization and focused contract tests for
the internal Team Operations Bullpen Readiness route. It does not add Dashboard
UI, public exposure, route certification, or Recommendation Engine V2 contract
changes.

## Phase Purpose

BaseballOS V3 Phase 9 creates the frontend client normalization layer needed
before any Dashboard UI consumes Team Operations Bullpen Readiness.

The phase proves that frontend code can safely normalize:

- successful readiness payloads
- degraded readiness payloads
- refused or fail-closed readiness payloads
- missing required metadata
- malformed governance metadata
- unknown readiness vocabulary
- internal, non-production, uncertified route metadata

The output is a stable frontend-friendly contract surface for future UI work.

## Scope

In scope:

- frontend API route constant for `/api/team-operations/bullpen-readiness`
- frontend getter for the internal readiness route
- frontend normalizer for the route payload
- contract-state handling for available, degraded, refused, and unavailable
  client states
- trust, freshness, refusal, fail-closed, route, and governance metadata
  preservation
- frontend contract tests for safe, degraded, refused, missing, malformed, and
  unknown payloads

Out of scope:

- Dashboard UI implementation
- new Dashboard route calls
- CSS or component changes
- backend route changes
- Recommendation Engine V2 contract changes
- public route certification
- production rollout
- ranking, selection, prediction, or pitcher-level advice

## Files Created/Modified

Created:

- `docs/V3_PHASE_9_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_CLIENT_NORMALIZATION_AND_CONTRACT_TESTS.md`
- `frontend/tests/teamOperationsBullpenReadinessApi.test.mjs`

Modified:

- `frontend/src/utils/api.js`
- `README.md`
- `docs/PROJECT_STATE_2026_06.md`
- `docs/V3_PHASE_8_TEAM_OPERATIONS_BULLPEN_READINESS_FRONTEND_INTEGRATION_PLAN.md`

## Client Normalization Summary

Phase 9 adds:

- `TEAM_OPERATIONS_BULLPEN_READINESS_ROUTE`
- `getTeamOperationsBullpenReadiness(params)`
- `normalizeTeamOperationsBullpenReadinessResponse(response)`

The normalizer returns a stable frontend view model with:

- `contractState`
- `sourceContractState`
- `isContractSafe`
- `isDegraded`
- `isRefused`
- `isFailClosed`
- `isInternal`
- `isInternalUncertified`
- `governance`
- `routeStatus`
- `missingFields`
- `malformedFields`
- `forbiddenFieldPaths`
- `forbiddenTextPaths`
- `unknownContractState`
- `unknownReadinessStatus`
- normalized readiness fields
- trust metadata
- freshness metadata
- refusal metadata
- fail-closed metadata
- internal route metadata

The normalized readiness fields expose `readinessStatus` and
`readinessSummary` from the implemented nested backend readiness contract:

```text
readiness.status_code
readiness.summary
```

The normalizer does not expose a raw backend response field.

## Contract Handling Summary

The client accepts only governed contract states:

- `available`
- `degraded`
- `refused`
- `unavailable`

The client accepts only governed readiness status vocabulary already defined by
the Team Operations contract, with client compatibility for the documented
planning vocabulary:

- `operationally_stable`
- `operationally_constrained`
- `operationally_stressed`
- `coverage_limited`
- `data_limited`
- `refused`

Unknown contract states or unknown readiness statuses make the normalized
payload unavailable rather than silently valid.

The client preserves the route's internal status:

```text
exposure = internal
production_status = non_production
certification_status = uncertified
public_certified = false
frontend_exposure = false
```

If the route metadata does not preserve those values, the normalized payload is
not treated as contract-safe.

## Refused/Degraded Handling Summary

Degraded payloads remain degraded when:

- the backend contract state is `degraded`
- the route remains internal, non-production, and uncertified
- required trust metadata is present
- required freshness metadata is present
- required governance metadata is safe
- no prohibited ranking, selection, prediction, or decision-language fields are
  present

Refused or fail-closed payloads remain contract-safe only when they retain:

- refusal metadata
- fail-closed metadata
- trust metadata
- freshness metadata
- route metadata
- governance metadata

Missing or malformed required fields produce:

```text
contractState = unavailable
isContractSafe = false
```

## Governance Preservation

Phase 9 explicitly preserves:

```text
ranking_applied === false
selection_made === false
```

The frontend normalizer requires the top-level and trust metadata governance
flags to remain false. If those fields are missing, malformed, or unsafe, the
normalized payload is unavailable.

Phase 9 does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- best/preferred/recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

The client also rejects prohibited field names and prohibited display-language
terms in normalized readiness payloads before future UI rendering can treat the
payload as safe.

## Testing Coverage

Phase 9 adds focused frontend tests for:

- successful response normalization
- degraded response normalization
- refused/fail-closed response normalization
- missing trust metadata handling
- missing freshness metadata handling
- missing governance metadata handling
- malformed governance metadata handling
- unknown readiness status handling
- internal, non-production, uncertified metadata preservation
- absence of best/preferred/recommended language introduced by normalization
- route getter behavior for `/api/team-operations/bullpen-readiness`

The existing V2 frontend API tests continue to cover the certified
Recommendation Engine V2 client contract.

## Validation Record

Required Phase 9 validation:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-9-client-normalization
Result: 299 passed, 0 failed.

cd frontend
npm test
Result: 89 passed, 0 failed.

git diff --check
Result: Passed with line-ending warnings only.

git diff --cached --check
Result: Passed after targeted Phase 9 staging.
```

Root `npm test` is not required when no root `package.json` exists.

## Non-Goals

Phase 9 does not:

- implement the Dashboard readiness panel
- render readiness output to users
- add component state
- add CSS
- promote the internal route
- certify the route for production
- alter backend Team Operations readiness behavior
- alter Recommendation Engine V2 behavior
- alter fatigue formulas
- alter ranking, selection, prediction, or recommendation behavior

## Remaining Risks

| Risk | Status | Mitigation |
| --- | --- | --- |
| Future UI could visually imply pitcher priority | Still open | Keep Phase 10 UI bounded to summary-first team-level rendering and prohibit priority layouts. |
| Backend and frontend vocabulary can drift | Reduced | Phase 9 validates known vocabulary and marks unknown statuses unavailable. |
| Internal route could be mistaken for production | Reduced | Route metadata is preserved and required for contract-safe normalization. |
| Missing metadata could be hidden by the client | Reduced | Missing trust, freshness, route, or governance metadata makes the view unavailable. |
| V2 frontend contract could regress | Mitigated | Existing V2 frontend API tests still pass. |

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 10 Team Operations Bullpen Readiness Dashboard UI Integration
```

The next milestone should implement a bounded Dashboard UI surface that consumes
only the normalized Phase 9 client payload. It should preserve internal,
non-production, uncertified route status and must not introduce production
certification, pitcher ranking, pitcher selection, pitcher recommendation,
prediction, matchup advice, or hidden priority ordering.

## Phase 10 Follow-Up

BaseballOS V3 Phase 10 Team Operations Bullpen Readiness Dashboard UI
Integration is complete.

The Phase 10 record is:

- `docs/V3_PHASE_10_TEAM_OPERATIONS_BULLPEN_READINESS_DASHBOARD_UI_INTEGRATION.md`

Phase 10 consumes the normalized Phase 9 client payload in a governed
Dashboard panel. The panel keeps the route visibly internal, non-production,
and uncertified, renders readiness as team-level context only, exposes
context/evidence/metadata sections on demand, and adds frontend rendering
tests for successful, degraded, refused, unavailable, metadata, and governance
states.

Phase 10 preserves:

```text
ranking_applied === false
selection_made === false
```

Phase 10 does not introduce ranking behavior, selection behavior, prediction
behavior, best/preferred/recommended behavior, hidden priority ordering,
pitcher-level advice, matchup advice, public exposure, production
certification, production rollout, backend route changes, or Recommendation
Engine V2 contract changes.
