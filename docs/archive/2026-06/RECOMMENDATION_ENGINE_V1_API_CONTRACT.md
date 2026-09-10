# Recommendation Engine V1 API Contract

## 1. API Objective

This document defines the API contract for exposing Recommendation Engine V1
candidate-level output.

The contract does not authorize frontend UI, database schema changes,
multi-candidate ranking, scoring, or final pitcher selection.

The candidate API must expose the existing candidate-level recommendation
pipeline without weakening Recommendation Engine V1 policy:

- one candidate per evaluation
- deterministic gate, category, and builder output
- visible confidence, freshness, explanations, and limitations
- structured refusals when trusted inputs are insufficient
- `ranking_applied=false`
- `selection_made=false`

BaseballOS may say a candidate is eligible for policy-approved categories. It
must not claim that the candidate is the final best pitcher.

## 2. Explicit Non-Goals

This contract does not authorize:

- additional route implementation beyond the candidate contract
- frontend UI implementation
- database changes
- write endpoints
- team-level recommendations
- bullpen-level recommendations
- multi-candidate ranking
- cross-candidate comparison
- final best-pitcher selection
- scoring formulas
- matchup modeling
- injury, medical, illness, or team-reported availability conclusions
- performance forecasts
- save, hold, win, loss, or run-prevention projections
- private clubhouse, travel, warm-up, or manager-intent inference

The API contract is limited to candidate-level exposure of the already staged
Recommendation Engine V1 backend pipeline.

## 3. Route Candidate

Implemented route:

```text
POST /api/recommendations/candidate
```

Route intent:

- evaluate exactly one candidate
- delegate to `RecommendationEngine.recommend(candidate=...)`
- return the engine's structured recommendation or refusal result
- preserve all trust and governance metadata

Implementation surface:

- `backend/api/recommendations.py`
- registered under `/api/recommendations`

Deferred routes:

- team recommendation routes
- bullpen stress summary routes
- multi-candidate selection routes
- dashboard aggregation routes
- simulator routes

No route may implement recommendation policy inline. Route code should validate
request shape, call the recommendation engine, and serialize the engine result.

## 4. Request Shape

The request body should contain one candidate and optional request metadata.

```json
{
  "candidate": {
    "pitcher_id": 456,
    "pitcher_name": "Example Pitcher",
    "team_id": 123,
    "team_name": "Example Club",
    "availability": {
      "availability_status": "Available",
      "confidence": "high",
      "data_state": "fresh",
      "reasons": [
        "Workload signals are inside current availability limits."
      ],
      "limitations": [
        "Based on public workload data tracked by BaseballOS."
      ],
      "inputs": {
        "fatigue_score": 21.4,
        "fatigue_risk_level": "low",
        "pitches_yesterday": 0,
        "pitches_last_3_days": 12,
        "pitches_last_5_days": 20,
        "appearances_last_3_days": 1,
        "appearances_last_5_days": 2,
        "days_rest": 1,
        "latest_game_date": "2026-06-01"
      }
    },
    "metadata": {
      "freshness_state": "fresh",
      "data_through": "2026-06-01",
      "last_successful_sync": "2026-06-02T10:00:00Z",
      "latest_sync_status": "success"
    }
  },
  "request": {
    "category": "best_available_arm",
    "team_id": 123,
    "team_name": "Example Club",
    "request_id": "optional-client-id"
  }
}
```

Required candidate fields:

- `candidate.pitcher_id`
- `candidate.pitcher_name`
- `candidate.availability.availability_status`
- `candidate.availability.confidence`
- `candidate.availability.data_state`
- `candidate.availability.inputs`

Recommended candidate fields:

- `candidate.team_id`
- `candidate.team_name`
- `candidate.availability.reasons`
- `candidate.availability.limitations`
- `candidate.metadata.data_through`
- `candidate.metadata.last_successful_sync`
- `candidate.metadata.latest_sync_status`

The request must not contain multiple candidates. If multiple candidates are
provided by a future client, the route must refuse rather than rank or select.

## 5. Response Shape

The response should wrap the serialized recommendation result in stable `data`
and `meta` envelopes.

