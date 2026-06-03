# BaseballOS V3 Phase 6 - Team Operations Bullpen Readiness Internal API Route Integration

## Decision

Status:

```text
V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION_COMPLETE
```

Implemented internal route:

```text
GET /api/team-operations/bullpen-readiness
```

Route status:

```text
INTERNAL_NON_PRODUCTION_UNCERTIFIED
```

Recommended next milestone:

```text
BaseballOS V3 Phase 7 Team Operations Bullpen Readiness Route Certification Readiness Review
```

V3 Phase 6 integrates the Phase 5 Team Operations Bullpen Readiness backend
domain foundation behind a Flask route so the readiness payload can be
exercised through API request handling. The route is explicitly internal,
non-production, and uncertified. It does not create frontend exposure and does
not change the certified Recommendation Engine V2 contract.

## Phase Purpose

The purpose of Phase 6 is to validate route-level behavior before public or
frontend integration.

This phase verifies:

- Flask route registration
- allowed query handling
- unsafe query refusal
- unsupported query refusal
- source input assembly
- trust metadata assembly
- freshness metadata assembly
- refusal metadata preservation
- fail-closed response behavior
- governance metadata preservation
- route-level internal status metadata

## Scope

In scope:

- internal Team Operations route registration
- route-level request validation
- internal source input assembly from existing fatigue, availability, and sync
  metadata sources
- route metadata marking the surface internal, non-production, and uncertified
- route tests
- domain test regression coverage
- documentation updates

Out of scope:

- frontend UI implementation
- frontend client integration
- production certification
- public rollout approval
- certified Recommendation Engine V2 contract changes
- Recommendation Engine V1 behavior changes
- fatigue formula changes
- availability threshold changes
- database schema changes
- new external data sources
- pitcher ranking
- pitcher selection
- pitcher recommendation
- matchup advice
- prediction behavior

## Files Created/Modified

Created:

- `backend/api/team_operations.py`
- `backend/tests/test_team_operations_bullpen_readiness_api.py`
- `docs/V3_PHASE_6_TEAM_OPERATIONS_BULLPEN_READINESS_INTERNAL_API_ROUTE_INTEGRATION.md`

Modified:

- `backend/app.py`
- `README.md`
- `docs/PROJECT_STATE_2026_06.md`
- `docs/V3_PHASE_5_TEAM_OPERATIONS_BULLPEN_READINESS_BACKEND_DOMAIN_FOUNDATION.md`

No frontend runtime files, generated frontend files, dependency folders,
Recommendation Engine V2 contract files, fatigue formula files, or database
schema files are modified by this phase.

## Internal Route Summary

Phase 6 registers:

```text
GET /api/team-operations/bullpen-readiness
```

The route is registered through:

```text
backend/api/team_operations.py
backend/app.py
```

The route calls the Phase 5 domain entrypoint:

```text
assemble_bullpen_readiness(...)
```

The route response includes route metadata:

```json
{
  "exposure": "internal",
  "production_status": "non_production",
  "certification_status": "uncertified",
  "public_certified": false,
  "frontend_exposure": false
}
```

This metadata is required until a later certification and rollout phase
changes the lifecycle status.

## Request Validation Summary

Allowed query parameters:

- `team_id`
- `team_abbreviation`
- `include_details`

Unsupported query parameters fail closed with:

```text
unsupported_request_parameter
```

Prohibited query intent fails closed with:

```text
forbidden_request_parameter
```

Prohibited query intent includes:

- `best`
- `recommend`
- `rank`
- `select`
- `matchup`
- `predict`
- `save`
- `injury`
- `performance`

The route does not accept controls that change ordering, selection,
recommendation behavior, matchup behavior, or prediction behavior.

## Response Contract Summary

The response preserves the Phase 5 domain payload plus route metadata.

The route response includes:

- contract identity
- internal route metadata
- readiness status
- constraints
- workload pressure
- availability distribution
- coverage inventory
- handedness coverage
- explanations
- limitations
- trust metadata
- freshness metadata
- refusal metadata
- fail-closed metadata
- governance metadata

The response remains team-level or context-level only.

## Refusal/Fail-Closed Behavior

The route fails closed when:

- a prohibited request parameter is present
- an unsupported request parameter is present
- `team_id` is malformed
- `include_details` is malformed
- source inputs cannot be safely assembled
- no current source inputs are available
- required trust metadata is missing
- required freshness metadata is missing
- the Phase 5 domain layer refuses assembly

Unsafe and unsupported requests return governed refusal payloads with
fail-closed metadata. Missing source input or metadata failures return governed
refusal payloads without exposing fallback readiness claims.

## Governance Preservation

Phase 6 explicitly preserves:

```text
ranking_applied === false
selection_made === false
```

It does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- best behavior
- preferred behavior
- recommended behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice

The route does not modify:

```text
GET /api/recommendations/v2/bullpen-state
```

The certified Recommendation Engine V2 route remains separate and unchanged.

## Testing Coverage

Backend route tests are added in:

```text
backend/tests/test_team_operations_bullpen_readiness_api.py
```

The tests verify:

- the route exists and returns a governed payload
- route metadata marks the surface internal, non-production, and uncertified
- governance flags remain false
- prohibited query parameters are refused
- unsupported query parameters are refused
- missing freshness inputs fail closed
- missing trust inputs fail closed
- response contains no ranking fields
- response contains no selection fields
- response contains no best, preferred, or recommended labels

Existing Phase 5 domain tests remain in:

```text
backend/tests/test_team_operations_bullpen_readiness.py
```

The full backend suite remains the regression proof that certified V2
recommendation behavior still passes.

## Validation

Required validation for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-6-readiness-api

cd frontend
npm test

git diff --check
git diff --cached --check
```

Root `npm test` is not required for Phase 6. If no root `package.json` exists,
that is expected and is not a project failure.

## Non-Goals

Phase 6 does not:

- certify the Team Operations readiness route for production
- expose frontend UI
- add frontend client code
- change the certified Recommendation Engine V2 route
- change Recommendation Engine V1 behavior
- change fatigue formulas
- change availability thresholds
- add new data sources
- add pitcher-level advice
- add matchup advice
- add ranking, selection, recommendation, or prediction behavior

## Remaining Risks

Remaining risks:

- The route is internal and uncertified.
- Public/frontend integration still requires certification readiness review.
- Route monitoring artifacts are not yet defined for production use.
- Accessibility and frontend rendering remain future work.
- Query validation covers current Phase 6 inputs only and may need expansion
  before public rollout.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 7 Team Operations Bullpen Readiness Route Certification Readiness Review
```

The next milestone should review route-level evidence, request validation,
response serialization, fail-closed behavior, and V2 regression safety before
any frontend integration or production certification work begins.
