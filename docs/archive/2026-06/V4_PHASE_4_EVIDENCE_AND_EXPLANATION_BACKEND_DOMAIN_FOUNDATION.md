# BaseballOS V4 Phase 4 - Evidence And Explanation Backend Domain Foundation

## Phase Status

Phase status:

```text
V4_PHASE_4_EVIDENCE_AND_EXPLANATION_BACKEND_DOMAIN_FOUNDATION_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
BACKEND_DOMAIN_FOUNDATION_ONLY
```

This phase creates the first backend implementation foundation for V4 Evidence
and Explanation. It adds internal domain contracts, stable vocabularies,
governance validation, deterministic serialization, and focused backend tests.

This phase does not integrate V4 explanations into availability, readiness,
recommendation, API route, database, or frontend behavior.

## What Was Implemented

V4 Phase 4 implements an internal backend explanation domain package:

```text
backend/explanations/
```

The domain foundation defines:

- explanation scope vocabulary
- subject type vocabulary
- evidence item representation
- explanation object representation
- stable reason code definitions
- stable limitation type definitions
- governance payload object
- freshness reference object
- trust reference object
- confidence object
- validation helpers
- deterministic JSON-compatible serialization helpers

The package is dependency-light and isolated from existing runtime surfaces. It
does not call Availability Engine, Recommendation Engine V1/V2, Team
Operations Bullpen Readiness, Flask routes, persistence, or frontend code.

## Domain Module Location

Files created:

```text
backend/explanations/__init__.py
backend/explanations/contracts.py
backend/tests/test_v4_explanations_domain_foundation.py
```

The implementation follows the existing backend pattern used by
`backend/recommendation` and `backend/team_operations`: frozen dataclasses,
stable constants, explicit `to_dict()` serialization, and focused pytest
coverage.

## Supported Scopes

Supported V4 explanation scopes:

```text
availability_state
workload_state
readiness_state
risk_distribution
freshness_state
trust_state
coverage_state
```

These scopes explain existing governed states only. They do not authorize new
decision behavior or change any existing calculations.

## Supported Subject Types

Supported V4 subject types:

```text
pitcher
team
bullpen
distribution
system
```

Subject types identify what an explanation describes. They do not create
pitcher ordering, pitcher selection, pitcher recommendation, matchup advice, or
decision automation.

## Supported Reason Codes

Stable Phase 4 reason codes:

```text
WORKLOAD_RECENT_USAGE_ELEVATED
FRESHNESS_STALE_SOURCE
COVERAGE_PARTIAL
TRUST_LIMITED
AVAILABILITY_MONITOR_THRESHOLD_MET
READINESS_DEGRADED_BY_LIMITATIONS
```

Reason code behavior:

- codes are stable uppercase identifiers
- each code has a display label
- each code has a neutral explanatory summary
- each code maps to an allowed explanation scope
- unsupported codes are rejected
- codes do not encode hidden priority, ranking, selection, recommendation, or
  prediction behavior

## Supported Limitation Types

Stable Phase 4 limitation types:

```text
missing_data
stale_data
partial_coverage
uncertified_source
limited_confidence
insufficient_context
```

Limitation behavior:

- unsupported limitation types are rejected
- limitations serialize with severity, summary, affected scopes, and refusal
  requirement
- affected scopes must use supported V4 explanation scopes
- limitations explain confidence and evidence boundaries
- limitations do not override fail-closed behavior or turn explanations into
  advice

## Domain Objects

Phase 4 defines these domain objects:

| Object | Purpose |
| --- | --- |
| `V4GovernancePayload` | Carries mandatory false governance flags and explanation-only scope. |
| `V4FreshnessReference` | Carries source freshness status, data-through, sync, source update, and failure summary fields. |
| `V4TrustReference` | Carries trust status, source, contract, certification status, and trust failure fields. |
| `V4Confidence` | Carries explanation confidence level and summary. |
| `V4Reason` | Represents one stable reason code with label, summary, and scope. |
| `V4Limitation` | Represents one visible limitation attached to explanation scopes. |
| `V4EvidenceItem` | Represents one source-attributed evidence item with freshness, trust, impact, and optional limitation. |
| `V4Explanation` | Represents the full explanation object with reasons, evidence, limitations, freshness, trust, confidence, and governance. |

All domain objects serialize to JSON-compatible dictionaries through `to_dict()`
methods with deterministic key ordering.

## Governance Payload Behavior

Every V4 governance payload preserves:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The backend domain rejects attempts to set:

- `ranking_applied` to true
- `selection_made` to true
- `recommendation_made` to true
- `prediction_made` to true
- `decision_scope` to anything other than `explanation_only`
- `advice_scope` to anything other than `none`

The domain also includes recursive governance scanning for forbidden fields
such as ranking, selection, recommendation, prediction, best/preferred arm,
hidden priority, pitcher choice, and matchup advice fields.

## Validation Coverage

Phase 4 validation covers:

- required explanation fields
- unsupported explanation scopes
- unsupported subject types
- unsupported reason codes
- unsupported limitation types
- unsupported freshness status vocabulary
- unsupported trust status vocabulary
- unsupported confidence vocabulary
- missing governance fields
- unsafe governance true values
- unsafe decision or advice scope values
- forbidden nested behavior fields

Validation is intentionally local to the V4 domain layer. It does not validate
API requests because no API route is implemented in this phase.

## Test Coverage

Backend tests were added in:

```text
backend/tests/test_v4_explanations_domain_foundation.py
```

The tests verify:

- supported scope vocabulary
- supported subject type vocabulary
- supported reason code vocabulary
- supported limitation vocabulary
- validator acceptance and rejection behavior
- governance payload defaults
- governance payload rejection of unsafe values
- missing governance field validation
- evidence item creation and serialization shape
- explanation object creation and serialization shape
- deterministic serialization for identical inputs
- prohibited behavior fields remain absent or false
- recursive detection of forbidden nested fields

The tests explicitly assert:

```text
ranking_applied is False
selection_made is False
recommendation_made is False
prediction_made is False
decision_scope == "explanation_only"
advice_scope == "none"
```

## Intentionally Not Implemented

V4 Phase 4 does not implement:

- API routes
- frontend UI
- frontend client normalization
- database migration
- availability integration
- readiness integration
- recommendation integration
- dashboard behavior changes
- fatigue calculation changes
- availability calculation changes
- Recommendation Engine behavior changes
- Team Operations Bullpen Readiness behavior changes
- trust logic changes
- freshness logic changes
- public route exposure
- production certification
- rollout approval

## Governance Preservation

V4 Phase 4 preserves:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
```

V4 Phase 4 does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred arm behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation

V4 may explain existing governed states.

V4 may not decide.

## Remaining Risks

Remaining risks are non-blocking for the backend domain foundation:

- V4 is not yet integrated with real availability or readiness evidence.
- No API contract has been exposed for V4 explanation objects.
- No frontend rendering language has been certified.
- Future builder phases must prove that explanations remain traceable to
  existing governed source evidence.
- Future integration phases must prove V1, V2, and V3 behavior remains
  unchanged.

## Recommended Next Milestone

Recommended next milestone:

```text
V4 Phase 5 - Evidence And Explanation Deterministic Builder
```

Phase 5 should add deterministic builder functions over safe internal inputs
or fixtures using the Phase 4 domain contracts. It should not expose public API
routes, implement frontend UI, change existing availability/readiness/
recommendation behavior, or approve rollout.
