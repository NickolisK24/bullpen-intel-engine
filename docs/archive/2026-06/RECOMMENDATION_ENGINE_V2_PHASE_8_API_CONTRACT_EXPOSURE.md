# Recommendation Engine V2 Phase 8 API Contract Exposure

## Status

Recommendation Engine V2 Phase 8 API Contract Exposure is complete.

This phase exposes the approved backend V2 API contract through a single
backend endpoint. It uses the V2 domain, context assembly, neutral
intelligence, inventory visibility, team bullpen context, trust metadata, and
refusal/fail-closed systems completed in Phases 1 through 7.

Phase 8 does not create frontend behavior, modify frontend files, rank
pitchers, select pitchers, predict outcomes, or change Recommendation Engine
V1.

## Endpoint Added

```text
GET /api/recommendations/v2/bullpen-state
```

Supported query parameters:

- `team_id`: optional team filter
- `limit`: optional maximum number of source records, capped at the backend
  contract limit

The endpoint is registered under the existing recommendations blueprint.

## Response Contract

The endpoint returns the approved V2 bullpen-state contract shape with:

- `scope`
- `ranking_applied`
- `selection_made`
- `confidence`
- `data_state`
- `generated_at`
- `freshness`
- `limitations`
- `explanations`
- `refusal_reasons`
- `fail_closed`
- `trust_metadata`
- `bullpen_state`

When source evidence is safe and sufficient, `bullpen_state` contains:

- descriptive bullpen status
- descriptive stress level
- readiness summary
- inventory summary
- neutral candidate groups
- team bullpen context
- trust metadata

When source evidence is critically missing or governance-unsafe,
`bullpen_state` is `null` and the response preserves explicit fail-closed,
trust, freshness, limitation, explanation, and refusal metadata.

## Source Evidence

The endpoint builds V2 API output from existing backend evidence:

- latest fatigue rows
- current availability classifications
- workload inputs used by the Availability Engine
- freshness/data-state metadata
- source reasons and limitations

Candidate group ordering and inventory member ordering preserve the neutral
source order produced by the backend. The ordering policy is non-ranking.

## Governance Compliance

Every V2 API response preserves:

```text
ranking_applied = false
selection_made = false
```

The endpoint does not expose:

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

Unsafe request fields or source fields fail closed rather than being silently
accepted.

## Fail-Closed Behavior

The endpoint returns explicit refusal/fail-closed metadata for:

- missing evidence
- stale evidence
- incomplete evidence
- unsupported evidence
- malformed evidence
- missing trust metadata
- missing freshness metadata
- missing explanation metadata
- missing limitation metadata
- unsafe ranking fields
- unsafe selection fields
- unsafe prediction fields

Fail-closed responses preserve top-level metadata and do not fabricate trust,
freshness, explanation, or limitation data.

## Test Coverage

Phase 8 test coverage is implemented in:

- `backend/tests/test_recommendation_v2_api_contract.py`

Coverage includes:

- successful V2 API response shape
- top-level no-ranking metadata
- top-level no-selection metadata
- trust metadata exposure
- freshness metadata exposure
- limitation exposure
- explanation exposure
- refusal/fail-closed metadata exposure
- forbidden field checks
- stale evidence fail-closed/degraded API behavior
- missing evidence fail-closed API behavior
- unsafe request field fail-closed API behavior
- Recommendation Engine V1 API regression safety

## V1 Preservation

Recommendation Engine V1 remains unchanged.

This phase did not modify:

- V1 recommendation engine behavior
- V1 recommendation API route semantics
- V1 candidate evaluation behavior
- V1 response contract
- V1 frontend behavior

The V1 guarantees remain active:

```text
ranking_applied = false
selection_made = false
```

## Phase 9 Completion Boundary

Recommendation Engine V2 Phase 9 adds frontend client consumption of the V2
endpoint while preserving trust metadata, freshness metadata, refusal metadata,
limitations, explanations, no-ranking, and no-selection guarantees.

The Phase 9 completion record is:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_9_FRONTEND_CLIENT.md`

Phase 9 does not create frontend UI support or user-facing V2 display behavior.
