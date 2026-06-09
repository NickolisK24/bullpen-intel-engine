# BaseballOS V4 Phase 2 - Evidence And Explanation Architecture And Contract Planning

## Phase Status

Phase status:

```text
V4_PHASE_2_EVIDENCE_AND_EXPLANATION_ARCHITECTURE_AND_CONTRACT_PLANNING_COMPLETE
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
READY_FOR_V4_PHASE_3_IMPLEMENTATION_PLANNING
```

This phase defines the technical architecture and contract plan for V4 before
implementation begins. It does not authorize backend implementation, frontend
implementation, database migration, runtime behavior change, or API route
creation.

## 1. Architecture Overview

V4 should be implemented as a deterministic explanation layer over existing
governed BaseballOS states.

The intended architecture is:

```text
Existing governed inputs
  -> explanation assembly layer
  -> explanation objects
  -> evidence items
  -> governed presentation surfaces
```

Explanation logic should live in a dedicated V4 explanation domain when
implementation is authorized. The explanation layer should consume already
available state, metadata, reasons, limitations, freshness, trust, refusal, and
fail-closed inputs from existing systems rather than recalculating their core
decisions.

Relationship to existing systems:

| Existing system | V4 relationship |
| --- | --- |
| Availability Engine V1 | V4 explains existing availability state, reasons, confidence, data state, and limitations. |
| Recommendation Engine V1 | V4 may explain one-candidate certified V1 evidence only when preserving candidate-only scope. |
| Recommendation Engine V2 | V4 explains governed bullpen-state context, trust, freshness, refusal, and fail-closed contributors without ranking or selection. |
| Team Operations Bullpen Readiness V3 | V4 explains readiness status, workload pressure, constraints, coverage, and limitations at team or context level. |
| Dashboard trust/freshness surfaces | V4 explains the meaning and source of visible freshness, trust, and refusal metadata. |

What should remain shared or reusable:

- existing availability statuses
- existing readiness statuses
- existing trust metadata
- existing freshness metadata
- existing refusal metadata
- existing fail-closed metadata
- existing reason and limitation text where already stable
- existing governance metadata
- existing source timestamps and data-through fields

What should remain isolated:

- explanation assembly logic
- V4 explanation object construction
- V4 evidence item normalization
- V4 reason code mapping
- V4 certification checks
- future V4 API contract behavior if separately authorized
- future V4 frontend presentation behavior if separately authorized

V4 must not move decision logic out of the existing engines. It should explain
the state that those engines already produced. It should not recalculate
availability, readiness, candidate eligibility, bullpen context, or freshness
criteria in a way that changes product behavior.

Determinism and auditability requirements:

- identical inputs must produce identical explanation objects
- explanation objects must reference stable reason codes
- evidence items must identify source, trust, freshness, and limitation state
- explanation summaries must be derived from reason codes and evidence items
- unsafe or missing evidence must degrade or fail closed visibly
- governance metadata must be carried with every explanation
- certification must be able to trace each explanation to source evidence

## 2. Explanation Scope Model

V4 should support explicit scopes. Scope names should be stable, lower-case,
and safe for backend tests, frontend rendering, and certification review.

Allowed scopes:

```text
availability_state
workload_state
readiness_state
risk_distribution
freshness_state
trust_state
coverage_state
```

### availability_state

Explains:

- why an availability status exists
- which workload, rest, recent-use, data-state, and limitation contributors
  are relevant

May reference:

- availability status
- confidence
- fatigue score
- rest days
- recent appearance count
- recent pitch count
- innings load
- data state
- source freshness
- availability limitations

Allowed outputs:

- explanation summary
- primary workload reasons
- supporting rest or recent-use evidence
- confidence and limitation notes

Prohibited outputs:

- use-this-pitcher instruction
- avoid-this-pitcher instruction
- pitcher ranking
- pitcher selection
- performance prediction

### workload_state

Explains:

- why workload is elevated, moderate, low, stale, or incomplete
- which workload contributors affected the displayed state

