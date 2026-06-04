# BaseballOS V5 Phase 6 - Observation API Surface

## Phase Status

Phase status:

```text
V5_PHASE_6_OBSERVATION_API_SURFACE_COMPLETE
```

Capability track:

```text
V5_BULLPEN_INTELLIGENCE_SURFACE
```

Implementation status:

```text
BACKEND_READ_ONLY_OBSERVATION_API_ONLY
```

V5 Phase 6 exposes governed Bullpen Intelligence observations through a
backend read-only API surface. The route uses deterministic supplied-state
assembly through the Phase 5 builders and Phase 4 contracts. It does not add
frontend UI, database migrations, live MLB/runtime integration, ranking,
selection, prediction, matchup advice, pitcher advice, or automated
decision-making.

## 1. Implemented Scope

Phase 6 adds:

- `backend/api/observations.py`
- `backend/observations/api_assembly.py`
- `backend/tests/test_observation_api.py`

It also updates application registration:

- `backend/app.py`

Implemented routes:

```text
GET /api/observations
POST /api/observations/preview
```

`GET /api/observations` returns deterministic sample-state observations for
the governed response contract.

`POST /api/observations/preview` accepts explicit supplied state for validation
preview. It is read-only and does not persist, query, or integrate runtime
data.

## 2. Response Contract

The API response includes the serialized `ObservationCollection` fields:

- `collection_id`
- `generated_at`
- `observation_count`
- `observations`
- `freshness`
- `confidence`
- `limitations`
- `suppressed_count`
- `suppression_reasons`
- `ranking_applied`
- `selection_made`

The route also includes:

- `status`
- `trust_status`
- `route_metadata`

Each observation preserves:

- `observation_id`
- `observation_type`
- `family`
- `severity`
- `title`
- `summary`
- `evidence`
- `limitations`
- `confidence`
- `freshness`
- `trust_status`
- `explanation_reference`
- `ranking_applied`
- `selection_made`

## 3. Read-Only Boundary

The Phase 6 API surface is backend-only and read-only.

It does not:

- write data
- query persistence
- call external services
- integrate live runtime data
- require database access
- expose frontend UI

The deterministic sequence is the V5 family sequence:

```text
inventory
readiness
workload_pressure
freshness
trust
```

This sequence is contract presentation order only. It is not pitcher ranking,
arm ordering, selection, or decision priority.

## 4. Fail-Closed Behavior

The API fails closed when:

- builder input is invalid
- required evidence is missing
- freshness metadata is missing
- trust status is missing
- confidence metadata is missing
- contract validation fails
- prohibited language is detected
- unsupported or prohibited request parameters are supplied

Fail-closed responses return:

- empty `observations`
- `status: fail_closed`
- `trust_status: fail_closed`
- safe `limitations`
- safe `suppression_reasons`
- `ranking_applied: false`
- `selection_made: false`

Unsafe partial observations are not returned.

## 5. Governance Guarantees

Every response preserves:

```text
ranking_applied === false
selection_made === false
```

API output remains:

```text
OBSERVATIONAL
DESCRIPTIVE
TRUST_AWARE
EXPLAINABLE
GOVERNED
```

API output does not become:

- ranking
- selection
- prediction
- pitcher advice
- matchup advice
- automated decision-making

## 6. Test Coverage

Phase 6 tests verify:

- API returns a governed observation collection
- top-level `ranking_applied` is false
- top-level `selection_made` is false
- each observation preserves `ranking_applied: false`
- each observation preserves `selection_made: false`
- prohibited language cannot be returned
- invalid or incomplete supplied state fails closed
- response serializes evidence
- response serializes limitations
- response serializes trust, freshness, and confidence metadata
- the route does not require database access
- the route does not call external services

## 7. Unauthorized Scope

Phase 6 does not authorize:

- frontend UI
- dashboard integration
- database migrations
- live runtime integration
- runtime observation generation from MLB data
- fatigue calculation changes
- availability calculation changes
- Recommendation Engine behavior changes
- Team Operations Readiness behavior changes
- explanation behavior changes
- trust logic changes
- freshness logic changes
- ranking
- selection
- pitcher recommendations
- matchup advice
- best-arm language
- closer/setup/role advice
- prediction
- automated decision-making

## 8. Next Phase Boundary

Recommended next milestone:

```text
V5_PHASE_7_FRONTEND_INTELLIGENCE_SURFACE
```

Phase 7 may add frontend UI consuming the governed API if separately
authorized. Phase 6 does not add frontend UI.

## Final Boundary

This document certifies only the V5 Phase 6 backend read-only observation API
surface.

It does not certify frontend surfaces, live runtime observations, controlled
rollout, production rollout, ranking, selection, prediction, pitcher
recommendations, matchup advice, best-arm language, role advice, or automated
decision-making.
