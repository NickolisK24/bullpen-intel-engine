# Recommendation Engine V1 Implementation Plan

## 1. Implementation Objective

Recommendation Engine V1 should translate the approved policy in
`docs/RECOMMENDATION_ENGINE_V1_POLICY.md` into a staged engineering build that
adds workload-informed decision support without weakening BaseballOS trust
rules.

The implementation objective is to produce deterministic, explainable,
auditable recommendation output that fails closed when trusted data is
insufficient. The system must recommend only within the limits of public
workload data already trusted by BaseballOS. It must not decide for the user,
forecast performance, predict injury, infer private team context, or introduce
black-box ranking.

This document is planning only. It does not authorize recommendation logic,
backend routes, frontend UI, database changes, ranking behavior, scoring
formulas, or implementation tests by itself.

## 2. Required Policy Inputs

The future implementation should consume policy-approved inputs only:

- Availability Engine V1 output:
  - `availability_status`
  - `confidence`
  - `data_state`
  - `reasons`
  - `limitations`
  - deterministic workload `inputs`
- fatigue score and fatigue risk level already used by availability
- recent workload inputs already derived for availability:
  - pitches yesterday
  - pitches over recent windows
  - appearance compression
  - days of rest
  - latest game date
- freshness and sync metadata:
  - data-through date
  - last sync attempt
  - last successful sync
  - latest fatigue calculation timestamp
  - sync status
  - freshness limitations
- pitcher and team context already available through current bullpen data
- the six V1 policy categories:
  - Best Available Arm
  - Freshest High-Leverage Arm
  - Lowest Current Workload Risk
  - Use With Caution
  - Avoid Tonight
  - Bullpen Stress Alert

The implementation must not add new source categories merely to make
recommendations more persuasive.

## 3. Proposed Backend Module Boundaries

Recommendation behavior should be centralized in a backend service module rather
than embedded in Flask route handlers or frontend components.

Proposed future module boundaries:

| Future surface | Responsibility |
| --- | --- |
| `backend/services/recommendations.py` | Policy orchestration, gate execution, category assignment, refusal construction, and response payload assembly. |
| `backend/services/recommendation_explanations.py` | Reusable explanation and limitation text, kept separate from gate mechanics. |
| `backend/services/recommendation_summary.py` | Optional team-level aggregation for Bullpen Stress Alert if that category needs shared summary behavior. |
| `backend/api/recommendations.py` | Candidate-level route exposure only; no inline recommendation classification. |
| `backend/api/bullpen.py` | Existing availability routes only; no inline recommendation classification. |
| `backend/tests/test_recommendations.py` | Focused service tests for policy behavior. |
| `backend/tests/test_recommendation_api.py` | Route-contract tests only after endpoint exposure is authorized. |

Availability classification must remain owned by
`backend/services/availability.py`. Recommendation code should consume
availability objects and must not reimplement availability thresholds.

### Foundation Layer Status

The initial foundation layer lives in `backend/recommendation/`. It defines
contracts, enums, result/refusal schemas, validation helpers, and a fail-closed
engine default. It does not select pitchers, rank candidates, assign categories,
or expose an API route.

The eligibility gate layer in `backend/recommendation/gates.py` evaluates
candidate trust readiness before any future recommendation selection. It
enforces pitcher identity, availability status, confidence, and freshness; emits
explainable exclusion and caution reasons; and keeps positive-pool eligibility
separate from cautionary or avoidance contexts. It still does not select, rank,
or recommend a pitcher.

The category assignment layer in `backend/recommendation/categories.py` maps
already-gated candidates into policy-approved category eligibility. It can mark
categories as assigned or blocked with explanations and limitations, but it does
not choose a final pitcher, rank candidates, or decide which eligible candidate
is best.

The builder/composer layer in `backend/recommendation/builder.py` combines a
candidate, gate result, and category assignment into a structured
`RecommendationResult`. It preserves explanations, limitations, confidence,
freshness, availability state, assigned categories, blocked categories, and
governance metadata. It still does not rank candidates, compare candidates, or
select a final pitcher.

The engine integration in `backend/recommendation/engine.py` allows
`RecommendationEngine.recommend()` to evaluate one candidate through the gate,
category-assignment, and builder pipeline. Calls with no candidate, invalid
candidate input, or multiple candidates fail closed. The engine still does not
rank, score, compare, or select a final pitcher. Frontend exposure and
multi-candidate route behavior remain future stages.