```json
{
  "data": {
    "outcome": "recommendation",
    "category": "best_available_arm",
    "category_code": "BEST_AVAILABLE_ARM",
    "candidate": {
      "pitcher_id": 456,
      "pitcher_name": "Example Pitcher",
      "team_id": 123,
      "team_name": "Example Club"
    },
    "confidence": {
      "level": "high",
      "level_code": "HIGH",
      "reasons": []
    },
    "freshness": {
      "state": "fresh",
      "state_code": "FRESH",
      "data_through": "2026-06-01",
      "last_successful_sync": "2026-06-02T10:00:00Z",
      "latest_sync_status": "success",
      "limitations": []
    },
    "availability": {
      "availability_status": "Available",
      "confidence": "high",
      "data_state": "fresh"
    },
    "assigned_categories": [],
    "blocked_categories": [],
    "explanations": [],
    "limitations": [],
    "alternatives": [],
    "refusal": null
  },
  "meta": {
    "policy": "recommendation_engine_v1",
    "policy_document": "docs/RECOMMENDATION_ENGINE_V1_POLICY.md",
    "contract_document": "docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md",
    "implementation_plan": "docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md",
    "response_mode": "candidate_category_eligibility",
    "ranking_applied": false,
    "selection_made": false,
    "selected_pitcher_id": null
  }
}
```

The exact serialization may adapt to current backend conventions, but the route
must preserve all fields required by this contract.

## 6. Success Response Example

Example response for a valid single candidate with fresh, high-confidence
availability:

```json
{
  "data": {
    "outcome": "recommendation",
    "outcome_code": "RECOMMENDATION",
    "category": "best_available_arm",
    "category_code": "BEST_AVAILABLE_ARM",
    "candidate": {
      "pitcher_id": 456,
      "pitcher_name": "Example Pitcher",
      "team_id": 123,
      "team_name": "Example Club"
    },
    "confidence": {
      "level": "high",
      "level_code": "HIGH",
      "reasons": []
    },
    "freshness": {
      "state": "fresh",
      "state_code": "FRESH",
      "data_through": "2026-06-01",
      "last_successful_sync": "2026-06-02T10:00:00Z",
      "latest_sync_status": "success",
      "limitations": []
    },
    "availability": {
      "availability_status": "Available",
      "confidence": "high",
      "data_state": "fresh"
    },
    "assigned_categories": [
      {
        "category": "best_available_arm",
        "category_code": "BEST_AVAILABLE_ARM"
      },
      {
        "category": "lowest_current_workload_risk",
        "category_code": "LOWEST_CURRENT_WORKLOAD_RISK"
      }
    ],
    "blocked_categories": [
      {
        "category": "freshest_high_leverage_arm",
        "category_code": "FRESHEST_HIGH_LEVERAGE_ARM",
        "reasons": [
          "missing_leverage_evidence"
        ]
      },
      {
        "category": "bullpen_stress_alert",
        "category_code": "BULLPEN_STRESS_ALERT",
        "reasons": [
          "requires_bullpen_context"
        ]
      }
    ],
    "explanations": [
      {
        "code": "eligibility_passed",
        "message": "Candidate passed Recommendation Engine V1 eligibility gates.",
        "details": {}
      },
      {
        "code": "best_available_arm_eligible",
        "message": "Candidate is eligible for Best Available Arm consideration. This is not final selection.",
        "details": {}
      },
      {
        "code": "builder_category_eligibility_only",
        "message": "Response builder composed category eligibility only; no ranking or final selection was applied.",
        "details": {}
      }
    ],
    "limitations": [
      {
        "code": "public_workload_data_only",
        "message": "Based on public workload data tracked by BaseballOS."
      },
      {
        "code": "not_performance_forecast",
        "message": "Not a performance forecast."
      },
      {
        "code": "user_decides",
        "message": "The user remains responsible for the final decision."
      },
      {
        "code": "builder_not_final_recommender",
        "message": "Builder output is candidate-level composition only; it does not rank, compare, or select pitchers."
      }
    ],
    "alternatives": [],
    "refusal": null
  },
  "meta": {
    "policy": "recommendation_engine_v1",
    "engine_version": "recommendation_engine_v1_builder",
    "policy_version": "recommendation_engine_v1",
    "contract_document": "docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md",
    "response_mode": "candidate_category_eligibility",
    "candidate_pipeline_enabled": true,
    "ranking_applied": false,
    "selection_made": false,
    "selected_pitcher_id": null
  }
}
```

This response does not mean BaseballOS selected the best pitcher. It means the
candidate is eligible for the listed categories under V1 policy.

