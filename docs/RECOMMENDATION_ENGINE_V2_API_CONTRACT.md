# Recommendation Engine V2 API Contract

## 1. Executive Summary

This document defines the proposed Recommendation Engine V2 API response
contract before implementation.

It is a documentation and contract-design milestone only. It does not
implement V2, add endpoints, modify existing endpoints, modify backend
behavior, modify frontend behavior, or change certified Recommendation Engine
V1 behavior.

The V2 API contract must preserve:

```text
ranking_applied = false
selection_made = false
```

The contract prevents accidental ranking, selection, opaque scoring,
prediction, or unsupported decision-making from entering future API design.

## 2. Relationship to V1 API

Recommendation Engine V1 exposes candidate-level evaluation only. V1 evaluates
one candidate at a time and preserves no-ranking and no-selection metadata.

This V2 API contract does not modify the V1 API, V1 response shape, V1 route
behavior, V1 frontend integration, or V1 certification.

Future V2 API design must remain separate from V1 until explicitly approved
for implementation.

## 3. Relationship to V2 Strategy

The V2 strategy foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`

This API contract supports the strategy by defining a response shape for
bullpen-state summaries, grouped eligibility, inventory visibility,
stress/readiness context, and broader explanations without ranking or
selection.

## 4. Relationship to V2 Governance Boundaries

The V2 governance-boundary document is:

- `docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`

This API contract is subordinate to that governance document. API payloads must
not contain ranking arrays, winner fields, hidden weights, opaque scores,
automated pitcher choice, unsupported predictions, or decision commands.

## 5. Relationship to V2 Architecture

The V2 architecture foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`

This API contract translates the architecture concepts into proposed
contract-level response objects:

- `BullpenState`
- `CandidateGroup`
- `Inventory`
- `TeamBullpenContext`
- `TrustMetadata`
- explainability, freshness, limitation, and refusal objects

## 6. API Contract Goals

The V2 API contract should:

- define future response shapes before implementation
- keep V2 descriptive, explainable, deterministic, auditable, trust-first, and
  fail-closed
- preserve top-level no-ranking and no-selection metadata
- define neutral candidate grouping
- define descriptive inventory and team context
- require freshness, confidence, explanations, limitations, and refusal
  metadata
- make anti-ranking rules contractually visible
- support future certification and test design

## 7. API Contract Non-Goals

This contract does not define or authorize:

- implemented endpoints
- route changes
- backend services
- frontend behavior
- database schema changes
- V1 API changes
- ranking or ordering logic
- score-like outputs
- final pitcher selection
- prediction models
- hidden weights
- implementation tests

Endpoint naming and route behavior remain provisional until implementation is
explicitly approved.

## 8. Proposed Endpoint Scope

The proposed future endpoint scope is bullpen-state V2 context.

Allowed provisional endpoint name:

```text
GET /api/recommendations/v2/bullpen-state
```

Equivalent naming may be considered during implementation planning, but no
endpoint is implemented by this document.

The proposed endpoint would return descriptive bullpen state, grouped
candidate context, inventory summaries, team bullpen context, trust metadata,
explanations, limitations, freshness, and refusal state.

## 9. Request Shape Principles

Future V2 requests should:

- identify the team or bullpen scope being evaluated
- avoid sending ordered candidate lists as preference inputs
- avoid accepting ranking, selection, priority, or score parameters
- preserve freshness and data-state requirements
- allow only inputs that can be explained from BaseballOS trust surfaces
- fail closed when requested scope exceeds certified V2 behavior

Request contracts belong in a future implementation-approved API milestone.

## 10. Response Shape Principles

Future V2 responses should:

- include top-level governance metadata
- include descriptive bullpen-state output when trusted
- include neutral candidate groups when grouping is supported
- include inventory summaries when inventory can be explained
- include team bullpen context without decision commands
- include explanations, limitations, freshness, confidence, data state, and
  refusal reasons
- preserve the same shape for refusal responses where practical
- avoid ranking arrays, score fields, winner fields, selected pitcher fields,
  and preference-ordered lists

If the response cannot preserve `ranking_applied=false` and
`selection_made=false`, the response must fail closed.

## 11. Required Top-Level Metadata

Every future V2 response must include top-level trust and governance metadata:

```json
{
  "scope": "bullpen_state",
  "ranking_applied": false,
  "selection_made": false,
  "confidence": "medium",
  "data_state": "complete",
  "generated_at": "ISO-8601 timestamp",
  "freshness": {},
  "limitations": [],
  "explanations": [],
  "refusal_reasons": []
}
```