The candidate-level API contract is documented in
`docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md`. That contract defines request
and response shape, mandatory trust fields, refusal behavior, frontend display
requirements, and no-ranking/no-selection metadata. The implemented route in
`backend/api/recommendations.py` exposes one-candidate evaluation only and
delegates policy behavior to `RecommendationEngine.recommend()`.

The frontend display contract is documented in
`docs/RECOMMENDATION_ENGINE_V1_FRONTEND_CONTRACT.md`. That contract defines how
future UI surfaces must display candidate-level output, visible trust and
freshness indicators, explanations, limitations, refusal states, copy
conventions, mobile behavior, accessibility, and no-ranking/no-selection
metadata before UI implementation is authorized.

Future implementation stages may either keep this domain package or adapt it
behind `backend/services/recommendations.py`, but recommendation behavior must
remain centralized and must not be duplicated in routes or frontend components.

## 4. Candidate Recommendation Data Flow

A future request should flow through explicit policy gates before any category
is returned.

Candidate flow:

1. Fetch candidate pitchers for the requested team or bullpen scope.
2. Fetch or compute current availability through the existing availability
   service path.
3. Attach freshness and sync metadata from the existing durable sync surfaces.
4. Normalize candidates into a recommendation input record.
5. Run required-data validation.
6. Run eligibility gates.
7. Run exclusion gates.
8. Run category-specific policy checks.
9. Build recommendation, caution, stress-alert, or refusal payloads.
10. Attach explanations, limitations, confidence, data state, and policy
    metadata.
11. Return a response that makes recommendation and refusal state explicit.

The flow should preserve the distinction between candidate collection,
availability classification, recommendation policy, and API serialization.

## 5. Eligibility Gate Design

Eligibility gates decide whether a pitcher may be considered for any V1
recommendation category.

Required gate outcomes:

- `eligible`: the candidate passes all required policy inputs for the requested
  scope.
- `ineligible`: the candidate is excluded for an explainable policy reason.
- `unknown`: the candidate cannot be evaluated because trusted inputs are
  missing or ambiguous.

Planned eligibility checks:

- current tracked pitcher in BaseballOS
- known team context for the request
- availability object present
- availability status present
- confidence present
- data state present
- data-through date present
- freshness state explainable
- workload inputs sufficient to support an explanation
- limitations available for the output

An `unknown` gate result should trigger refusal when it affects the requested
recommendation category. Unknown must not be converted into a speculative
recommendation.

## 6. Exclusion Gate Design

Exclusion gates decide whether a candidate must be removed from positive
recommendation categories or routed only to cautionary output.

Planned exclusion checks:

- `Avoid` and `Unavailable` exclude a candidate from positive categories.
- Low or unknown confidence excludes the candidate from current recommendation
  output.
- Stale, missing, historical, or unknown data state excludes the candidate from
  current recommendation output.
- Incomplete data excludes the candidate unless the approved policy later
  defines a narrow cautionary allowance.
- Ambiguous pitcher identity, team context, or latest workload date excludes
  the candidate.
- Any category requiring unsupported information must refuse instead of
  selecting a candidate.

Each exclusion should emit a stable reason code and user-visible explanation.
This allows audits to count why candidates were excluded without parsing prose.

## 7. Availability Status Integration

Recommendation Engine V1 should treat availability status as a policy gate, not
as a hidden score.

Planned status handling:

| Availability status | Future recommendation handling |
| --- | --- |
| `Available` | Eligible for positive workload categories if confidence and freshness pass. |
| `Monitor` | Eligible only when the monitoring reason is included in the recommendation explanation. |
| `Limited` | Excluded from normal-use categories; eligible for `Use With Caution` or team stress context. |
| `Avoid` | Excluded from positive categories; eligible for `Avoid Tonight` or team stress context. |
| `Unavailable` | Excluded as a usable option; eligible only as an unavailable workload constraint in team stress context. |

The recommendation layer must never weaken an availability restriction.

## 8. Confidence Handling

Recommendation confidence should be derived from availability confidence and
freshness confidence. It must never exceed the underlying availability
confidence.

Planned confidence rules:

- high confidence is required for positive categories
- medium confidence may support cautionary output when the uncertainty is
  explained
- low confidence refuses current recommendation output
- unknown confidence refuses current recommendation output
- missing explanation detail lowers confidence or refuses output

Confidence should be described as data and policy confidence. It must not be
framed as probability, correctness likelihood, game-outcome likelihood, or
medical risk.

## 9. Freshness Handling

Freshness handling should run before category assignment.

Planned freshness checks:

- require a trusted data-through date for current recommendations
- keep sync timestamp and data-through date separate
- reject stale, missing, historical, or unknown freshness state for current
  recommendations
- disclose failed latest sync attempts when prior trusted data is still fresh
- refuse if freshness cannot be explained

The future implementation should prefer an explicit refusal over presenting old
workload context as current bullpen guidance.

## 10. Refusal Handling

Refusal is a first-class output, not an error condition.

Planned refusal behavior:

- return a structured refusal object when no trusted recommendation can be made
- include a stable refusal reason code
- include user-visible refusal text
- include data-state and freshness context
- include limitations explaining what BaseballOS does not know
- avoid speculative fallback guidance

Recommended refusal categories:

- `missing_required_inputs`
- `stale_data`
- `unknown_freshness`
- `low_confidence`
- `category_out_of_scope`
- `all_candidates_excluded`
- `unsupported_claim_requested`
- `missing_limitations`

Default refusal text should align with the policy:

```text
BaseballOS cannot make a current recommendation because trusted current
workload data is insufficient.
```

## 11. Explanation Payload Requirements

Every recommendation and refusal should include explanation payloads that are
safe for direct UI display and useful for audit.

Required explanation fields:

- recommendation category
- pitcher or team scope
- availability status
- availability confidence
- data state
- data-through date
- last successful sync when available
- primary workload reasons
- relevant limitations
- deterministic inputs used
- exclusion reasons for candidates omitted from the requested category when
  needed to prevent overclaiming
- refusal reason when no recommendation is allowed

Explanations should be assembled from stable reason codes plus controlled text.
The future implementation should avoid free-form prose generated inside route
handlers.

## 12. Limitation Payload Requirements

Limitations must travel with recommendation output, not live only in static
documentation.

Required limitation themes:

- based on public workload data tracked by BaseballOS
- not a medical or injury conclusion
- not a performance forecast
- not a team-reported availability status
- no bullpen warm-up, travel, illness, clubhouse, or manager-intent knowledge
- no guarantee that a pitcher will or will not pitch
- user remains responsible for the final decision

The implementation should make limitation payloads deterministic and testable.
Category-specific limitations should be additive and should not replace the base
trust limitations.

## 13. Suggested API Response Shape

Endpoint exposure is a later implementation stage. If authorized, the response
shape should make recommendation, refusal, confidence, freshness, and policy
metadata explicit.

Illustrative response shape:

```json
{
  "data": {
    "scope": {
      "team_id": 123,
      "team_name": "Example Club",
      "mode": "current_recommendations"
    },
    "recommendations": [
      {
        "category": "Best Available Arm",
        "pitcher": {
          "id": 456,
          "name": "Example Pitcher"
        },
        "confidence": "high",
        "availability": {
          "availability_status": "Available",
          "confidence": "high",
          "data_state": "fresh"
        },
        "reasons": [
          "Workload signals are inside current policy limits."
        ],
        "limitations": [
          "Based on public workload data tracked by BaseballOS."
        ],
        "inputs": {
          "latest_game_date": "2026-06-01",
          "reference_date": "2026-06-02"
        }
      }
    ],
    "refusal": null,
    "excluded_candidates": [
      {
        "pitcher_id": 789,
        "reason_code": "availability_excluded",
        "availability_status": "Avoid"
      }
    ]
  },
  "meta": {
    "policy": "recommendation_engine_v1",
    "policy_document": "docs/RECOMMENDATION_ENGINE_V1_POLICY.md",
    "data_through": "2026-06-01",
    "last_successful_sync": "2026-06-02T10:00:00Z",
    "is_current_recommendation": true
  }
}
```

If refusal is required, `recommendations` should be empty and `refusal` should
contain reason code, message, data-state context, and limitations.

## 14. Suggested Test Strategy

Future tests should prove policy boundaries before UI polish.

Suggested backend service tests:

- positive category requires high confidence and fresh data
- `Avoid` and `Unavailable` cannot enter positive categories
- `Limited` routes only to caution or stress context
- stale data refuses current recommendations
- missing data refuses current recommendations
- low and unknown confidence refuse current recommendations
- medium confidence is limited to cautionary output
- recommendation confidence never exceeds availability confidence
- required explanations are present
- required limitations are present
- unsupported forecast or private-context requests refuse
- tie behavior is deterministic and auditable once tie rules are approved

Suggested API tests after endpoint authorization:

- response shape contains `data`, `meta`, recommendation or refusal state
- route delegates to the recommendation service
- stale and missing data responses are refusals, not empty successes
- policy document/version metadata is present

Suggested regression validation:

- availability tests remain unchanged by recommendation work
- sync-status tests continue to distinguish sync timestamp from data-through date
- recommendation tests must not require network access
- fixture data should exercise all six V1 categories and refusal cases

## 15. Suggested Staged Implementation Sequence

### Stage 1: Backend Recommendation Policy Module Skeleton

Create the backend module structure and typed result shapes without selecting
recommendations. The first stage should return controlled refusal or empty
planning fixtures only.

Exit criteria:

- module boundaries exist
- no route exposure
- no frontend exposure
- no category assignment behavior
- tests cover skeleton shape only if implementation is authorized

### Stage 2: Eligibility And Exclusion Gates

Implement deterministic gate evaluation before category assignment.

Exit criteria:

- candidate eligibility is explainable
- exclusions emit stable reason codes
- stale, missing, and low-confidence inputs fail closed
- availability status restrictions are preserved

### Stage 3: Recommendation Category Assignment

Implement category assignment only after gates are stable. Category assignment
must use documented deterministic rules and must avoid hidden composite scores.

Exit criteria:

- all six V1 categories are reachable in tests
- positive categories require fresh high-confidence data
- cautionary categories preserve limitations
- any tie handling is documented and auditable

### Stage 4: Explainability And Refusal Payloads

Attach user-visible explanations, deterministic inputs, limitations, and refusal
metadata to every output.

Exit criteria:

- no recommendation without reasons
- no recommendation without limitations
- refusals include stable reason codes and trust context
- output is suitable for future UI display without route-written prose

### Stage 5: API Endpoint Exposure

Expose a read-only endpoint only after service behavior is proven.

Exit criteria:

- route matches `docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md`
- route delegates to the recommendation service
- response shape matches the documented contract
- no database migration required
- no write endpoint introduced
- freshness metadata appears in `meta`

### Stage 6: Frontend Display Planning

Plan UI consumption before building it. The frontend should display backend
output and must not recalculate recommendations.

Exit criteria:

- display states are documented in
  `docs/RECOMMENDATION_ENGINE_V1_FRONTEND_CONTRACT.md`
- refusal state has a first-class UI plan
- limitations are visible with the recommendation
- mobile and desktop layouts preserve readability
- accessibility requirements are documented before UI work begins

### Stage 7: Governance And Regression Validation

Add audit and regression coverage after service and route behavior are stable.

Exit criteria:

- policy boundary tests pass
- availability regression tests pass
- stale/missing data refusal behavior is validated
- documentation reflects implemented behavior
- category wording remains stable

## 16. Risks And Guardrails

Key risks:

- recommendation wording may sound like a team decision
- users may mistake workload guidance for injury or performance prediction
- frontend code may be tempted to recompute categories locally
- stale data may appear persuasive if refusal state is not prominent
- hidden ordering rules may become black-box ranking
- category expansion may outrun policy approval

Guardrails:

- centralize recommendation behavior in the backend service layer
- keep category text stable and policy-reviewed
- expose refusal state as normal output
- require explanations and limitations in every response
- test stale, missing, low-confidence, and out-of-scope cases first
- keep availability classification untouched by recommendation work
- document any future tie rule or category-rule change before adoption
- avoid any wording that removes the user's judgment

## 17. Non-Goals For The Implementation Phase

The implementation phase should not:

- change fatigue scoring
- change Availability Engine thresholds
- change sync metadata semantics
- add database tables or migrations for V1
- add write endpoints
- add frontend recommendation UI before backend policy behavior is proven
- add performance forecasts
- add injury, medical, transaction, or team-news inference
- add matchup modeling
- add save, hold, win, loss, or run-prevention projections
- add black-box ranking
- use private, paid, warm-up, travel, or manager-intent data
- replace user judgment with automated decisions

Recommendation Engine V1 should remain a trust-first decision-support layer
that recommends within strict public-workload limits and refuses when the data
cannot support the requested guidance.
