# BaseballOS V4 Phase 10 - Team Operations Readiness Explanation Architecture

## Phase Status

Phase status:

```text
V4_PHASE_10_TEAM_OPERATIONS_READINESS_EXPLANATION_ARCHITECTURE_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_11_READINESS_EXPLANATION_IMPLEMENTATION
```

This phase converts the V4 Phase 9 Team Operations Readiness Explanation
capability definition into a technical architecture plan. It is planning only.
It does not implement backend behavior, frontend behavior, API routes,
dashboard rendering, runtime integration, database changes, certification, or
rollout.

Availability Explanation Integration remains the only certified V4 explanation
integration. Team Operations Readiness explanations remain planned, not
implemented, certified, exposed, or approved for rollout.

## 1. Architecture Overview

Future Team Operations Readiness explanation generation should use a bounded
adapter architecture.

Participating systems:

| System | Role in future readiness explanations |
| --- | --- |
| Team Operations Bullpen Readiness | Source of existing team-level readiness state, constraints, workload pressure, availability distribution, coverage, trust metadata, freshness metadata, refusal metadata, fail-closed metadata, limitations, explanations, and governance metadata. |
| Availability Engine | Indirect evidence contributor through existing readiness payloads such as availability distribution and coverage. It should not be called directly by the readiness explanation adapter unless a later implementation phase proves that direct dependency is necessary. |
| V4 Explanation Domain Foundation | Provides explanation scopes, subject types, reason code vocabulary, limitation vocabulary, governance payload, validation, and deterministic serialization. |
| V4 Deterministic Builder | Creates validated `V4Explanation` objects, evidence items, limitations, reasons, stable IDs, and stable serialized output. |
| Future readiness explanation adapter | Planned integration layer that maps existing readiness output into V4 explanations without changing readiness calculation behavior. |

Systems that remain unchanged:

- fatigue calculations
- availability calculations
- Team Operations Readiness calculations
- Team Operations Readiness API route behavior
- Recommendation Engine V1 behavior
- certified Recommendation Engine V2 behavior
- V3 readiness dashboard behavior
- database schema
- frontend rendering
- rollout status

Planned integration boundary:

```text
existing readiness payload
  -> future readiness explanation adapter
  -> V4 deterministic builder
  -> V4Explanation objects
```

The adapter should be one-way:

- read existing readiness output
- extract evidence already present in the readiness payload
- map supported evidence into V4 evidence items
- map supported conditions into V4 reason codes
- map data boundaries into V4 limitations
- attach governed defaults through the builder
- return V4 explanation objects
- avoid mutating the original readiness payload

No route, dashboard, or public exposure should be attached until later contract,
certification, and rollout phases authorize it.

## 2. Explanation Scope Architecture

Scope decisions should use existing V4 scope vocabulary where possible. Phase
10 does not implement or extend scopes.

| Scope | Purpose | Inputs | Outputs | Limitations | Governance requirements |
| --- | --- | --- | --- | --- | --- |
| `readiness_state` | Explain the overall Team Operations readiness state. | Readiness status, readiness summary, constraints, workload pressure, coverage state, trust metadata, freshness metadata, refusal metadata, fail-closed state. | One root explanation for the current team or bullpen readiness state. | Must not explain individual pitcher choice; must not derive new readiness state. | Governance defaults must be attached automatically and all decision/advice flags must remain safe. |
| `team_readiness_state` | Candidate alias if future architecture needs a clearer team-level name. | Same as `readiness_state`. | Same conceptual output as `readiness_state`. | Existing V4 contracts do not currently define this scope. | Do not add unless Phase 11 implementation finds the existing `readiness_state` scope ambiguous and tests cover the extension. |
| `workload_pressure` | Explain workload pressure evidence behind readiness constraints. | Workload pressure state, high-risk workload counts, critical workload counts, fatigue distribution, workload constraints. | Supporting explanation or evidence group for workload pressure. | Must not identify which pitcher to use or avoid. | Must remain aggregate or context-level only. |
| `coverage_state` | Explain role, handedness, availability, or evidence coverage constraints. | Coverage inventory, handedness coverage, availability distribution, coverage state, partial or missing coverage limitations. | Supporting explanation or evidence group for coverage limitations. | Coverage counts must not imply priority ordering. | Must not create hidden pitcher ordering or coverage-based advice. |
| `freshness_state` | Explain freshness impact on readiness confidence or refusal. | Freshness state, data-through date, latest workload date, latest sync status, last successful sync, stale or missing warnings. | Supporting explanation for stale, missing, incomplete, historical, unknown, or current source state. | Missing timestamps must become limitations, not fabricated dates. | Must preserve fail-closed and refusal semantics when freshness is unsafe. |
| `trust_state` | Explain trust, source evidence, validation, and governance limits. | Trust confidence, confidence reasons, source evidence state, governance state, trust validation errors, refusal reasons. | Supporting explanation for trust-limited readiness. | Must not convert trust confidence into pitcher advice. | Unsafe trust metadata must fail closed in implementation. |
| `confidence_state` | Candidate scope for readiness confidence explanation. | Confidence value, confidence reasons, trust metadata, freshness metadata, limitations. | Supporting explanation for high, medium, low, or unknown confidence. | Existing V4 contracts do not currently define this scope. | Prefer existing `trust_state` plus `limited_confidence` limitation unless a future phase proves this scope is necessary. |

Architecture decision:

```text
Use readiness_state as the primary architecture scope.
Use existing workload_state, coverage_state, freshness_state, and trust_state
as supporting scopes where future implementation needs separate explanation
objects or evidence groups.
Do not add team_readiness_state or confidence_state unless Phase 11 proves
that current vocabulary is insufficient.
```

## 3. Evidence Mapping Architecture

Readiness explanation evidence should be sourced from existing Team Operations
Readiness payloads. Evidence should not be fabricated, inferred from absent
data, or pulled from new external sources.

Evidence-to-scope mapping:

| Evidence source | Primary scope | Attachment strategy |
| --- | --- | --- |
| Readiness status code and display label | `readiness_state` | Attach as base categorical evidence. |
| Readiness summary | `readiness_state` | Use for explanation summary context, not as proof by itself. |
| Operational constraints | `readiness_state` | Attach categories and severities as structured evidence or reason triggers. |
| Workload pressure state | `workload_state` | Attach as categorical evidence and reason trigger when elevated or unknown. |
| High-risk workload counts | `workload_state` | Attach as numeric evidence when present. |
| Critical workload counts | `workload_state` | Attach as numeric evidence when present. |
| Fatigue distribution | `workload_state` | Attach as aggregate distribution evidence when present. |
| Availability distribution | `readiness_state` or `coverage_state` | Attach as aggregate availability context, not pitcher ordering. |
| Coverage metrics | `coverage_state` | Attach role, handedness, availability, or evidence coverage counts when present. |
| Freshness metrics | `freshness_state` | Attach data-through, latest workload, sync, stale warning, and missing warning fields when present. |
| Trust metrics | `trust_state` | Attach confidence, data state, source evidence state, governance state, validation errors, and confidence reasons. |
| Confidence metrics | `trust_state` or candidate `confidence_state` | Attach as trust evidence unless future implementation adds `confidence_state`. |
| Refusal metadata | `readiness_state` or `trust_state` | Attach reason code, reason summary, and refusal state when present. |
| Fail-closed metadata | `readiness_state` | Attach fail-closed state and reason evidence when present. |
| Governance metadata | all generated explanations | Attach through V4 builder governance defaults, not as caller-provided overrides. |

Evidence attachment requirements:

- Use V4 builder evidence helpers when implementation begins.
- Preserve field labels, values, units, source, freshness reference, trust
  reference, and impact where available.
- Use aggregate evidence only; do not sort pitchers by quality or priority.
- Represent missing evidence with limitations.
- Attach freshness and trust references to evidence where the readiness payload
  supplies those metadata fields.

Determinism requirements:

- Sort extracted evidence by stable category and field name before building
  evidence items.
- Use deterministic evidence IDs from the Phase 5 builder unless explicit IDs
  are required by a future retained-evidence strategy.
- Use canonical JSON serialization for retained artifacts and tests.
- Identical readiness inputs should produce identical explanation dictionaries,
  evidence IDs, explanation IDs, and serialized strings.

## 4. Reason Code Architecture

Reason code ownership should remain in the V4 Explanation domain vocabulary.
The future readiness adapter should map readiness conditions to supported V4
reason codes. It should not create ad hoc reason strings outside the contract.

Existing reason codes suitable for initial readiness architecture:

| Reason code | Usage |
| --- | --- |
| `READINESS_DEGRADED_BY_LIMITATIONS` | Use when limitations materially explain a constrained, stressed, data-limited, refused, or degraded readiness state. |
| `WORKLOAD_RECENT_USAGE_ELEVATED` | Use when workload pressure, high-risk counts, critical workload counts, or fatigue distribution explain readiness constraints. |
| `FRESHNESS_STALE_SOURCE` | Use when stale, missing, incomplete, historical, or unknown freshness contributes to readiness limits or refusal. |
| `COVERAGE_PARTIAL` | Use when coverage inventory, handedness coverage, availability distribution, or source evidence coverage is partial or missing. |
| `TRUST_LIMITED` | Use when trust metadata, confidence reasons, source evidence state, governance state, or validation errors limit readiness confidence. |

Candidate readiness-focused reason code families:

| Candidate reason code | Purpose | Phase 10 decision |
| --- | --- | --- |
| `READINESS_DEGRADED_BY_FRESHNESS` | More precise degraded-readiness reason for freshness-specific degradation. | Candidate only; implement only if existing `FRESHNESS_STALE_SOURCE` is too narrow. |
| `READINESS_DEGRADED_BY_COVERAGE` | More precise degraded-readiness reason for coverage-specific degradation. | Candidate only; implement only if `COVERAGE_PARTIAL` is insufficient for readiness root explanations. |
| `READINESS_DATA_LIMITED` | Direct explanation for data-limited readiness status. | Candidate only; useful if data-limited status needs a root reason distinct from specific missing/stale/partial evidence. |
| `WORKLOAD_PRESSURE_ELEVATED` | Direct explanation for elevated workload pressure. | Candidate only; useful if workload pressure differs from recent usage evidence. |
| `TRUST_LIMITED_FOR_READINESS` | Readiness-specific trust limitation reason. | Candidate only; use only if generic `TRUST_LIMITED` cannot certify readiness behavior clearly. |
| `CONFIDENCE_REDUCED` | Direct explanation for reduced readiness confidence. | Candidate only; may be covered by `limited_confidence` limitation plus trust evidence. |
| `READINESS_REFUSED_BY_FAIL_CLOSED` | Direct explanation for readiness refusal or fail-closed state. | Candidate only; useful if refusal needs explicit certification proof. |

Certification expectations:

- Every reason code must have a stable label and summary.
- Every reason code must map to one or more deterministic input conditions.
- Unsupported reason codes must fail validation.
- Reason mapping must be covered by focused tests.
- Reason code additions must update docs, contracts, and tests together.

Stability expectations:

- Do not rename certified reason codes.
- Do not change certified reason semantics without a new review.
- Do not overload a reason code to imply advice, ranking, selection,
  recommendation, or prediction.

## 5. Limitation Architecture

Existing V4 limitation types are sufficient for the initial readiness
architecture:

```text
missing_data
stale_data
partial_coverage
uncertified_source
limited_confidence
insufficient_context
```

Reuse strategy:

| Limitation type | Readiness use |
| --- | --- |
| `missing_data` | Required readiness, trust, freshness, coverage, workload, refusal, or governance evidence is unavailable. |
| `stale_data` | Source data or readiness freshness evidence is not current. |
| `partial_coverage` | Coverage inventory, handedness coverage, availability distribution, or source evidence coverage is incomplete. |
| `uncertified_source` | Evidence source or explanation source is not certified for readiness explanation use. |
| `limited_confidence` | Trust or readiness confidence is medium, low, unknown, or otherwise reduced. |
| `insufficient_context` | Readiness can be explained only at a shallower level because BaseballOS lacks deeper context. |

