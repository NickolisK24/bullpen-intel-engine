# BaseballOS V3 Phase 4 - Team Operations Bullpen Readiness API Contract And Certification Requirements

## Decision

Status:

```text
V3_PHASE_4_TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT_AND_CERTIFICATION_REQUIREMENTS_COMPLETE
```

Approved planning contract:

```text
TEAM_OPERATIONS_BULLPEN_READINESS_API_CONTRACT
```

Chosen route strategy:

```text
GET /api/team-operations/bullpen-readiness
```

Recommended next milestone:

```text
BaseballOS V3 Phase 5 Team Operations Bullpen Readiness Backend Domain Foundation
```

V3 Phase 4 defines the formal API contract and certification requirements for
Team Operations Bullpen Readiness. This phase is planning and documentation
only. It does not implement an endpoint, change API behavior, change frontend
runtime behavior, or authorize production rollout.

## Phase Purpose

The purpose of V3 Phase 4 is to remove ambiguity before implementation begins.

This phase defines:

- endpoint strategy
- request contract
- response contract
- readiness status contract
- constraint contract
- workload pressure contract
- availability distribution contract
- coverage inventory contract
- handedness coverage contract
- explanation and limitation contracts
- trust, freshness, refusal, governance, and fail-closed metadata contracts
- successful, degraded, and refused response examples
- backend, frontend, accessibility, governance, testing, and rollout
  certification requirements

Future implementation must satisfy this contract before it can be certified.

## Scope

In scope:

- Team Operations API strategy
- endpoint strategy
- route naming decision
- request contract
- response contract
- readiness status contract
- constraint contract
- workload pressure contract
- availability distribution contract
- coverage inventory contract
- handedness coverage contract
- explanation contract
- limitation contract
- trust metadata contract
- freshness metadata contract
- refusal metadata contract
- governance metadata contract
- fail-closed contract
- response examples
- certification requirements
- risks and mitigations
- recommended next milestone

Out of scope:

- runtime implementation
- backend code changes
- frontend code changes
- API route registration
- database schema changes
- fatigue formula changes
- recommendation logic changes
- Recommendation Engine V1 changes
- certified Recommendation Engine V2 behavior changes
- lifecycle promotion
- production rollout
- pitcher ranking
- pitcher recommendation
- pitcher selection
- hidden priority ordering
- matchup advice
- outcome prediction
- injury prediction
- save prediction
- performance prediction

## Relationship To V3 Phase 2

V3 Phase 2 defined Team Operations Bullpen Readiness as a governed
intelligence layer that summarizes the operational state of a bullpen from
existing BaseballOS workload, availability, freshness, trust, and roster
coverage evidence.

Phase 2 established that the capability may describe:

- team-level bullpen readiness state
- operational constraints
- workload pressure
- handedness coverage
- role or coverage inventory
- availability distribution
- freshness and trust limitations
- refusal conditions
- explainable contributing factors

Phase 2 also established that the capability must not rank pitchers, select
pitchers, recommend pitchers, predict outcomes, infer injuries, predict saves,
predict performance, provide matchup advice, or tell the user who to use.

V3 Phase 4 converts those capability boundaries into a formal API contract.

## Relationship To V3 Phase 3

V3 Phase 3 defined the implementation plan. It recommended a separate Team
Operations backend/API surface rather than extending the certified
Recommendation Engine V2 bullpen-state endpoint.

Phase 3 proposed:

- a Team Operations domain layer
- a governed readiness response shape
- trust and freshness metadata
- refusal and fail-closed behavior
- summary-first Dashboard presentation
- backend and frontend certification tests
- rollout gates

V3 Phase 4 turns that plan into an official contract and certification
specification. Future implementation should follow this contract unless a
later governance phase explicitly changes it.

## Team Operations API Strategy

Team Operations Bullpen Readiness should be exposed as a Team Operations API
surface, not as an expansion of Recommendation Engine V2.

Strategy:

- keep the certified V2 recommendation endpoint stable
- define readiness as a separate operations capability
- make the route name describe the operational resource
- keep readiness output team-level or context-level
- require visible governance metadata in every response
- require visible trust, freshness, refusal, and fail-closed metadata
- fail closed when required metadata is missing or unsafe

