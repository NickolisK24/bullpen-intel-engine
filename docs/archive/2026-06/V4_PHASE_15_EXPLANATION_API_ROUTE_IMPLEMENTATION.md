# BaseballOS V4 Phase 15 - Explanation API Route Implementation

## Phase Status

Phase status:

```text
V4_PHASE_15_EXPLANATION_API_ROUTE_IMPLEMENTATION_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
BACKEND_ROUTES_IMPLEMENTED
INTERNAL_UNCERTIFIED_ROUTE_STATUS
NO_FRONTEND_EXPOSURE
NO_DASHBOARD_EXPOSURE
```

Recommended next milestone:

```text
V4 Phase 16 - Explanation API Route Certification Readiness Review
```

Phase 15 implements governed backend API routes for certified V4 explanation
types only. The routes expose certified explanation objects for Availability
Explanations and Team Operations Readiness Explanations. This phase does not
implement frontend UI, dashboard rendering, database persistence, rollout
approval, source-engine behavior changes, or Recommendation Engine behavior.

## Routes Implemented

The implemented backend routes are:

```text
GET /api/explanations/availability/<pitcher_id>
GET /api/explanations/team-readiness
GET /api/explanations/team-readiness/<scope>
GET /api/explanations/<explanation_type>
```

Route registration is added through the Flask application blueprint setup.

The route family is marked:

```text
route_status = "internal_uncertified_route"
```

The route status intentionally keeps explanation API exposure separate from
production certification or frontend availability.

## Certified Scopes Exposed

Certified explanation types exposed:

- `availability_explanation`
- `team_readiness_explanation`

Availability explanation scope exposed:

- `availability_state`

Team Operations Readiness explanation scopes exposed:

- `readiness_state`
- `workload_state`
- `coverage_state`
- `freshness_state`
- `trust_state`

Unsupported or uncertified explanation types fail closed. Unsupported or
uncertified readiness scopes fail closed.

## Response Envelopes

Successful responses use a shared governed envelope:

```json
{
  "status": "ok",
  "explanation_type": "availability_explanation",
  "certification_status": "certified_with_non_blocking_observations",
  "route_status": "internal_uncertified_route",
  "explanation": {},
  "governance": {
    "ranking_applied": false,
    "selection_made": false,
    "recommendation_made": false,
    "prediction_made": false,
    "decision_scope": "explanation_only",
    "advice_scope": "none"
  }
}
```

For successful responses, governance is available inside the explanation object
and mirrored at the envelope level.

Fail-closed responses use a shared unavailable envelope:

```json
{
  "status": "unavailable",
  "explanation_type": "team_readiness_explanation",
  "certification_status": "certified_with_non_blocking_observations",
  "route_status": "internal_uncertified_route",
  "explanation": null,
  "limitations": [],
  "refusal": {
    "refused": true,
    "reason_code": "unsupported_scope",
    "summary": "The requested readiness explanation scope is not certified for API exposure."
  },
  "governance": {
    "ranking_applied": false,
    "selection_made": false,
    "recommendation_made": false,
    "prediction_made": false,
    "decision_scope": "explanation_only",
    "advice_scope": "none"
  }
}
```

Fail-closed responses do not fabricate evidence.

## Availability Explanation Route

The availability route accepts a pitcher identifier:

```text
GET /api/explanations/availability/<pitcher_id>
```

The route:

- loads the pitcher by the existing backend identifier
- loads latest fatigue evidence for that pitcher
- uses existing game-log evidence and the existing Availability Engine
  classifier
- builds a certified V4 Availability Explanation
- returns the governed shared response envelope

The route fails closed when:

- the pitcher is unknown
- required fatigue evidence is missing
- request parameters are unsupported
- request parameters contain prohibited query intent
- builder validation cannot safely produce an explanation

The route does not modify availability thresholds, fatigue calculations, status
assignment, source data, or existing availability responses.

## Team Readiness Explanation Route

The Team Operations Readiness routes are:

```text
GET /api/explanations/team-readiness
GET /api/explanations/team-readiness/<scope>
```

The default scope is:

```text
readiness_state
```

The routes:

- reuse existing Team Operations readiness source assembly
- preserve existing readiness calculations and response behavior
- build certified V4 Team Operations Readiness Explanations
- enforce the certified readiness scope allowlist
- return the governed shared response envelope

The route supports safe `team_id`, `team_abbreviation`, and `scope` request
parameters where applicable.

The route fails closed when:

- readiness records are unavailable
- `team_id` is malformed
- a requested scope is unsupported or uncertified
- request parameters are unsupported
- request parameters contain prohibited query intent
- the source readiness payload fails closed
- builder validation cannot safely produce an explanation

## Certification Boundary

Phase 15 exposes only certified V4 explanation types through backend routes:

- Availability Explanations certified in V4 Phase 8
- Team Operations Readiness Explanations certified in V4 Phase 13

The route implementation does not expose:

- Recommendation Explanations
- Risk Distribution Explanations
- explanation UI surfaces
- future readiness expansion scopes
- placeholder explanation types
- uncertified explanation types

Unsupported explanation types return a governed fail-closed response with:

```text
reason_code = "uncertified_explanation_type"
```

Unsupported readiness scopes return a governed fail-closed response with:

```text
reason_code = "unsupported_scope"
```

## Governance Preservation

Every successful response and every fail-closed response preserves:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The route implementation does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation

The explanation routes may expose why an existing governed state exists. They
may not tell the user what to do.

## Fail-Closed Behavior

Fail-closed responses are used for:

- unknown pitcher
- missing source data
- unsupported request parameters
- prohibited query intent
- unsupported readiness scope
- uncertified explanation type
- source input assembly failure
- source payload refusal
- builder validation failure

Fail-closed responses include:

- `status: "unavailable"`
- `explanation: null`
- visible limitation metadata
- visible refusal metadata
- governed defaults at the envelope level

Fail-closed responses do not include recommendation, selection, ranking,
prediction, matchup, or decision fields.

## Tests Added

The focused route test file is:

- `backend/tests/test_v4_explanation_api_routes.py`

The tests cover:

- successful availability explanation response
- unknown pitcher fail-closed response
- missing availability source data fail-closed response
- prohibited availability query intent
- successful Team Operations readiness explanation response
- successful certified readiness scope response
- unsupported readiness scope fail-closed response
- missing Team Operations readiness records fail-closed response
- prohibited Team Operations readiness query intent
- uncertified explanation type fail-closed response
- deterministic repeated route responses
- envelope-level governance
- absence of prohibited ranking, selection, recommendation, prediction,
  matchup, and decision fields

Existing backend test coverage remains responsible for preserving source engine
behavior, including Availability Engine, Team Operations Readiness, and
Recommendation Engine behavior.

## Behavior Preservation

Phase 15 does not change:

- availability thresholds
- availability calculations
- fatigue calculations
- readiness calculations
- readiness status assignment
- Recommendation Engine behavior
- existing dashboard behavior
- frontend behavior
- database schema

The route implementation reuses existing source outputs and adapters. It does
not rewrite the source engines.

## Intentionally Unimplemented

Phase 15 intentionally does not implement:

- frontend explanation client
- dashboard explanation display
- explanation route production certification
- explanation route rollout approval
- Recommendation Explanations
- Risk Distribution Explanations
- explanation persistence
- route monitoring artifacts
- route certification-readiness review

## Recommended Next Milestone

The recommended next milestone is:

```text
V4 Phase 16 - Explanation API Route Certification Readiness Review
```

Phase 16 should review whether the newly implemented backend explanation routes
are ready for formal certification review before any frontend or dashboard
exposure is planned.