## 7. Refusal Response Example

Example response for stale candidate data:

```json
{
  "data": {
    "outcome": "refusal",
    "outcome_code": "REFUSAL",
    "category": null,
    "category_code": null,
    "candidate": {
      "pitcher_id": 456,
      "pitcher_name": "Example Pitcher",
      "team_id": 123,
      "team_name": "Example Club"
    },
    "confidence": {
      "level": "high",
      "level_code": "HIGH",
      "reasons": [
        "stale_freshness"
      ]
    },
    "freshness": {
      "state": "stale",
      "state_code": "STALE",
      "data_through": "2026-05-30",
      "last_successful_sync": "2026-06-02T10:00:00Z",
      "latest_sync_status": "success",
      "limitations": [
        "stale_freshness"
      ]
    },
    "availability": {
      "availability_status": "Available",
      "confidence": "high",
      "data_state": "stale"
    },
    "assigned_categories": [],
    "blocked_categories": [
      {
        "category": "best_available_arm",
        "category_code": "BEST_AVAILABLE_ARM",
        "reasons": [
          "candidate_not_eligible",
          "candidate_excluded",
          "positive_category_requires_fresh_data"
        ]
      }
    ],
    "explanations": [
      {
        "code": "stale_freshness",
        "message": "Stale freshness fails closed.",
        "details": {}
      }
    ],
    "limitations": [
      {
        "code": "public_workload_data_only",
        "message": "Based on public workload data tracked by BaseballOS."
      },
      {
        "code": "candidate_excluded",
        "message": "Candidate is excluded because trusted recommendation inputs are insufficient or disqualifying."
      },
      {
        "code": "builder_not_final_recommender",
        "message": "Builder output is candidate-level composition only; it does not rank, compare, or select pitchers."
      }
    ],
    "alternatives": [],
    "refusal": {
      "reason": "stale_data",
      "reason_code": "STALE_DATA",
      "message": "BaseballOS cannot make a current recommendation because trusted current workload data is insufficient."
    }
  },
  "meta": {
    "policy": "recommendation_engine_v1",
    "contract_document": "docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md",
    "response_mode": "candidate_category_eligibility",
    "candidate_pipeline_enabled": true,
    "ranking_applied": false,
    "selection_made": false,
    "selected_pitcher_id": null
  }
}
```

Refusal is a normal trust outcome. It is not a server failure.

## 8. Required Trust Fields

Every response must include:

- `confidence.level`
- `confidence.level_code`
- `confidence.reasons`
- `availability.availability_status`
- `availability.confidence`
- `availability.data_state`
- `limitations`
- `meta.policy`
- `meta.policy_version`
- `meta.ranking_applied`
- `meta.selection_made`

The API must not return recommendation category output without confidence and
limitations.

## 9. Required Freshness Fields

Every response must include freshness state. The route should include
timestamps when available.

Required:

- `freshness.state`
- `freshness.state_code`
- `freshness.limitations`

Recommended:

- `freshness.data_through`
- `freshness.last_successful_sync`
- `freshness.latest_sync_status`

Freshness requirements:

- stale data must refuse current recommendations
- missing freshness must refuse current recommendations
- unknown freshness must refuse current recommendations
- sync timestamp must not substitute for data-through date
- freshness limitations must be visible in refusal responses

## 10. Required Explanation Fields

Each explanation must include:

- `code`
- `message`
- `details`

Explanation requirements:

- codes must be stable enough for audit
- messages must be safe for direct display
- details must not include private or unsupported claims
- successful category eligibility must state that no ranking or final selection
  occurred
- refusals must include the reason that caused fail-closed behavior

The route must not generate free-form recommendation reasoning outside the
recommendation engine pipeline.

## 11. Required Limitation Fields

Each limitation must include:

- `code`
- `message`

Mandatory limitation themes:

- public workload data only
- not injury or medical status
- not a performance forecast
- not team-reported availability
- no private clubhouse, travel, warm-up, illness, or manager-intent context
- no guarantee that a pitcher will or will not pitch
- user remains responsible for the final decision
- no ranking, comparison, or final selection in this route

Limitations must appear on both recommendation and refusal responses.

## 12. Required Category Fields

Every response must include category state, even when no category is emitted.

Required fields:

- `category`
- `category_code`
- `assigned_categories`
- `blocked_categories`