The API must not create a hidden recommendation engine.

## Endpoint Strategy

Approved endpoint strategy:

```text
GET /api/team-operations/bullpen-readiness
```

Rationale:

- the capability is Team Operations, not Recommendation Engine expansion
- the route keeps certified V2 recommendation behavior untouched
- the route is readable and resource-oriented
- the contract version can be carried in metadata instead of forcing a URL
  version on the first Team Operations endpoint
- future incompatible versions can receive a separate versioned route if needed

The existing certified endpoint remains stable:

```text
GET /api/recommendations/v2/bullpen-state
```

No V2 route behavior changes are authorized by this phase.

## Route Naming Decision

The chosen public route is:

```text
GET /api/team-operations/bullpen-readiness
```

The planned backend blueprint can be named:

```text
team_operations
```

The planned route handler can be named:

```text
get_team_operations_bullpen_readiness
```

The planned contract metadata should include:

```json
{
  "capability": "team_operations_bullpen_readiness",
  "contract": "team_operations_bullpen_readiness_api_contract",
  "contract_version": "v3_phase_4"
}
```

Route rules:

- the route must not accept ranking, selection, recommendation, matchup, or
  prediction controls
- the route must fail closed when forbidden request fields are present
- the route must return the same governance metadata in available, degraded,
  refused, and unavailable states
- the route must not change the certified V2 recommendation endpoint

## Request Contract

HTTP method:

```text
GET
```

Allowed query parameters:

| Parameter | Required | Type | Meaning |
|-----------|----------|------|---------|
| `team_id` | Optional until implementation defines multi-team behavior | integer | Current BaseballOS team identifier. |
| `team_abbreviation` | Optional | string | Public team abbreviation when available. |
| `include_details` | Optional | boolean | Allows detail sections to be included without changing summary semantics. |

Request rules:

- request parameters must not change ranking, selection, recommendation, or
  prediction behavior
- `include_details` must only control detail visibility
- absent team scope may return an unavailable or refused state if the backend
  cannot resolve a safe team context
- unsupported parameters must be ignored only if they are harmless; forbidden
  parameters must trigger fail-closed refusal

Forbidden query parameters include:

- `rank`
- `ranking`
- `score`
- `priority`
- `selected_pitcher`
- `selected_pitcher_id`
- `recommended_pitcher`
- `recommended_pitcher_id`
- `preferred_pitcher`
- `best_pitcher`
- `winner`
- `matchup`
- `matchup_advice`
- `prediction`
- `outcome_prediction`
- `injury_prediction`
- `save_prediction`
- `performance_prediction`

## Response Contract

Every response must use this top-level shape:

```json
{
  "capability": "team_operations_bullpen_readiness",
  "scope": "team_bullpen_readiness",
  "contract": "team_operations_bullpen_readiness_api_contract",
  "contract_version": "v3_phase_4",
  "contract_state": "available",
  "ranking_applied": false,
  "selection_made": false,
  "generated_at": "ISO-8601 timestamp",
  "team": {},
  "readiness": {},
  "constraints": [],
  "workload_pressure": {},
  "availability_distribution": {},
  "coverage_inventory": {},
  "handedness_coverage": {},
  "explanations": [],
  "limitations": [],
  "trust_metadata": {},
  "freshness": {},
  "refusal": {},
  "fail_closed": {}
}
```

Allowed `contract_state` values:

- `available`
- `degraded`
- `refused`
- `unavailable`

Response rules:

- all output must be team-level or context-level
- no pitcher ranking may appear
- no pitcher recommendation may appear
- no pitcher selection may appear
- no best or preferred label may appear
- no hidden priority ordering may appear
- no matchup advice may appear
- no outcome, injury, save, or performance prediction may appear
- every response must preserve `ranking_applied === false`
- every response must preserve `selection_made === false`

## Readiness Status Contract

Readiness object shape:

```json
{
  "status": "Operationally Constrained",
  "status_code": "operationally_constrained",
  "summary": "Team-level readiness is constrained by current workload distribution.",
  "basis": [
    "availability_distribution",
    "workload_pressure",
    "freshness",
    "trust_metadata"
  ]
}
```

Allowed status values:

| Status | Status Code | Meaning |
|--------|-------------|---------|
| Operationally Stable | `operationally_stable` | Current public workload and freshness data support a low-constraint team-level readiness summary. |
| Operationally Constrained | `operationally_constrained` | Meaningful availability, workload, freshness, or coverage constraints exist, but evidence remains sufficient. |
| Operationally Stressed | `operationally_stressed` | Elevated concentration of constrained or unavailable inventory is visible. |
| Data Limited | `data_limited` | Data is stale, partial, low-confidence, incomplete, or coverage-limited. |
| Refused | `refused` | Required evidence or governance metadata is missing, unsafe, or unsupported. |

Readiness rules:

- readiness status is team-level/context-level only
- readiness status must not be assigned to individual pitchers
- readiness status must not produce a pitcher choice
- readiness status must not imply which pitcher should be used

## Constraint Contract

Constraint object shape:

```json
{
  "constraint_id": "freshness_stale",
  "category": "freshness",
  "severity": "blocking",
  "affected_area": "readiness",
  "count": 1,
  "message": "Current workload evidence is stale.",
  "evidence": [
    "data_through: 2026-06-01"
  ]
}
```

Allowed categories:

- `workload`
- `availability`
- `freshness`
- `trust`
- `coverage`
- `refusal`
- `governance`

Allowed severities:

- `informational`
- `caution`
- `blocking`

Constraint rules:

- constraints explain why the team-level state is qualified
- constraints may include counts and evidence
- constraints must not tell the user which pitcher to use

## Workload Pressure Contract

Workload pressure object shape:

```json
{
  "pressure_state": "moderate",
  "pressure_state_code": "moderate",
  "low_count": 4,
  "moderate_count": 2,
  "elevated_count": 1,
  "unknown_count": 0,
  "latest_workload_date": "YYYY-MM-DD",
  "summary": "Recent workload pressure is moderate at the team level."
}
```

Allowed pressure states:

- `low`
- `moderate`
- `elevated`
- `unknown`

Workload rules:

- workload pressure must use public workload and existing fatigue evidence only
- workload pressure must not infer injury
- workload pressure must not forecast performance
- workload pressure must not produce pitcher-level preference

## Availability Distribution Contract

Availability distribution object shape:

```json
{
  "available": 4,
  "monitor": 2,
  "limited": 1,
  "avoid": 0,
  "unavailable": 0,
  "unknown": 0,
  "total": 7
}
```

Availability rules:

- status names map to existing Availability Engine labels
- counts are team-level distribution counts
- member ordering must not be returned unless a future implementation proves
  neutral ordering and certification approves it
- availability distribution must not identify a chosen pitcher

## Coverage Inventory Contract

Coverage inventory object shape:

```json
{
  "active_pitcher_count": 7,
  "current_workload_data_count": 7,
  "missing_workload_data_count": 0,
  "availability_covered_count": 7,
  "availability_missing_count": 0,
  "coverage_state": "covered"
}
```

Allowed coverage states:

- `covered`
- `partial`
- `missing`
- `unknown`

Coverage rules:

- coverage inventory is a count summary
- coverage inventory must not become a depth chart
- coverage inventory must not imply role certainty beyond public roster fields

## Handedness Coverage Contract

Handedness coverage object shape:

```json
{
  "left_handed_count": 2,
  "right_handed_count": 5,
  "unknown_count": 0,
  "coverage_state": "covered",
  "limitations": []
}
```

Handedness rules:

- handedness coverage uses public roster throwing-hand data only
- handedness coverage is count-based
- handedness coverage must not become matchup advice
- missing handedness data must be visible as `unknown_count` or a limitation

## Explanation Contract

Explanation object shape:

```json
{
  "explanation_id": "readiness_operationally_constrained",
  "level": "team",
  "message": "Readiness is operationally constrained because workload pressure is moderate and one coverage constraint is present.",
  "evidence": [
    "pressure_state: moderate",
    "coverage_state: partial"
  ],
  "applies_to": "readiness"
}
```