May reference:

- fatigue score
- recent workload windows
- pitch-count load
- appearance frequency
- innings load
- rest recovery
- source freshness

Allowed outputs:

- workload contributor list
- reason code list
- evidence item list
- limitation list

Prohibited outputs:

- projected fatigue
- injury prediction
- rest prescription
- pitcher-level advice
- hidden priority ordering

### readiness_state

Explains:

- why Team Operations Bullpen Readiness is healthy, constrained, degraded, or
  refused
- what team-level factors contributed to the current readiness context

May reference:

- readiness status
- workload pressure
- constraints
- availability distribution
- coverage inventory
- handedness coverage
- freshness metadata
- trust metadata
- refusal and fail-closed metadata

Allowed outputs:

- team-level explanation summary
- readiness contributor list
- limitations
- trust and freshness notes
- refusal or fail-closed reason summary

Prohibited outputs:

- pitcher recommendation
- pitcher selection
- pitcher ranking
- matchup advice
- best/preferred arm language
- decision instruction

### risk_distribution

Explains:

- what evidence contributes to a displayed risk, availability, or readiness
  distribution
- why a distribution contains specific categories or counts

May reference:

- category counts
- availability statuses
- freshness state
- trust state
- known limitations
- safe aggregate metadata

Allowed outputs:

- category evidence summary
- count-level context
- limitation summary
- freshness and trust context

Prohibited outputs:

- quality-based ordering of pitchers
- ranking by risk
- selection of safer or better pitchers
- prediction of future outcomes

### freshness_state

Explains:

- why freshness is current, stale, missing, degraded, or refused
- which source timestamps and data-through values affect the output

May reference:

- sync status
- last sync attempt
- last successful sync
- data-through date
- workload data date
- source freshness status
- freshness failure state

Allowed outputs:

- freshness explanation summary
- stale or missing source notes
- data-through explanation
- fail-closed reason where applicable

Prohibited outputs:

- substituting sync time for baseball data coverage
- hiding stale source state
- treating missing freshness as safe current evidence

### trust_state

Explains:

- why trust is satisfied, limited, failed, or unknown
- what trust metadata affects the output

May reference:

- trust status
- source availability
- contract identity
- certified surface status
- refusal state
- fail-closed state
- limitations

Allowed outputs:

- trust explanation summary
- trust limitation list
- contract or source notes
- safe degradation notes

Prohibited outputs:

- using trust language to override missing evidence
- hiding trust failures
- issuing advice when trust is limited

### coverage_state

Explains:

- what coverage is present, partial, missing, or limited
- how role, handedness, inventory, or team-level coverage evidence affects the
  current context

May reference:

- coverage inventory
- handedness counts where available
- role/coverage inventory where available
- availability distribution
- source freshness
- limitations

Allowed outputs:

- coverage explanation summary
- neutral count or distribution evidence
- limitations
- freshness and trust notes

Prohibited outputs:

- choosing a pitcher from coverage evidence
- matchup guidance
- quality-based ordering
- hidden priority output

## 3. Explanation Object Shape

V4 should define a stable internal explanation object shape before
implementation. This phase does not implement the model.

Proposed object:

```json
{
  "explanation_id": "availability_state:player:12345:current",
  "scope": "availability_state",
  "subject_type": "player",
  "subject_id": "12345",
  "state_explained": "Monitor",
  "summary": "Availability is Monitor because recent workload is elevated and rest recovery is incomplete.",
  "primary_reasons": [
    {
      "code": "AVAILABILITY_MONITOR_THRESHOLD_MET",
      "label": "Monitor threshold met",
      "summary": "Recent workload evidence supports Monitor rather than Available."
    }
  ],
  "supporting_evidence": [
    {
      "evidence_id": "recent_pitch_count_3d",
      "evidence_type": "workload_metric",
      "label": "Recent pitch count",
      "value": 42,
      "unit": "pitches",
      "source": "mlb_stats_api_game_logs",
      "freshness": {
        "status": "current",
        "data_through": "2026-06-03"
      },
      "trust_status": "trusted",
      "impact": "supports_monitor",
      "limitation": null
    }
  ],
  "limitations": [
    {
      "limitation_type": "insufficient_context",
      "summary": "Public data does not include warm-up activity or manager intent."
    }
  ],
  "freshness": {
    "status": "current",
    "data_through": "2026-06-03"
  },
  "trust": {
    "status": "trusted",
    "source": "certified_baseballos_surface"
  },
  "confidence": {
    "level": "medium",
    "summary": "Confidence is limited to public workload evidence."
  },
  "governance": {
    "ranking_applied": false,
    "selection_made": false,
    "recommendation_made": false,
    "prediction_made": false,
    "decision_scope": "explanation_only",
    "advice_scope": "none"
  },
  "generated_at": "2026-06-04T00:00:00Z"
}
```

Required field principles:

- `explanation_id` should be deterministic and traceable.
- `scope` must be one of the allowed scope values.
- `subject_type` should be explicit, such as `player`, `team`, `surface`, or
  `distribution`.
- `subject_id` should identify the explained subject without implying ranking.
- `state_explained` should reflect an existing governed state.
- `summary` must be explanatory and non-advisory.
- `primary_reasons` must use stable reason codes.
- `supporting_evidence` must use evidence item objects.
- `limitations` must be visible when confidence or scope is constrained.
- `freshness` and `trust` must preserve source metadata.
- `governance` must preserve all mandatory invariants.

## 4. Evidence Item Shape

V4 should use reusable evidence items so explanations can be audited and
certified.

Proposed evidence item:

```json
{
  "evidence_id": "workload_recent_usage_3d",
  "evidence_type": "workload_metric",
  "label": "Recent usage",
  "value": 42,
  "unit": "pitches",
  "source": "mlb_stats_api_game_logs",
  "freshness": {
    "status": "current",
    "data_through": "2026-06-03"
  },
  "trust_status": "trusted",
  "impact": "supports_elevated_workload",
  "limitation": null
}
```

Evidence item fields:

| Field | Purpose |
| --- | --- |
| `evidence_id` | Stable identifier for traceability and testing. |
| `evidence_type` | Category such as workload metric, freshness metadata, trust metadata, coverage count, refusal metadata, or limitation. |
| `label` | Human-readable display label. |
| `value` | The relevant value, count, state, or summary. |
| `unit` | Unit when applicable, such as pitches, days, appearances, count, or status. |
| `source` | Source system or governed surface. |
| `freshness` | Source freshness metadata. |
| `trust_status` | Trust state for the evidence. |
| `impact` | Neutral explanation impact. |
| `limitation` | Any limitation attached to the evidence item. |

Allowed evidence patterns:

- neutral workload metric evidence
- neutral freshness metadata
- neutral trust metadata
- neutral availability status evidence
- neutral readiness status evidence
- neutral coverage count evidence
- visible limitation evidence
- visible refusal or fail-closed evidence

Prohibited evidence patterns:

- quality score used to order pitchers
- hidden priority value
- best/preferred flag
- matchup advantage score
- predicted performance value
- injury likelihood value
- decision instruction
- private medical or clubhouse claim
- evidence without source or trust metadata
- freshness-unsafe evidence treated as current

Evidence must support explanation, not advice.

## 5. Reason Code Model

V4 should use stable, testable, human-readable reason codes. Reason codes
should map to safe display labels and should be reviewed during certification.

Reason code strategy:

- codes are uppercase snake case
- codes are stable across releases unless a migration is documented
- codes are grouped by explanation scope
- codes are safe for logs, tests, docs, and frontend display mapping
- codes do not contain pitcher names
- codes do not imply ranking, selection, recommendation, or prediction
- labels are separate from codes so copy can be improved without breaking tests

Candidate reason codes:

| Code | Scope | Meaning |
| --- | --- | --- |
| `WORKLOAD_RECENT_USAGE_ELEVATED` | `workload_state` | Recent usage contributes to elevated workload. |
| `WORKLOAD_REST_RECOVERY_LIMITED` | `workload_state` | Rest recovery is limited by recent workload. |
| `FRESHNESS_STALE_SOURCE` | `freshness_state` | Source freshness is stale. |
| `FRESHNESS_MISSING_SOURCE` | `freshness_state` | Required freshness metadata is unavailable. |
| `COVERAGE_PARTIAL` | `coverage_state` | Coverage evidence is partial. |
| `COVERAGE_HANDEDNESS_LIMITED` | `coverage_state` | Handedness coverage evidence is limited. |
| `TRUST_LIMITED` | `trust_state` | Trust metadata indicates limited confidence. |
| `TRUST_METADATA_MISSING` | `trust_state` | Trust metadata is missing or unsafe. |
| `AVAILABILITY_MONITOR_THRESHOLD_MET` | `availability_state` | Availability state is Monitor due to governed threshold evidence. |
| `AVAILABILITY_LIMITED_THRESHOLD_MET` | `availability_state` | Availability state is Limited due to governed threshold evidence. |
| `READINESS_DEGRADED_BY_LIMITATIONS` | `readiness_state` | Readiness is degraded by limitations. |
| `READINESS_REFUSED_BY_FAIL_CLOSED` | `readiness_state` | Readiness explanation is refused because fail-closed conditions apply. |
| `RISK_DISTRIBUTION_REFLECTS_COUNTS` | `risk_distribution` | Distribution reflects neutral category counts. |

Certification expectations:

- every reason code has a documented label
- every reason code maps to one or more allowed scopes
- every reason code has test coverage once implemented
- reason codes are not used to encode hidden priority
- reason code labels remain neutral and non-advisory

## 6. Limitation Model

V4 limitations should make explanation more trustworthy. Limitations are not
excuses, hidden overrides, or decision modifiers.

Allowed limitation types:

```text
missing_data
stale_data
partial_coverage
uncertified_source
limited_confidence
insufficient_context
refusal_active
fail_closed_active
public_data_only
metadata_unavailable
```

Proposed limitation object:

```json
{
  "limitation_type": "stale_data",
  "severity": "degrades_confidence",
  "summary": "Source freshness is stale, so the explanation is limited.",
  "affected_scopes": ["readiness_state", "freshness_state"],
  "requires_refusal": false
}
```

Limitation model rules:

- limitations must be visible when present
- limitations must be attached to affected scopes
- limitations must not hide unsafe evidence
- limitations must not override fail-closed behavior
- limitations must not turn explanation into advice
- limitations should reduce confidence or trigger refusal when required
- limitations should reference source, freshness, or trust context where
  possible

Examples:

| Limitation | Meaning |
| --- | --- |
| `missing_data` | Required source data or metadata is unavailable. |
| `stale_data` | Source data is not current enough for normal confidence. |
| `partial_coverage` | Coverage evidence is incomplete. |
| `uncertified_source` | A source is visible but not certified for this explanation. |
| `limited_confidence` | Explanation is useful but not complete enough for high confidence. |
| `insufficient_context` | BaseballOS lacks private or external context needed for deeper claims. |

## 7. Governance Contract

Every V4 explanation should carry governance metadata.

Required governance fields:

```json
{
  "ranking_applied": false,
  "selection_made": false,
  "recommendation_made": false,
  "prediction_made": false,
  "decision_scope": "explanation_only",
  "advice_scope": "none"
}
```

Required values:

| Field | Required value | Reason |
| --- | --- | --- |
| `ranking_applied` | `false` | V4 cannot rank pitchers, teams, or choices. |
| `selection_made` | `false` | V4 cannot select a pitcher or decision. |
| `recommendation_made` | `false` | V4 cannot recommend an action. |
| `prediction_made` | `false` | V4 cannot predict outcomes, injuries, saves, or performance. |
| `decision_scope` | `explanation_only` | V4 explains existing state only. |
| `advice_scope` | `none` | V4 must not provide pitcher-level or matchup advice. |