Contract rules:

- `ranking_applied` must remain `false`.
- `selection_made` must remain `false`.
- If either value cannot truthfully remain `false`, the response must fail
  closed.
- No response may include sorted ranking, score-based ordering, winner
  selection, or "best option" language.

## 12. Bullpen State Response Object

`BullpenState` represents descriptive bullpen context.

Required shape:

```json
{
  "status": "available_context",
  "stress_level": "elevated",
  "readiness_summary": "Limited fresh inventory is available.",
  "inventory_summary": [],
  "candidate_groups": [],
  "team_context": {},
  "trust": {}
}
```

Required fields:

- `status`
- `stress_level`
- `readiness_summary`
- `inventory_summary`
- `candidate_groups`
- `team_context`
- `trust`

`BullpenState` must remain descriptive. It must not identify a selected
pitcher, top pitcher, best candidate, or preferred order.

## 13. Candidate Group Response Object

`CandidateGroup` represents a neutral grouping of candidates that share the
same documented eligibility basis.

Required shape:

```json
{
  "group_id": "fresh_high_leverage_arms",
  "label": "Fresh High-Leverage Arms",
  "description": "Pitchers matching documented fresh high-leverage criteria.",
  "eligibility_basis": [],
  "candidate_count": 3,
  "ordering": "alphabetical_non_ranking",
  "candidates": [],
  "explanations": [],
  "limitations": [],
  "confidence": "medium",
  "freshness": {},
  "refusal_reasons": []
}
```

Candidate rules:

- candidates inside a group must not be ordered by preference
- deterministic ordering must be neutral, such as alphabetical or stable ID
  order
- neutral ordering must be documented as non-ranking
- group labels must describe criteria, not superiority
- candidate groups must not contain selected-pitcher, recommended-pitcher, or
  winner fields

## 14. Inventory Response Object

`Inventory` represents descriptive bullpen resource visibility.

Required shape:

```json
{
  "inventory_type": "high_leverage_inventory",
  "label": "High-Leverage Inventory",
  "count": 2,
  "members": [],
  "evidence": [],
  "limitations": [],
  "freshness": {},
  "confidence": "medium"
}
```

Inventory concepts may include:

- High-Leverage Inventory
- Multi-Inning Inventory
- Emergency Coverage Inventory
- Limited Availability Inventory

Inventory must be descriptive only. It must not imply which member should be
used first.

## 15. Team Bullpen Context Response Object

`TeamBullpenContext` represents descriptive team-level bullpen context.

Required shape:

```json
{
  "workload_distribution": {},
  "availability_distribution": {},
  "leverage_inventory": [],
  "readiness_indicators": [],
  "stress_indicators": [],
  "explanations": [],
  "limitations": []
}
```

Team context must not provide a team-level decision command, matchup advice,
game outcome prediction, manager-intent inference, or final pitcher selection.

## 16. Trust Metadata Object

`TrustMetadata` represents governance metadata attached to top-level and nested
objects.

Required shape:

```json
{
  "scope": "bullpen_state",
  "ranking_applied": false,
  "selection_made": false,
  "confidence": "medium",
  "data_state": "complete",
  "generated_at": "ISO-8601 timestamp"
}
```

`ranking_applied=false` and `selection_made=false` are mandatory for V2
responses. If future behavior cannot truthfully set both fields to `false`,
the response must fail closed.

## 17. Explainability Object

`Explainability` objects describe why an output exists and what data supports
it.

Required shape:

```json
{
  "explanation_id": "bullpen_stress_limited_fresh_inventory",
  "level": "bullpen",
  "message": "Bullpen stress is elevated because fresh inventory is limited.",
  "evidence": [],
  "applies_to": "bullpen_state"
}
```

Explainability is required at every supported level:

- candidate level
- group level
- inventory level
- bullpen level
- team level
- refusal level

No V2 output should exist without supporting reasoning.

## 18. Freshness Object

`Freshness` objects describe sync and baseball data coverage.

Required shape:

```json
{
  "sync_timestamp": "ISO-8601 timestamp",
  "data_through": "YYYY-MM-DD",
  "freshness_state": "current",
  "stale_warning": null,
  "missing_data_warning": null
}
```

Freshness rules:

- sync timestamp visibility is required
- data-through date visibility is required
- stale data warnings are required when applicable
- missing data warnings are required when applicable
- degraded freshness must affect confidence, refusal, or output suppression
- sync timestamp must not substitute for data-through date

## 19. Limitation Object

`Limitation` objects describe what BaseballOS does not know or cannot prove.

Required shape:

```json
{
  "limitation_id": "no_manager_intent",
  "message": "BaseballOS does not know manager intent or bullpen warm-up activity.",
  "severity": "informational",
  "applies_to": "team_context"
}
```

Limitations must stay attached to the output they qualify. They must not be
hidden in static documentation only.

## 20. Refusal Object

`Refusal` objects describe why V2 output was refused, suppressed, or
downgraded.

Required shape:

```json
{
  "refusal_id": "stale_freshness",
  "reason": "freshness_stale",
  "message": "Current bullpen-state output is refused because data is stale.",
  "applies_to": "bullpen_state"
}
```

Refusal reasons should be deterministic and auditable. Refusal must preserve
top-level metadata, including `ranking_applied=false` and
`selection_made=false`.

## 21. Error and Fail-Closed Response Shape

Future V2 responses must preserve contract shape when output fails closed.

Fail-closed responses should include:

- top-level metadata
- `bullpen_state` as `null` or suppressed
- freshness state
- explanations when available
- limitations
- refusal reasons
- no forbidden ranking or selection fields

Required fail-closed behavior:

- stale data triggers refusal, suppression, or downgraded confidence
- incomplete data triggers refusal, suppression, or downgraded confidence
- unexplained eligibility triggers refusal
- output that would exceed certified V2 scope triggers refusal
- output that would imply ranking or selection triggers refusal

## 22. Anti-Ranking Contract Rules

The V2 API contract explicitly forbids:

- ranking arrays
- numeric rank fields
- priority scores
- hidden weights
- "best candidate" fields
- "recommended_pitcher" fields
- "selected_pitcher" fields
- sorted preference lists
- comparative winner language

Disallowed fields include:

```json
{
  "rank": 1,
  "score": 92,
  "priority": "high",
  "best_candidate": true,
  "recommended_pitcher_id": 12345,
  "selected_pitcher_id": 12345
}
```

Allowed fields include:

```json
{
  "group_id": "fresh_high_leverage_arms",
  "label": "Fresh High-Leverage Arms",
  "candidate_count": 3
}
```

Contract rule: BaseballOS may group, summarize, and explain. BaseballOS must
not rank, choose, or decide.

## 23. Example Successful Response

This example is illustrative only. It does not implement an endpoint.

```json
{
  "scope": "bullpen_state",
  "ranking_applied": false,
  "selection_made": false,
  "confidence": "medium",
  "data_state": "complete",
  "generated_at": "2026-06-02T18:30:00Z",
  "freshness": {
    "sync_timestamp": "2026-06-02T12:00:00Z",
    "data_through": "2026-06-01",
    "freshness_state": "current",
    "stale_warning": null,
    "missing_data_warning": null
  },
  "limitations": [
    {
      "limitation_id": "no_manager_intent",
      "message": "BaseballOS does not know manager intent or bullpen warm-up activity.",
      "severity": "informational",
      "applies_to": "bullpen_state"
    }
  ],
  "explanations": [
    {
      "explanation_id": "limited_fresh_inventory",
      "level": "bullpen",
      "message": "Bullpen stress is elevated due to limited fresh inventory.",
      "evidence": ["Two available high-leverage arms meet documented criteria."],
      "applies_to": "bullpen_state"
    }
  ],
  "refusal_reasons": [],
  "bullpen_state": {
    "status": "available_context",
    "stress_level": "elevated",
    "readiness_summary": "Current bullpen inventory includes two available high-leverage arms.",
    "inventory_summary": [
      {
        "inventory_type": "high_leverage_inventory",
        "label": "High-Leverage Inventory",
        "count": 2,
        "members": [
          {
            "pitcher_id": 1001,
            "display_name": "Pitcher A"
          },
          {
            "pitcher_id": 1002,
            "display_name": "Pitcher B"
          }
        ],
        "evidence": ["Availability and workload criteria passed."],
        "limitations": [],
        "freshness": {
          "freshness_state": "current"
        },
        "confidence": "medium"
      }
    ],
    "candidate_groups": [
      {
        "group_id": "fresh_high_leverage_arms",
        "label": "Fresh High-Leverage Arms",
        "description": "Pitchers matching documented fresh high-leverage criteria.",
        "eligibility_basis": ["availability_status", "recent_workload", "freshness"],
        "candidate_count": 3,
        "ordering": "alphabetical_non_ranking",
        "candidates": [
          {
            "pitcher_id": 1001,
            "display_name": "Pitcher A"
          },
          {
            "pitcher_id": 1002,
            "display_name": "Pitcher B"
          },
          {
            "pitcher_id": 1003,
            "display_name": "Pitcher C"
          }
        ],
        "explanations": [
          {
            "message": "Three pitchers currently qualify for Fresh High-Leverage Arm criteria."
          }
        ],
        "limitations": [],
        "confidence": "medium",
        "freshness": {
          "freshness_state": "current"
        },
        "refusal_reasons": []
      }
    ],
    "team_context": {
      "workload_distribution": {
        "summary": "Recent workload is concentrated among limited inventory."
      },
      "availability_distribution": {
        "available": 4,
        "monitor": 2,
        "limited": 1,
        "avoid": 1,
        "unavailable": 0
      },
      "leverage_inventory": ["High-Leverage Inventory"],
      "readiness_indicators": ["Limited fresh inventory"],
      "stress_indicators": ["Elevated bullpen stress"],
      "explanations": [],
      "limitations": []
    },
    "trust": {
      "ranking_applied": false,
      "selection_made": false,
      "confidence": "medium",
      "data_state": "complete"
    }
  }
}
```

