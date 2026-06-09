# BaseballOS V4 Phase 14 - Explanation API Contract Planning

## Phase Status

Phase status:

```text
V4_PHASE_14_EXPLANATION_API_CONTRACT_PLANNING_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
PLANNING_ONLY
```

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_15_EXPLANATION_API_ROUTE_IMPLEMENTATION
```

This phase defines the governed API contract plan for exposing certified V4
explanation objects. It does not implement Flask routes, modify backend runtime
behavior, modify frontend behavior, change Dashboard UI, alter source engines,
or approve production rollout.

## 1. Contract Scope

Phase 14 covers API contract planning for certified V4 explanations only.

Included contract-planning scope:

- Availability Explanation API contracts
- Team Operations Readiness Explanation API contracts
- shared V4 explanation response shape
- governance response requirements
- limitation response requirements
- fail-closed response requirements
- safe error handling recommendations
- future route testing requirements

Excluded from Phase 14:

- frontend UI
- Dashboard implementation
- route implementation
- uncertified explanation scopes
- recommendation behavior
- runtime source-engine changes
- database persistence
- rollout approval
- public production certification for explanation routes

Certified explanations may be exposed by future routes only as explanation
objects. Explanation APIs may not expose decisions.

Every planned API response must preserve and expose:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

Planned API contracts must not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred arm behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation

## 2. Certified Explanation Types

Currently certified explanation tracks:

| Explanation type | Certification status | Certification source | API exposure status |
| --- | --- | --- | --- |
| `availability_explanation` | `CERTIFIED_WITH_NON_BLOCKING_OBSERVATIONS` | [V4 Phase 8 formal certification](V4_PHASE_8_AVAILABILITY_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) | Not implemented; contract planned in this phase |
| `team_readiness_explanation` | `CERTIFIED_WITH_NON_BLOCKING_OBSERVATIONS` | [V4 Phase 13 formal certification](V4_PHASE_13_TEAM_OPERATIONS_READINESS_EXPLANATION_FORMAL_CERTIFICATION_REVIEW.md) | Not implemented; contract planned in this phase |

Uncertified or future explanation types must not be exposed through public,
internal, or experimental API routes until separately certified.

Uncertified types include:

- `risk_distribution_explanation`
- `recommendation_explanation`
- explanation UI surfaces
- future readiness expansion scopes beyond the certified readiness adapter
- any explanation type that attempts to explain a recommendation, selection,
  ranking, prediction, matchup, or decision

## 3. Candidate API Routes

Phase 14 recommends a small V4 explanation route family. Route names are
contract candidates only; no route is implemented in this phase.

### Candidate Route: Availability Explanation

```text
GET /api/explanations/availability/:pitcher_id
```

Purpose:

- expose a certified V4 explanation for an existing Availability Engine state
- answer why the pitcher has the current `Available`, `Monitor`, `Limited`,
  `Avoid`, or `Unavailable` availability state
- preserve the Availability Engine state rather than recalculating it

Subject type:

```text
pitcher
```

Explanation scope:

```text
availability_state
```

Expected inputs:

- `pitcher_id` path parameter
- optional safe context identifiers if future implementation requires them,
  such as `team_id`, `date`, or existing source snapshot selectors

Prohibited inputs:

- `rank`
- `recommend`
- `select`
- `best`
- `preferred`
- `matchup`
- `predict`
- `injury`
- `save`
- `performance`
- any input that requests pitcher advice, hidden priority ordering, matchup
  guidance, or decision automation

Expected response:

- shared successful response shape with `status: "ok"`
- a single V4 explanation object
- governance payload with all false decision flags
- visible evidence, limitations, freshness, trust, and confidence references

Governance requirements:

- `ranking_applied === false`
- `selection_made === false`
- `recommendation_made === false`
- `prediction_made === false`
- `decision_scope === "explanation_only"`
- `advice_scope === "none"`

Fail-closed behavior:

- unknown pitcher, missing availability data, stale unsafe data, builder
  validation failure, or unsafe query intent must not fabricate explanation
  evidence
- response must return a governed unavailable/refusal shape with limitations

### Candidate Route: Team Readiness Explanation

```text
GET /api/explanations/team-readiness
```

Purpose:

- expose a certified V4 explanation for the existing Team Operations Bullpen
  Readiness state
- answer why readiness is operationally stable, degraded, data-limited,
  freshness-limited, coverage-limited, trust-limited, or workload-constrained
  using the current readiness payload

Subject type:

```text
bullpen
```

Default explanation scope:

```text
readiness_state
```

Expected inputs:

- optional safe `scope` query parameter limited to certified Team Operations
  readiness explanation scopes
- optional safe context identifiers if implementation requires them, such as
  `team_id` or date/snapshot selectors already supported by the readiness
  source surface

Certified scopes:

```text
readiness_state
workload_state
coverage_state
freshness_state
trust_state
```

Expected response:

- shared successful response shape with `status: "ok"`
- one V4 explanation object for the requested certified scope
- visible governance, evidence, limitation, freshness, trust, and confidence
  metadata

Governance requirements:

- all output remains team-level, bullpen-level, or context-level
- no pitcher ranking, selection, recommendation, matchup advice, or hidden
  priority ordering

Fail-closed behavior:

- missing readiness payloads, missing trust/freshness inputs, unsupported
  scopes, uncertified explanation types, unsafe query intent, or builder
  validation failures must return a governed unavailable/refusal shape

### Candidate Route: Team Readiness Explanation By Scope

```text
GET /api/explanations/team-readiness/:scope
```

Purpose:

- provide a path-based alternative to `?scope=...` for certified Team
  Operations Readiness explanation scopes
- make future route tests explicit about scope-specific behavior

Subject type:

```text
bullpen
```

Explanation scopes:

```text
readiness_state
workload_state
coverage_state
freshness_state
trust_state
```

Expected inputs:

- `scope` path parameter constrained to certified readiness scopes
- optional safe context identifiers if implementation requires them

Governance requirements:

- same as the base Team Readiness route

Fail-closed behavior:

- unsupported or uncertified scopes must fail closed and must not silently
  downgrade into another explanation type

Preferred route strategy:

- implement the query-parameter form first unless repository route conventions
  favor path-specific scope routing
- preserve one shared response shape for both forms if both are implemented
  later
- avoid adding route variants that imply recommendation, selection, ranking,
  prediction, or advice

## 4. Shared Response Shape

All future explanation routes should return a stable envelope.

Successful response shape:

```json
{
  "status": "ok",
  "explanation_type": "availability_explanation",
  "certification_status": "certified_with_non_blocking_observations",
  "route_status": "internal_or_uncertified_until_route_certification",
  "explanation": {
    "explanation_id": "explanation:availability_state:pitcher:123:...",
    "scope": "availability_state",
    "subject_type": "pitcher",
    "subject_id": "123",
    "state_explained": "Monitor",
    "summary": "This availability state reflects recent workload and freshness evidence.",
    "primary_reasons": [],
    "supporting_evidence": [],
    "limitations": [],
    "freshness": {},
    "trust": {},
    "confidence": {},
    "governance": {
      "ranking_applied": false,
      "selection_made": false,
      "recommendation_made": false,
      "prediction_made": false,
      "decision_scope": "explanation_only",
      "advice_scope": "none"
    },
    "generated_at": "2026-06-04T00:00:00Z"
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

Shared response requirements:

- `status` must be explicit
- `explanation_type` must identify the certified track
- `certification_status` must be explicit
- `route_status` must not imply production certification before a separate
  route certification phase
- `explanation` must use the deterministic V4 explanation object shape
- envelope-level `governance` must mirror explanation-level governance
- responses must not include decision, ranking, selection, prediction,
  recommendation, best/preferred, matchup, or pitcher-choice fields

Stable route statuses:

```text
internal_or_uncertified_until_route_certification
certified_route_pending_rollout
production_exposed_if_separately_approved
```

Only the first status is appropriate for initial Phase 15 route implementation.

## 5. Fail-Closed Response Shape

Explanation routes must fail closed when explanations cannot be generated
safely.

Unavailable response shape:

```json
{
  "status": "unavailable",
  "explanation_type": "team_readiness_explanation",
  "certification_status": "certified_with_non_blocking_observations",
  "route_status": "internal_or_uncertified_until_route_certification",
  "explanation": null,
  "limitations": [
    {
      "type": "missing_data",
      "label": "Required explanation inputs are unavailable",
      "summary": "The explanation cannot be generated without the required source payload."
    }
  ],
  "refusal": {
    "refused": true,
    "reason_code": "missing_source_data",
    "summary": "Explanation generation failed closed because required source data is unavailable."
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

Fail-closed response requirements:

- no fabricated evidence
- no guessed state
- no silent fallback to uncertified explanation types
- no safe-looking response when governance metadata is missing or malformed
- no recommendation or advice language
- visible limitation or refusal metadata
- governance payload present even when `explanation` is null

## 6. Error Handling Contract

Future route implementation should treat unsafe or unavailable explanation
requests as governed contract outcomes.

| Error case | Recommended status code | Response shape | Governance requirement | Logging / audit expectation |
| --- | --- | --- | --- | --- |
| Unknown subject | `404` | `status: "unavailable"`, `explanation: null`, `missing_data` limitation | Required in envelope | Log subject identifier and route, not private or inferred data |
| Unsupported scope | `400` or `422` | `status: "unavailable"`, `unsupported_scope` refusal | Required in envelope | Log requested scope and certified scope list |
| Uncertified explanation type | `403` or `422` | `status: "unavailable"`, `uncertified_source` limitation | Required in envelope | Log requested explanation type and certification boundary |
| Missing source data | `503` or `424` | `status: "unavailable"`, `missing_data` limitation | Required in envelope | Log missing source surface and data freshness if available |
| Stale source data | `503` or `424` when unsafe | `status: "unavailable"` or degraded shape with `stale_data` limitation | Required in envelope | Log freshness status and source timestamp if available |
| Internal builder validation failure | `500` with governed fail-closed body | `status: "unavailable"`, builder validation limitation | Required in envelope | Log validation failure class and safe reason code |
| Prohibited query intent | `400` or `422` | `status: "unavailable"`, unsafe intent refusal | Required in envelope | Log query key only, not user decision intent beyond rejected field |

Error handling must remain contract-first. It should not expose stack traces,
internal private values, or inferred baseball decisions in response bodies.

## 7. Governance Contract

Every future explanation API response, including errors and unavailable states,
must preserve:

```text
ranking_applied = false
selection_made = false
recommendation_made = false
prediction_made = false
decision_scope = "explanation_only"
advice_scope = "none"
```

API-level governance requirements:

- governance must appear at the response-envelope level
- successful responses must also include the same governance payload inside the
  explanation object
- route validators must reject unsafe query parameters that imply ranking,
  selection, prediction, recommendation, best/preferred arm behavior, matchup
  advice, pitcher-level advice, or decision automation
- if source governance metadata is missing, unsafe, or malformed, the route
  must fail closed
- response ordering must not imply quality ranking or preferred arms
- response language must explain evidence and limitations, not tell the user
  what to do

Prohibited response fields include:

```text
rank
ranking
selected
selection
recommended
recommendation
best
preferred
priority
matchup_advice
pitcher_advice
decision
prediction
```

Field names that are already part of certified historical contracts must not be
expanded into V4 explanation routes without a separate governance review.

## 8. Certification Boundary

Only certified explanation types can be API-exposed.

Certified explanation types:

- Availability Explanations
- Team Operations Readiness Explanations

Current certification limits:

- both tracks are certified with non-blocking observations
- both tracks are certified for internal backend explanation construction only
- neither track has certified API route exposure yet
- neither track has certified frontend or Dashboard rendering yet
- neither track has rollout approval as an explanation API surface

Future explanation types require separate certification before exposure.

Future route implementation must not use the existence of a certified backend
adapter as automatic route certification. Route behavior, request validation,
error handling, response envelopes, and fail-closed behavior require their own
tests and certification review.

## 9. Testing Requirements

Future Phase 15 route tests should verify:

- route returns a governed Availability explanation for a valid certified
  availability input
- route returns a governed Team Operations readiness explanation for a valid
  certified readiness input
- route preserves deterministic payload shape for identical inputs
- route exposes envelope-level and explanation-level governance metadata
- route rejects unsupported scopes
- route rejects uncertified explanation types
- route rejects prohibited query intent such as `rank`, `recommend`, `select`,
  `best`, `preferred`, `matchup`, or `predict`
- route fails closed on missing source data
- route fails closed on stale unsafe source data
- route fails closed on malformed governance metadata
- route does not expose ranking fields
- route does not expose selection fields
- route does not expose recommendation fields
- route does not expose prediction fields
- route does not expose best/preferred labels
- route does not expose matchup or pitcher-level advice
- route does not alter Availability Engine behavior
- route does not alter Team Operations Readiness behavior
- route does not alter Recommendation Engine V1 or V2 behavior
- existing V4 domain, builder, availability explanation, and readiness
  explanation tests still pass

Certification tests for the route should also review:

- successful response shape
- unavailable/fail-closed response shape
- error status-code behavior
- governance invariant visibility
- limitation visibility
- freshness/trust/confidence visibility
- internal/uncertified route status visibility until route certification

## 10. Implementation Readiness Decision

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_15_EXPLANATION_API_ROUTE_IMPLEMENTATION
```

Rationale:

- Availability Explanation Integration is certified with non-blocking
  observations
- Team Operations Readiness Explanations are certified with non-blocking
  observations
- Phase 14 defines route candidates, shared response shapes, fail-closed
  response shapes, safe error cases, governance requirements, certification
  boundaries, and testing requirements
- the next phase can implement route-level exposure without changing source
  engine behavior or adding frontend/UI surfaces

Recommended next milestone:

```text
V4 Phase 15 - Explanation API Route Implementation
```

Recommended Phase 15 scope:

- implement backend route integration only
- expose certified explanation types only
- keep routes internal or explicitly uncertified until route certification
- add route tests for success, unsupported scope, unsafe query intent,
  fail-closed behavior, governance invariants, and engine preservation
- do not implement frontend UI, Dashboard rendering, rollout approval, or
  uncertified explanation types