Each assigned category should include:

- `category`
- `category_code`

Each blocked category should include:

- `category`
- `category_code`
- `reasons`

Category requirements:

- positive categories require fresh, high-confidence, eligible candidates
- cautionary categories must preserve caution reasons and limitations
- avoidance categories must not be mixed into positive recommendation claims
- `bullpen_stress_alert` must not be emitted from this candidate route unless a
  future policy explicitly defines candidate-level behavior

## 13. Required Metadata Fields

Every response must include:

- `meta.policy`
- `meta.policy_version`
- `meta.engine_version`
- `meta.policy_document`
- `meta.contract_document`
- `meta.implementation_plan`
- `meta.response_mode`
- `meta.candidate_pipeline_enabled`
- `meta.ranking_applied`
- `meta.selection_made`
- `meta.selected_pitcher_id`

Required invariant values for this route:

```json
{
  "response_mode": "candidate_category_eligibility",
  "ranking_applied": false,
  "selection_made": false,
  "selected_pitcher_id": null
}
```

No response from this route may set `ranking_applied` or `selection_made` to
`true`.

## 14. Error And Refusal Handling Policy

Policy refusals should be represented as structured refusal responses whenever
the request can be parsed and evaluated.

Use structured refusal for:

- missing candidate
- invalid candidate fields
- missing availability
- missing confidence
- low or unknown confidence
- missing, stale, incomplete, historical, or unknown freshness
- excluded availability status
- multiple candidates
- unsupported category request
- missing mandatory limitations

Transport or shape errors may use an error response only when the route cannot
construct a candidate evaluation at all, such as malformed JSON.

Recommended HTTP behavior:

- `200 OK` for successful candidate evaluation
- `200 OK` for policy refusal from an evaluable request
- `400 Bad Request` for malformed JSON or non-object request bodies
- `405 Method Not Allowed` for non-POST methods
- `500 Internal Server Error` only for unexpected server failures

An empty recommendation list must not be used as a substitute for refusal.

## 15. Fail-Closed Behavior

The candidate API must fail closed.

Fail-closed means:

- no trusted candidate input produces refusal
- invalid candidate input produces refusal
- stale freshness produces refusal
- low or unknown confidence produces refusal
- missing availability produces refusal
- unavailable candidates do not produce positive categories
- multiple candidates do not trigger ranking or selection
- unsupported requests do not produce fallback guidance

Fail-closed responses must preserve refusal reason, explanations, limitations,
confidence state, freshness state, and metadata.

## 16. Frontend Display Requirements

Future frontend consumers must display backend output. They must not
recalculate recommendation categories.

Display requirements:

- show outcome as recommendation or refusal
- show category eligibility without implying final selection
- show confidence
- show freshness state and data-through date when available
- show availability status
- show explanations
- show limitations
- show refusal reason when present
- show that ranking and selection were not applied
- preserve caution and avoidance wording

Display prohibitions:

- do not hide limitations behind only static documentation
- do not label category eligibility as "best pitcher"
- do not compare candidates in this candidate route UI
- do not sort candidate responses into a ranking
- do not present stale data as current guidance
- do not remove refusal state from the user flow

## 17. Governance Requirements

Candidate API implementation must continue to satisfy these governance
requirements:

- route delegates to `RecommendationEngine.recommend()`
- route tests prove no ranking or selection occurs
- route tests cover successful candidate output and refusal output
- stale, missing, low-confidence, unavailable, and invalid inputs fail closed
- response includes required trust, freshness, explanation, limitation,
  category, and metadata fields
- API documentation remains aligned with policy and implementation plan
- category wording remains stable
- no frontend code recalculates recommendation decisions

Any later change to response shape, category semantics, refusal semantics, or
metadata invariants requires a documentation update before implementation.

## 18. Future Expansion Boundaries

Future expansion requires separate policy and contract work before
implementation.

Deferred expansions:

- team-level recommendation endpoint
- bullpen-level stress endpoint
- multi-candidate selection endpoint
- ranking or tie-break endpoint
- dashboard integration
- simulator integration
- role-aware recommendations
- rest-of-series planning
- matchup-aware guidance
- private or paid data integrations
- public external API publishing

Expansion must preserve deterministic behavior, visible explanations, visible
limitations, freshness transparency, confidence disclosure, and fail-closed
refusal when trusted data is insufficient.