The example does not imply ranking. Candidate ordering is documented as
alphabetical and non-ranking.

## 24. Example Refusal Response

This example is illustrative only. It does not implement an endpoint.

```json
{
  "scope": "bullpen_state",
  "ranking_applied": false,
  "selection_made": false,
  "confidence": "low",
  "data_state": "stale",
  "generated_at": "2026-06-02T18:30:00Z",
  "freshness": {
    "sync_timestamp": "2026-06-01T12:00:00Z",
    "data_through": "2026-05-30",
    "freshness_state": "stale",
    "stale_warning": "Bullpen-state output is stale beyond accepted thresholds.",
    "missing_data_warning": "Some workload evidence is incomplete."
  },
  "limitations": [
    {
      "limitation_id": "incomplete_workload_evidence",
      "message": "BaseballOS cannot explain current candidate eligibility from incomplete workload evidence.",
      "severity": "blocking",
      "applies_to": "bullpen_state"
    }
  ],
  "explanations": [
    {
      "explanation_id": "fail_closed_stale_data",
      "level": "refusal",
      "message": "Output is refused because freshness is stale and explanations cannot be produced.",
      "evidence": ["Data-through date is outside the accepted freshness window."],
      "applies_to": "bullpen_state"
    }
  ],
  "refusal_reasons": [
    {
      "refusal_id": "stale_freshness",
      "reason": "freshness_stale",
      "message": "Current bullpen-state output is refused because data is stale.",
      "applies_to": "bullpen_state"
    },
    {
      "refusal_id": "scope_exceeded",
      "reason": "exceeds_certified_v2_scope",
      "message": "Requested output would exceed certified V2 scope.",
      "applies_to": "bullpen_state"
    }
  ],
  "bullpen_state": null
}
```

The refusal response preserves trust metadata and does not include ranking,
selection, score, winner, or recommended-pitcher fields.

## 25. Testing Requirements

Future implementation must test:

- response includes `ranking_applied=false`
- response includes `selection_made=false`
- no forbidden fields exist
- candidate groups are not preference-ranked
- deterministic neutral ordering only
- stale data triggers refusal or downgrade
- missing data triggers refusal or downgrade
- explanations are present
- limitations are present
- freshness metadata is present
- refusal responses preserve contract shape

Tests must inspect both successful and fail-closed responses.

## 26. Certification Requirements

Future implementation cannot be certified unless:

- API contract is followed
- anti-ranking rules pass
- fail-closed paths pass
- trust metadata is always present
- example responses match actual behavior
- V1 behavior remains unchanged

Certification must explicitly prove that V2 API behavior did not introduce
ranking, selection, opaque scoring, prediction, unsupported decision-making, or
hidden weights.

## 27. Implementation Gate

V2 API implementation must not begin until:

1. API contract is approved
2. frontend contract is approved
3. certification requirements are approved
4. user explicitly approves implementation

This document alone does not authorize endpoint implementation, route changes,
backend behavior changes, frontend behavior changes, or V1 behavior changes.