Extension strategy:

- Add a new limitation type only when a future implementation cannot accurately
  represent a readiness boundary with current vocabulary.
- Any extension must update V4 contracts, builders, tests, docs, and
  certification review.
- Limitation extensions must remain descriptive and must not become decision
  instructions.

Certification expectations:

- Limitations must be visible in generated explanations.
- Missing evidence must become a limitation, not fabricated evidence.
- Stale freshness must remain explicit.
- Partial coverage must not be hidden behind a high-level summary.
- Limited confidence must not be converted into advice.

## 6. Builder Integration Plan

Future readiness explanation implementation should reuse the Phase 5
deterministic builder layer.

Reusable pieces:

- `build_explanation(...)`
- `build_evidence_item(...)`
- `build_numeric_evidence(...)`
- `build_percentage_evidence(...)`
- `build_limitation(...)`
- `build_reason(...)`
- `build_reasons(...)`
- `serialize_explanation(...)`
- `stable_json_dumps(...)`
- Phase 4 governance payload defaults
- Phase 4 scope, subject, reason, limitation, freshness, trust, confidence,
  and forbidden-field validation

Readiness-specific pieces planned for future implementation:

- a readiness explanation adapter
- safe extraction of readiness payload fields
- readiness status to reason mapping
- constraint category to reason mapping
- workload pressure evidence mapping
- availability distribution evidence mapping
- coverage evidence mapping
- freshness evidence mapping
- trust evidence mapping
- refusal and fail-closed evidence mapping
- readiness limitation mapping
- readiness subject-id strategy
- deterministic ordering of evidence, reasons, and limitations

Candidate future module boundary:

```text
backend/explanations/readiness.py
```

The candidate module should be separate from:

- `backend/team_operations/bullpen_readiness.py`
- `backend/api/team_operations.py`
- frontend Dashboard components
- Recommendation Engine modules

Areas requiring future extension:

- whether current `readiness_state` is enough or a `team_readiness_state`
  scope should be added
- whether `confidence_state` is necessary or trust scope plus
  `limited_confidence` is enough
- whether existing reason codes are enough for root readiness explanations
- whether explanation output should be one root explanation or root plus
  supporting scoped explanations
- whether future API exposure should embed explanations in readiness output or
  expose them through a separate explanation route

## 7. Readiness Explanation Object Shape

Future readiness explanations should use V4 explanation object semantics.

Conceptual root explanation shape:

```json
{
  "scope": "readiness_state",
  "subject_type": "bullpen",
  "subject_id": "team:<team_id>:bullpen",
  "state_explained": "operationally_constrained",
  "summary": "Readiness is constrained by visible workload, coverage, freshness, or trust evidence.",
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations"
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "readiness_status",
      "label": "Readiness status",
      "value": "operationally_constrained",
      "source": "team_operations_bullpen_readiness"
    }
  ],
  "limitations": [],
  "freshness": {
    "status": "current"
  },
  "trust": {
    "status": "trusted"
  },
  "confidence": {
    "level": "medium"
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

Conceptual freshness-limited explanation shape:

```json
{
  "scope": "freshness_state",
  "subject_type": "bullpen",
  "subject_id": "team:<team_id>:bullpen",
  "state_explained": "freshness_limited",
  "summary": "Freshness metadata limits the readiness explanation.",
  "primary_reasons": [
    {
      "code": "FRESHNESS_STALE_SOURCE",
      "label": "Source freshness stale"
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "freshness_state",
      "label": "Freshness state",
      "value": "stale",
      "source": "team_operations_bullpen_readiness"
    }
  ],
  "limitations": [
    {
      "limitation_type": "stale_data",
      "summary": "Readiness source data is not current."
    }
  ],
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

Conceptual refused explanation shape:

```json
{
  "scope": "readiness_state",
  "subject_type": "bullpen",
  "subject_id": "team:<team_id>:bullpen",
  "state_explained": "refused",
  "summary": "Readiness explanation is refused because required metadata is unsafe or unavailable.",
  "primary_reasons": [
    {
      "code": "READINESS_DEGRADED_BY_LIMITATIONS",
      "label": "Readiness degraded by limitations"
    }
  ],
  "supporting_evidence": [
    {
      "evidence_type": "fail_closed_state",
      "label": "Fail-closed state",
      "value": "refused",
      "source": "team_operations_bullpen_readiness"
    }
  ],
  "limitations": [
    {
      "limitation_type": "missing_data",
      "summary": "Required readiness metadata is unavailable."
    }
  ],
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

These examples are conceptual only. They do not implement or change any
runtime response shape.

## 8. Testing Architecture

Future Phase 11 implementation should add focused backend tests before any API
or frontend exposure.

Required test categories:

- reason mapping tests
- evidence attribution tests
- limitation mapping tests
- determinism tests
- governance tests
- behavior-preservation tests
- fail-closed tests
- forbidden-field tests
- unsupported vocabulary tests

Minimum test expectations:

- root readiness explanation for operationally stable readiness
- root readiness explanation for operationally constrained readiness
- root readiness explanation for operationally stressed readiness
- data-limited readiness explanation
- refused readiness explanation
- workload pressure evidence appears when present
- availability distribution evidence appears when present
- coverage evidence appears when present
- freshness evidence appears when present
- trust evidence appears when present
- missing evidence becomes a limitation
- stale evidence becomes a limitation
- partial coverage becomes a limitation
- limited confidence becomes a limitation
- identical inputs produce identical serialized output
- explanation generation does not mutate readiness payloads
- readiness statuses remain unchanged
- V2 recommendation tests remain unaffected

Governance test assertions:

```text
ranking_applied is False
selection_made is False
recommendation_made is False
prediction_made is False
decision_scope == "explanation_only"
advice_scope == "none"
```

Behavior-preservation tests must prove no changes to:

- fatigue calculations
- availability calculations
- Team Operations Readiness calculations
- Team Operations Readiness status assignment
- Recommendation Engine behavior
- API response behavior

## 9. Certification Architecture

Future Team Operations Readiness explanation certification must verify:

- no recommendation behavior
- no selection behavior
- no ranking behavior
- no prediction behavior
- no best/preferred/recommended behavior
- no hidden priority ordering
- no pitcher-level advice
- no matchup advice
- evidence attribution correctness
- reason code stability
- reason code determinism
- limitation visibility
- trust metadata visibility
- freshness metadata visibility
- refusal metadata visibility
- fail-closed metadata visibility
- governance preservation
- deterministic output
- readiness calculation preservation
- API contract preservation unless a later contract phase authorizes a safe
  extension
- frontend non-exposure until a later UI phase authorizes it

Certification should proceed only after:

- Phase 11 implements the internal backend readiness explanation adapter
- focused backend tests pass
- existing backend regression tests pass
- governance invariants are visible in generated explanations
- all missing or unsafe evidence paths produce limitations or refused
  explanation output rather than fabricated evidence
- no user-facing exposure is implied by backend implementation alone

## 10. Implementation Readiness Decision

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_11_READINESS_EXPLANATION_IMPLEMENTATION
```

Rationale:

- Phase 9 established the capability boundary and found no planning blocker.
- Existing Team Operations Readiness payloads expose the evidence categories
  needed for initial readiness explanation generation.
- Existing V4 scopes cover readiness, workload, coverage, freshness, and trust.
- Existing V4 builders can construct deterministic explanations, evidence,
  limitations, reasons, governance payloads, and stable serialized output.
- The Phase 6 availability adapter provides a proven internal adapter pattern
  that can be reused for readiness without changing source behavior.
- Existing limitation types are sufficient for the first implementation pass.

Recommended next milestone:

```text
V4 Phase 11 - Team Operations Readiness Explanation Implementation
```

Phase 11 should implement only an internal backend readiness explanation
adapter and focused tests. It should not expose API routes, modify Dashboard UI,
change readiness calculations, change Recommendation Engine behavior, approve
certification, or approve rollout.