Allowed levels:

- `team`
- `readiness`
- `constraint`
- `workload`
- `coverage`
- `freshness`
- `trust`
- `refusal`

Explanation rules:

- every available or degraded readiness output must include at least one
  explanation
- refusal responses should include explanation when safe evidence exists
- explanations must be tied to the output they qualify

## Limitation Contract

Limitation object shape:

```json
{
  "limitation_id": "public_workload_data_only",
  "message": "Readiness is based on public workload data tracked by BaseballOS.",
  "severity": "informational",
  "applies_to": "readiness"
}
```

Allowed severities:

- `informational`
- `caution`
- `blocking`

Required baseline limitations:

- public workload data only
- not injury or medical information
- not performance forecast
- no manager intent
- no bullpen warm-up knowledge
- user remains responsible for baseball decisions

## Trust Metadata Contract

Trust metadata object shape:

```json
{
  "scope": "team_bullpen_readiness",
  "capability": "team_operations_bullpen_readiness",
  "confidence": "medium",
  "confidence_reasons": [],
  "data_state": "fresh",
  "source_evidence_state": "represented",
  "governance_state": "compliant",
  "generated_at": "ISO-8601 timestamp",
  "limitations": [],
  "explanations": [],
  "refusal_reasons": [],
  "trust_validation_errors": [],
  "ranking_applied": false,
  "selection_made": false
}
```

Allowed confidence values:

- `high`
- `medium`
- `low`
- `unknown`

Allowed data states:

- `fresh`
- `stale`
- `missing`
- `incomplete`
- `historical`
- `unknown`

Trust rules:

- trust metadata is required in every response
- missing trust metadata must fail closed
- `ranking_applied` must be `false`
- `selection_made` must be `false`

## Freshness Metadata Contract

Freshness object shape:

```json
{
  "freshness_state": "current",
  "data_through": "YYYY-MM-DD",
  "latest_workload_date": "YYYY-MM-DD",
  "last_successful_sync": "ISO-8601 timestamp",
  "latest_sync_status": "success",
  "latest_fatigue_calculated_at": "ISO-8601 timestamp",
  "generated_at": "ISO-8601 timestamp",
  "stale_warning": null,
  "missing_data_warning": null,
  "limitations": []
}
```

Allowed freshness states:

- `current`
- `stale`
- `missing`
- `incomplete`
- `historical`
- `unknown`

Freshness rules:

- data-through date is required when available
- sync timestamp must not substitute for data-through date
- stale freshness must reduce confidence, degrade, or refuse output
- missing freshness metadata must fail closed

## Refusal Metadata Contract

Refusal object shape:

```json
{
  "refused": false,
  "refusal_id": null,
  "reason": null,
  "message": null,
  "applies_to": null,
  "recovery_note": null
}
```

Refusal response shape:

```json
{
  "refused": true,
  "refusal_id": "missing_trust_metadata",
  "reason": "trust_metadata_missing",
  "message": "Readiness output is refused because required trust metadata is missing.",
  "applies_to": "readiness",
  "recovery_note": "Refresh evidence and rerun certification checks before exposing readiness."
}
```

Refusal rules:

- refusal metadata is required when output is refused
- refusal must preserve governance metadata
- refusal must not include unsafe fallback readiness claims
- refusal is a valid product state, not an error to hide

## Governance Metadata Contract

Governance metadata requirements:

```text
ranking_applied === false
selection_made === false
```

Governance metadata object shape:

```json
{
  "ranking_applied": false,
  "selection_made": false,
  "ranking_behavior": false,
  "selection_behavior": false,
  "prediction_behavior": false,
  "best_preferred_recommended_behavior": false,
  "governance_state": "compliant"
}
```

The contract prohibits:

- pitcher ranking
- pitcher recommendation
- pitcher selection
- best labels
- preferred labels
- recommended labels
- hidden priority ordering
- matchup advice
- outcome prediction
- injury prediction
- save prediction
- performance prediction

All outputs must remain team-level or context-level.

## Fail-Closed Contract

Fail-closed object shape:

```json
{
  "failed_closed": false,
  "state": "not_failed_closed",
  "reason_codes": [],
  "critical_failure": false,
  "safe_partial_output_allowed": true
}
```

Fail-closed rules:

- missing trust metadata fails closed
- missing freshness metadata fails closed
- missing refusal metadata fails closed when refusal is required
- forbidden request fields fail closed
- forbidden output fields fail closed
- stale or missing data may degrade or refuse depending on severity
- output that would imply ranking, selection, recommendation, or prediction
  must fail closed

Allowed fail-closed states:

- `not_failed_closed`
- `degraded_safe_output`
- `refused`
- `critical_failure`

## Example Successful Response

```json
{
  "capability": "team_operations_bullpen_readiness",
  "scope": "team_bullpen_readiness",
  "contract": "team_operations_bullpen_readiness_api_contract",
  "contract_version": "v3_phase_4",
  "contract_state": "available",
  "ranking_applied": false,
  "selection_made": false,
  "generated_at": "2026-06-03T12:00:00Z",
  "team": {
    "team_id": 111,
    "team_name": "Example Club",
    "team_abbreviation": "EX"
  },
  "readiness": {
    "status": "Operationally Stable",
    "status_code": "operationally_stable",
    "summary": "Team-level bullpen readiness is operationally stable from current public workload evidence.",
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness",
      "trust_metadata"
    ]
  },
  "constraints": [],
  "workload_pressure": {
    "pressure_state": "low",
    "pressure_state_code": "low",
    "low_count": 5,
    "moderate_count": 1,
    "elevated_count": 0,
    "unknown_count": 0,
    "latest_workload_date": "2026-06-03",
    "summary": "Recent workload pressure is low at the team level."
  },
  "availability_distribution": {
    "available": 4,
    "monitor": 1,
    "limited": 1,
    "avoid": 0,
    "unavailable": 0,
    "unknown": 0,
    "total": 6
  },
  "coverage_inventory": {
    "active_pitcher_count": 6,
    "current_workload_data_count": 6,
    "missing_workload_data_count": 0,
    "availability_covered_count": 6,
    "availability_missing_count": 0,
    "coverage_state": "covered"
  },
  "handedness_coverage": {
    "left_handed_count": 2,
    "right_handed_count": 4,
    "unknown_count": 0,
    "coverage_state": "covered",
    "limitations": []
  },
  "explanations": [
    {
      "explanation_id": "readiness_operationally_stable",
      "level": "readiness",
      "message": "Readiness is operationally stable because freshness is current and workload pressure is low.",
      "evidence": [
        "freshness_state: current",
        "pressure_state: low"
      ],
      "applies_to": "readiness"
    }
  ],
  "limitations": [
    {
      "limitation_id": "public_workload_data_only",
      "message": "Readiness is based on public workload data tracked by BaseballOS.",
      "severity": "informational",
      "applies_to": "readiness"
    }
  ],
  "trust_metadata": {
    "scope": "team_bullpen_readiness",
    "capability": "team_operations_bullpen_readiness",
    "confidence": "high",
    "confidence_reasons": [
      "fresh_data",
      "complete_metadata"
    ],
    "data_state": "fresh",
    "source_evidence_state": "represented",
    "governance_state": "compliant",
    "generated_at": "2026-06-03T12:00:00Z",
    "limitations": [],
    "explanations": [],
    "refusal_reasons": [],
    "trust_validation_errors": [],
    "ranking_applied": false,
    "selection_made": false
  },
  "freshness": {
    "freshness_state": "current",
    "data_through": "2026-06-03",
    "latest_workload_date": "2026-06-03",
    "last_successful_sync": "2026-06-03T11:30:00Z",
    "latest_sync_status": "success",
    "latest_fatigue_calculated_at": "2026-06-03T11:45:00Z",
    "generated_at": "2026-06-03T12:00:00Z",
    "stale_warning": null,
    "missing_data_warning": null,
    "limitations": []
  },
  "refusal": {
    "refused": false,
    "refusal_id": null,
    "reason": null,
    "message": null,
    "applies_to": null,
    "recovery_note": null
  },
  "fail_closed": {
    "failed_closed": false,
    "state": "not_failed_closed",
    "reason_codes": [],
    "critical_failure": false,
    "safe_partial_output_allowed": true
  }
}
```

## Example Degraded Response

```json
{
  "capability": "team_operations_bullpen_readiness",
  "scope": "team_bullpen_readiness",
  "contract": "team_operations_bullpen_readiness_api_contract",
  "contract_version": "v3_phase_4",
  "contract_state": "degraded",
  "ranking_applied": false,
  "selection_made": false,
  "generated_at": "2026-06-03T12:00:00Z",
  "team": {
    "team_id": 111,
    "team_name": "Example Club",
    "team_abbreviation": "EX"
  },
  "readiness": {
    "status": "Data Limited",
    "status_code": "data_limited",
    "summary": "Team-level readiness is data limited because current workload evidence is incomplete.",
    "basis": [
      "freshness",
      "coverage_inventory",
      "trust_metadata"
    ]
  },
  "constraints": [
    {
      "constraint_id": "coverage_partial",
      "category": "coverage",
      "severity": "caution",
      "affected_area": "coverage_inventory",
      "count": 2,
      "message": "Two pitcher records are missing current workload data.",
      "evidence": [
        "missing_workload_data_count: 2"
      ]
    }
  ],
  "workload_pressure": {
    "pressure_state": "unknown",
    "pressure_state_code": "unknown",
    "low_count": 3,
    "moderate_count": 1,
    "elevated_count": 0,
    "unknown_count": 2,
    "latest_workload_date": "2026-06-02",
    "summary": "Recent workload pressure is partially unknown because some current workload evidence is missing."
  },
  "availability_distribution": {
    "available": 3,
    "monitor": 1,
    "limited": 0,
    "avoid": 0,
    "unavailable": 0,
    "unknown": 2,
    "total": 6
  },
  "coverage_inventory": {
    "active_pitcher_count": 6,
    "current_workload_data_count": 4,
    "missing_workload_data_count": 2,
    "availability_covered_count": 4,
    "availability_missing_count": 2,
    "coverage_state": "partial"
  },
  "handedness_coverage": {
    "left_handed_count": 1,
    "right_handed_count": 4,
    "unknown_count": 1,
    "coverage_state": "partial",
    "limitations": [
      "One active pitcher is missing throwing-hand data."
    ]
  },
  "explanations": [
    {
      "explanation_id": "readiness_data_limited",
      "level": "readiness",
      "message": "Readiness is data limited because workload and handedness coverage are partial.",
      "evidence": [
        "missing_workload_data_count: 2",
        "handedness_unknown_count: 1"
      ],
      "applies_to": "readiness"
    }
  ],
  "limitations": [
    {
      "limitation_id": "partial_workload_coverage",
      "message": "Some active pitcher records do not have current workload evidence.",
      "severity": "caution",
      "applies_to": "coverage_inventory"
    }
  ],
  "trust_metadata": {
    "scope": "team_bullpen_readiness",
    "capability": "team_operations_bullpen_readiness",
    "confidence": "low",
    "confidence_reasons": [
      "partial_coverage"
    ],
    "data_state": "incomplete",
    "source_evidence_state": "represented",
    "governance_state": "compliant",
    "generated_at": "2026-06-03T12:00:00Z",
    "limitations": [
      "partial_workload_coverage"
    ],
    "explanations": [
      "readiness_data_limited"
    ],
    "refusal_reasons": [],
    "trust_validation_errors": [],
    "ranking_applied": false,
    "selection_made": false
  },
  "freshness": {
    "freshness_state": "incomplete",
    "data_through": "2026-06-02",
    "latest_workload_date": "2026-06-02",
    "last_successful_sync": "2026-06-03T11:30:00Z",
    "latest_sync_status": "success",
    "latest_fatigue_calculated_at": "2026-06-03T11:45:00Z",
    "generated_at": "2026-06-03T12:00:00Z",
    "stale_warning": null,
    "missing_data_warning": "Some current workload evidence is missing.",
    "limitations": [
      "partial_workload_coverage"
    ]
  },
  "refusal": {
    "refused": false,
    "refusal_id": null,
    "reason": null,
    "message": null,
    "applies_to": null,
    "recovery_note": null
  },
  "fail_closed": {
    "failed_closed": false,
    "state": "degraded_safe_output",
    "reason_codes": [
      "partial_coverage"
    ],
    "critical_failure": false,
    "safe_partial_output_allowed": true
  }
}
```

## Example Refusal Response

```json
{
  "capability": "team_operations_bullpen_readiness",
  "scope": "team_bullpen_readiness",
  "contract": "team_operations_bullpen_readiness_api_contract",
  "contract_version": "v3_phase_4",
  "contract_state": "refused",
  "ranking_applied": false,
  "selection_made": false,
  "generated_at": "2026-06-03T12:00:00Z",
  "team": null,
  "readiness": {
    "status": "Refused",
    "status_code": "refused",
    "summary": "Readiness output is refused because required trust metadata is missing.",
    "basis": [
      "trust_metadata",
      "fail_closed"
    ]
  },
  "constraints": [
    {
      "constraint_id": "trust_metadata_missing",
      "category": "trust",
      "severity": "blocking",
      "affected_area": "readiness",
      "count": 1,
      "message": "Required trust metadata is missing.",
      "evidence": []
    }
  ],
  "workload_pressure": null,
  "availability_distribution": null,
  "coverage_inventory": null,
  "handedness_coverage": null,
  "explanations": [
    {
      "explanation_id": "readiness_refused_missing_trust_metadata",
      "level": "refusal",
      "message": "Readiness output failed closed before summary assembly.",
      "evidence": [
        "trust_metadata_missing"
      ],
      "applies_to": "refusal"
    }
  ],
  "limitations": [
    {
      "limitation_id": "readiness_refused",
      "message": "Readiness output is withheld until required metadata is available.",
      "severity": "blocking",
      "applies_to": "readiness"
    }
  ],
  "trust_metadata": {
    "scope": "team_bullpen_readiness",
    "capability": "team_operations_bullpen_readiness",
    "confidence": "unknown",
    "confidence_reasons": [
      "missing_trust_metadata"
    ],
    "data_state": "unknown",
    "source_evidence_state": "missing",
    "governance_state": "refused",
    "generated_at": "2026-06-03T12:00:00Z",
    "limitations": [
      "readiness_refused"
    ],
    "explanations": [
      "readiness_refused_missing_trust_metadata"
    ],
    "refusal_reasons": [
      "trust_metadata_missing"
    ],
    "trust_validation_errors": [
      "missing_trust_metadata"
    ],
    "ranking_applied": false,
    "selection_made": false
  },
  "freshness": {
    "freshness_state": "unknown",
    "data_through": null,
    "latest_workload_date": null,
    "last_successful_sync": null,
    "latest_sync_status": null,
    "latest_fatigue_calculated_at": null,
    "generated_at": "2026-06-03T12:00:00Z",
    "stale_warning": null,
    "missing_data_warning": "Required metadata is missing.",
    "limitations": [
      "readiness_refused"
    ]
  },
  "refusal": {
    "refused": true,
    "refusal_id": "missing_trust_metadata",
    "reason": "trust_metadata_missing",
    "message": "Readiness output is refused because required trust metadata is missing.",
    "applies_to": "readiness",
    "recovery_note": "Refresh evidence and rerun certification checks before exposing readiness."
  },
  "fail_closed": {
    "failed_closed": true,
    "state": "critical_failure",
    "reason_codes": [
      "trust_metadata_missing"
    ],
    "critical_failure": true,
    "safe_partial_output_allowed": false
  }
}
```

## Backend Certification Requirements

Backend certification must prove:

- endpoint contract shape is stable
- route is separate from certified Recommendation Engine V2
- request parsing rejects forbidden fields
- response serialization includes required top-level fields
- readiness status uses only allowed vocabulary
- constraints use only allowed categories and severities
- trust metadata is present in every response
- freshness metadata is present in every response
- refusal metadata is present when refusal occurs
- fail-closed behavior works for missing, stale, malformed, incomplete, and
  governance-unsafe evidence
- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best/preferred/recommended behavior exists

## Frontend Certification Requirements

Frontend certification must prove:

- the client calls only the approved Team Operations readiness route
- available, degraded, refused, and unavailable states normalize safely
- summary-first rendering is used
- trust metadata is visible
- freshness metadata is visible
- explanations are visible or available on demand
- limitations are visible or available on demand
- refusal metadata is visible when present
- no visual treatment implies a selected pitcher
- no leaderboard, numbered choice, winner, or quality-sorted layout appears
- certified V1 and V2 frontend behavior remains unchanged

## Accessibility Certification Requirements

Accessibility certification must prove:

- keyboard support for detail expansion
- screen-reader support for readiness state, trust metadata, freshness
  metadata, limitations, explanations, refusal, and fail-closed status
- mobile support at 320 px, 375 px, 390 px, and 768 px
- color is not the only signal for readiness, degradation, refusal, or
  fail-closed state
- focus order remains stable
- loading, refused, unavailable, and fail-closed states use appropriate status
  or alert semantics

## Governance Certification Requirements

Governance certification must prove:

```text
ranking_applied === false
selection_made === false
```

It must also prove:

- no pitcher ranking behavior
- no pitcher recommendation behavior
- no pitcher selection behavior
- no best/preferred/recommended behavior
- no hidden priority ordering
- no matchup advice
- no outcome prediction
- no injury prediction
- no save prediction
- no performance prediction
- all outputs remain team-level or context-level
- the contract does not create a hidden recommendation engine

## Testing Certification Requirements

Testing certification must include:

- backend route contract tests
- backend domain serialization tests
- backend forbidden request field tests
- backend forbidden response field tests
- backend trust metadata tests
- backend freshness metadata tests
- backend refusal metadata tests
- backend fail-closed tests
- backend degraded response tests
- frontend client normalization tests
- frontend available/degraded/refused/unavailable rendering tests
- frontend prohibited-language tests
- frontend accessibility tests
- V1 regression tests
- V2 regression tests

Certification must record exact test files, test names, and assertion groups
in the lifecycle evidence packet.

## Rollout Certification Requirements

Rollout certification must prove:

- backend certification completed
- frontend certification completed
- accessibility certification completed
- governance certification completed
- testing certification completed
- lifecycle evidence packet updated
- monitoring artifact expectations defined
- owner and retention cadence recorded
- production rollout decision completed
- post-rollout monitoring and boundary review scheduled

Production exposure is not allowed until rollout certification is complete.

## Risks And Mitigations

| Risk | Mitigation |
|------|------------|
| Route is mistaken for Recommendation Engine expansion | Use `/api/team-operations/bullpen-readiness` and preserve the certified V2 route unchanged. |
| Readiness status becomes pitcher guidance | Keep all output team-level/context-level and require explicit limitation text. |
| Frontend creates hidden ordering through layout | Prohibit leaderboard, winner, first-choice, and quality-sorted presentations. |
| Missing metadata produces unsafe output | Require fail-closed behavior for missing trust, freshness, or refusal metadata. |
| Degraded output appears complete | Require `contract_state: degraded`, visible constraints, limitations, and freshness warnings. |
| Handedness coverage becomes matchup advice | Limit handedness output to counts and limitations only. |
| Tests focus only on success states | Certification requires forbidden-field, degraded, refused, fail-closed, and accessibility tests. |

## Validation

Validation required for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-4-contract
Result: 278 passed, 0 failed.

cd frontend
npm test
Result: 78 passed, 0 failed.

git diff --check
Result: Passed; reported only LF-to-CRLF warnings, including known unrelated
frontend generated/dependency drift.

git diff --cached --check
Result: Passed after targeted documentation staging.
```

Root `npm test` is not required for V3 Phase 4. If no root `package.json`
exists, that is expected and is not a project failure.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 5 Team Operations Bullpen Readiness Backend Domain Foundation
```

The next milestone should remain bounded to implementation only if explicitly
authorized. It should implement backend domain objects and serialization tests
for this contract before exposing any API route or frontend behavior.