Mandatory platform invariants:

```text
ranking_applied === false
selection_made === false
```

V4 must also preserve:

- no ranking behavior
- no selection behavior
- no prediction behavior
- no recommendation behavior
- no best/preferred arm behavior
- no hidden priority ordering
- no pitcher-level advice
- no matchup advice
- no decision automation

If governance metadata is missing, malformed, or unsafe, V4 implementation
should degrade or refuse the explanation rather than silently treating the
payload as valid.

## 8. API Contract Candidates

This phase does not create APIs. The routes below are contract candidates only.

Candidate API principles:

- routes should be versioned or clearly scoped when implemented
- responses must carry explanation, evidence, limitation, freshness, trust, and
  governance metadata
- unsafe query intent must be refused
- API output must be deterministic for identical inputs
- no route may become a hidden recommendation engine

### GET /api/explanations/availability/:pitcher_id

Purpose:

- explain an existing availability state for a single pitcher

Expected response shape:

```json
{
  "contract": "baseballos.v4.explanation.availability_state",
  "explanation": {},
  "governance": {},
  "metadata": {
    "surface_status": "planned",
    "certification_status": "not_implemented"
  }
}
```

Governance requirements:

- one subject only
- no bullpen ranking
- no selection
- no recommendation
- no matchup guidance

Reasons to delay implementation:

- V4 domain object and reason code model should be finalized first
- availability explanation tests should be planned before route exposure
- frontend presentation language should be reviewed before public display

### GET /api/explanations/readiness/team

Purpose:

- explain the team-level Team Operations Bullpen Readiness state

Expected response shape:

```json
{
  "contract": "baseballos.v4.explanation.readiness_state",
  "explanation": {},
  "governance": {},
  "metadata": {
    "surface_status": "planned",
    "certification_status": "not_implemented"
  }
}
```

Governance requirements:

- team-level or context-level only
- no pitcher selection
- no best/preferred arm language
- no hidden priority ordering
- no matchup advice

Reasons to delay implementation:

- V3 controlled rollout observation should continue independently
- explanation architecture should avoid changing V3 readiness behavior
- certification must prove V3 regressions do not occur

### GET /api/explanations/risk-distribution

Purpose:

- explain a neutral category distribution already shown by BaseballOS

Expected response shape:

```json
{
  "contract": "baseballos.v4.explanation.risk_distribution",
  "explanation": {},
  "governance": {},
  "metadata": {
    "surface_status": "planned",
    "certification_status": "not_implemented"
  }
}
```

Governance requirements:

- counts and categories only
- no quality-based ordering
- no selection guidance
- no prediction

Reasons to delay implementation:

- risk distribution explanation needs clear scope naming before certification
- frontend language must avoid implying risk ranking
- evidence attribution rules must be stable before API exposure

### Existing-payload extension candidate

Purpose:

- add explanation objects to existing governed payloads instead of creating
  separate explanation routes

Expected response shape:

```json
{
  "existing_payload": {},
  "explanations": {
    "availability_state": {},
    "freshness_state": {}
  }
}
```

Governance requirements:

- must not change existing contract behavior unexpectedly
- explanations must remain optional until certified
- fail-closed behavior must remain unchanged

Reasons to delay implementation:

- extension could affect existing certified payload contracts
- a separate planning review should decide whether extension or dedicated
  routes are safer
- rollout strategy differs for additive payloads versus new routes

## 9. Frontend Surface Candidates

This phase does not implement frontend UI.

Candidate frontend surfaces:

| Surface | Purpose | Governance constraint |
| --- | --- | --- |
| Explanation drawer | Show why a state exists without taking over the Dashboard. | Must use neutral labels and preserve metadata visibility. |
| Evidence panel | List supporting evidence items and limitations. | Must not order evidence as pitcher priority. |
| Why this state? button | Open contextual explanation on demand. | Must be keyboard accessible and avoid advice language. |
| Readiness detail view | Explain team-level readiness context. | Must remain team-level or context-level only. |
| Availability explanation modal | Explain one availability state. | Must not instruct use or avoidance. |
| Risk distribution explanation panel | Explain category counts and data limits. | Must not rank categories or pitchers. |

Frontend planning requirements:

- summary-first display
- expand-on-demand evidence
- visible limitations
- visible freshness metadata
- visible trust metadata
- visible governance metadata
- accessible disclosure controls
- mobile-safe layout
- neutral labels
- no best/preferred/recommended language
- no pitcher-level advice
- no matchup advice

Potential UI labels:

- `Why this state?`
- `Evidence`
- `Limitations`
- `Freshness`
- `Trust`
- `Governance`

Labels to avoid:

- `Best option`
- `Preferred arm`
- `Recommended pitcher`
- `Use this pitcher`
- `Pick`
- `Start here`
- `Highest priority`

## 10. Certification Requirements

V4 implementation must prove:

- explanations are deterministic
- evidence attribution is accurate
- explanation attribution is accurate
- reason codes are stable
- reason code labels are safe for display
- limitations are visible
- freshness metadata is visible where applicable
- trust metadata is visible where applicable
- refusal metadata is visible where applicable
- fail-closed metadata is visible where applicable
- governance fields are present
- `ranking_applied === false`
- `selection_made === false`
- `recommendation_made === false`
- `prediction_made === false`
- no recommendation behavior exists
- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best/preferred arm behavior exists
- no hidden priority ordering exists
- no pitcher-level advice exists
- no matchup advice exists
- no decision automation exists
- V1 candidate-level boundaries remain intact
- V2 bullpen-state behavior remains unchanged
- V3 Team Operations Bullpen Readiness behavior remains unchanged

Required future test categories:

- reason code stability tests
- explanation object shape tests
- evidence item shape tests
- limitation visibility tests
- governance metadata tests
- missing freshness degradation/refusal tests
- missing trust degradation/refusal tests
- unsafe query intent refusal tests if APIs are implemented
- frontend prohibited-language tests if UI is implemented
- V1, V2, and V3 regression tests

Required future retained evidence:

- V4 implementation plan
- V4 API contract if routes are proposed
- V4 frontend contract if UI is proposed
- V4 certification requirements
- V4 certification-readiness review
- V4 formal certification review
- rollout or observation artifact if exposed in controlled rollout

## 11. Implementation Readiness Decision

Decision:

```text
READY_FOR_V4_PHASE_3_IMPLEMENTATION_PLANNING
```

Rationale:

- V4 Phase 1 defined the capability as explanation-only.
- Phase 2 defines a deterministic explanation architecture.
- Phase 2 defines allowed explanation scopes.
- Phase 2 defines proposed explanation object and evidence item shapes.
- Phase 2 defines reason code and limitation models.
- Phase 2 defines a governance contract that preserves current invariants.
- Phase 2 identifies API candidates without creating API routes.
- Phase 2 identifies frontend candidates without implementing UI.
- Phase 2 defines certification requirements before implementation planning.

This decision authorizes planning for V4 Phase 3 only. It does not authorize
runtime implementation.

Recommended next milestone:

```text
V4 Phase 3 - Evidence And Explanation Implementation Plan
```

V4 Phase 3 should convert this architecture and contract plan into a concrete
implementation plan. It should identify files or modules to create, tests to
write, certification gates, rollout gates, and implementation sequence while
preserving all governance boundaries.

## Final Boundary

This document authorizes architecture and contract planning only.

It does not authorize:

- backend implementation
- frontend implementation
- database migration
- runtime behavior changes
- API route creation
- API contract exposure
- fatigue calculation changes
- availability calculation changes
- recommendation behavior changes
- readiness calculation changes
- trust logic changes
- freshness logic changes
- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred arm behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation
