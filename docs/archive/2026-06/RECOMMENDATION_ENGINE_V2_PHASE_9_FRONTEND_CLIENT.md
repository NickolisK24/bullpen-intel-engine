# Recommendation Engine V2 Phase 9 Frontend Client Integration

## Status

Recommendation Engine V2 Phase 9 Frontend Client Integration is complete.

This phase adds frontend client support for the approved V2 endpoint:

```text
GET /api/recommendations/v2/bullpen-state
```

Phase 9 does not create new UI panels, modify V2 rendering behavior, rank
pitchers, select pitchers, predict outcomes, change backend V2 behavior, or
change Recommendation Engine V1.

## Frontend Client Path

The V2 frontend client integration is implemented in:

- `frontend/src/utils/api.js`

The client exports:

- `RECOMMENDATION_V2_BULLPEN_STATE_ROUTE`
- `getRecommendationV2BullpenState`
- `normalizeRecommendationV2BullpenStateResponse`

`getRecommendationV2BullpenState` consumes the approved endpoint and returns a
normalized contract object for future rendering layers.

## Contract Safety Behavior

The client preserves the backend V2 response contract instead of converting it
into a recommendation UI model.

The normalized contract object exposes:

- endpoint path
- contract state
- no-ranking and no-selection governance flags
- missing required fields
- malformed fields
- forbidden ranking/selection/prediction field paths
- scope
- confidence
- data state
- generated timestamp
- freshness metadata
- limitation metadata
- explanation metadata
- refusal metadata
- trust metadata
- bullpen state when the contract is safe

The client does not fabricate confidence, freshness, limitations,
explanations, refusal reasons, trust metadata, or governance flags.

## Contract States

The client represents V2 responses as one of three states:

- `available`: required contract fields are present, governance flags are safe,
  no forbidden fields are present, and the response is not fail-closed.
- `fail_closed`: required contract fields are present, governance flags are
  safe, no forbidden fields are present, and the backend explicitly returned a
  fail-closed response.
- `unavailable`: required fields are missing, malformed, governance-unsafe, or
  forbidden ranking/selection/prediction fields are present.

Unavailable responses suppress `bullpenState` for future rendering layers
rather than presenting unsafe output as valid.

## Governance Compliance

The frontend client preserves:

```text
ranking_applied === false
selection_made === false
```

The client does not introduce:

- ranked candidates
- selected pitcher fields
- recommended pitcher fields
- best pitcher fields
- preferred pitcher fields
- winner fields
- score-ordered lists
- prediction fields
- injury forecasts
- save forecasts
- game outcome forecasts

Forbidden response fields are detected and marked unavailable instead of being
silently propagated into future UI state.

## No UI Exposure

Phase 9 does not add:

- V2 React panels
- V2 route changes
- V2 visible dashboard behavior
- ranking UI
- selection UI
- prediction UI
- best/preferred/recommended pitcher UI

Future V2 rendering remains a separate governance milestone.

## Test Coverage

Phase 9 frontend test coverage is implemented in:

- `frontend/tests/recommendationV2Api.test.mjs`

Coverage includes:

- successful V2 API client response handling
- `ranking_applied === false`
- `selection_made === false`
- trust metadata handling
- freshness metadata handling
- limitation handling
- explanation handling
- refusal/fail-closed metadata handling
- missing governance field handling
- forbidden ranking field handling
- forbidden selection field handling
- endpoint path and query parameter consumption

## V1 Preservation

Recommendation Engine V1 remains unchanged.

This phase did not modify:

- V1 recommendation engine behavior
- V1 recommendation API route semantics
- V1 candidate evaluation behavior
- V1 response contract
- V1 frontend rendering behavior

The V1 guarantees remain active:

```text
ranking_applied = false
selection_made = false
```

## Phase 10 Completion Boundary

Recommendation Engine V2 Phase 10 adds governed frontend rendering while
preserving trust metadata, freshness metadata, refusal metadata, limitations,
explanations, no-ranking, and no-selection guarantees.

The Phase 10 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_10_GOVERNED_FRONTEND_RENDERING.md`

Phase 10 does not create ranking UI, selection UI, prediction UI, or
Recommendation Engine V1 behavior changes.
