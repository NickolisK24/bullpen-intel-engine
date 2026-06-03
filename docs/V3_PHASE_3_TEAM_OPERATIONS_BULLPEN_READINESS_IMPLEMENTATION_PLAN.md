# BaseballOS V3 Phase 3 - Team Operations Bullpen Readiness Implementation Plan

## Decision

Status:

```text
V3_PHASE_3_TEAM_OPERATIONS_BULLPEN_READINESS_IMPLEMENTATION_PLAN_COMPLETE
```

Capability planned:

```text
TEAM_OPERATIONS_BULLPEN_READINESS
```

Recommended next milestone:

```text
BaseballOS V3 Phase 4 Team Operations Bullpen Readiness API Contract And Certification Requirements
```

V3 Phase 3 converts the V3 Phase 2 capability definition into an implementation
plan. This phase is planning and documentation only. It does not implement
runtime behavior, change API contracts, change frontend behavior, or authorize
production rollout.

## Phase Purpose

The purpose of V3 Phase 3 is to define how Team Operations Bullpen Readiness
should be implemented if a future implementation phase is explicitly approved.

This plan translates the Phase 2 capability definition into:

- backend architecture
- domain module structure
- API endpoint strategy
- response contract shape
- readiness status calculation boundaries
- constraint and workload summary approach
- coverage and handedness inventory approach
- trust, freshness, refusal, and fail-closed metadata requirements
- frontend presentation approach
- accessibility approach
- testing strategy
- certification strategy
- rollout strategy

This is the bridge between capability definition and implementation. It is not
the implementation itself.

## Scope

In scope:

- implementation goals
- non-goals
- proposed backend architecture
- proposed domain module structure
- proposed API endpoint plan
- proposed response contract
- allowed and prohibited input data
- readiness status calculation plan
- constraint detection plan
- workload pressure summary plan
- coverage inventory plan
- handedness coverage plan
- availability distribution plan
- trust metadata plan
- freshness metadata plan
- refusal and fail-closed plan
- explainability plan
- frontend integration plan
- dashboard presentation plan
- accessibility plan
- test strategy
- certification strategy
- rollout strategy
- implementation sequence
- risks and mitigations
- recommended next milestone

Out of scope:

- runtime behavior changes
- backend code changes
- frontend code changes
- API contract changes
- database schema changes
- fatigue formula changes
- recommendation logic changes
- Recommendation Engine V1 changes
- certified Recommendation Engine V2 behavior changes
- feature implementation
- lifecycle promotion
- production rollout
- pitcher ranking
- pitcher selection
- pitcher recommendation
- quality-based ordering
- best, preferred, or recommended labels
- prediction behavior
- matchup advice
- hidden priority outputs

## Relationship To V3 Phase 1 And Phase 2

V3 Phase 1 selected the next product direction:

```text
TEAM_OPERATIONS_BULLPEN_READINESS_PLANNING
```

That decision was based on current product evidence, data availability,
governance risk, implementation risk, maintainability, portfolio value, and
baseball operations value.

V3 Phase 2 defined what the capability may and may not say. It established:

- allowed inputs
- prohibited inputs
- allowed outputs
- prohibited outputs
- readiness vocabulary
- constraint vocabulary
- coverage vocabulary
- workload vocabulary
- trust metadata requirements
- freshness metadata requirements
- refusal metadata requirements
- fail-closed requirements
- explainability requirements
- testing expectations
- accessibility expectations
- certification gates

V3 Phase 3 uses those boundaries to define an implementation plan. It preserves
the Phase 2 capability definition without expanding the product scope.

## Implementation Goals

Future implementation should:

- create a governed team-level bullpen readiness layer
- summarize the operational state of a bullpen from current public workload,
  availability, roster, trust, and freshness evidence
- expose a single team-level readiness status
- show availability distribution by existing availability labels
- show workload pressure using counts and documented categories only
- show coverage inventory using neutral counts and public roster fields
- show handedness coverage as counts only
- expose trust metadata, freshness metadata, refusal metadata, and
  fail-closed state
- provide visible explanations and limitations
- preserve all certified V2 governance boundaries
- keep the user responsible for baseball decisions

Future implementation must make unsafe or unsupported output impossible to
display as complete readiness.

## Non-Goals

V3 Phase 3 does not authorize:

- implementation work
- backend runtime changes
- frontend runtime changes
- API route changes
- API contract changes
- database schema changes
- fatigue formula changes
- recommendation logic changes
- Recommendation Engine V1 changes
- Recommendation Engine V2 behavior changes
- production rollout
- pitcher ranking
- pitcher ordering by quality
- pitcher selection
- pitcher recommendation
- matchup advice
- game outcome prediction
- injury prediction
- save prediction
- performance prediction
- best pitcher output
- preferred pitcher output
- recommended pitcher output
- hidden priority output
- manager intent inference
- private data integration

The planned readiness calculation is team-level and context-level only. It
must not produce a pitcher-level recommendation, ranking, ordering, selection,
or decision command.

## Proposed Backend Architecture

The preferred future architecture is a separate Team Operations layer that
reuses certified BaseballOS data and governance patterns without modifying the
certified Recommendation Engine V2 runtime contract.

Preferred architecture:

| Layer | Planned Responsibility |
|-------|------------------------|
| Source data access | Read current roster, fatigue, workload, availability, sync, and trust metadata from existing services. |
| Domain assembly | Build a governed `BullpenReadinessAssessment` from current evidence. |
| Governance validation | Reject prohibited fields, unsupported inputs, ranking signals, selection signals, prediction signals, and missing metadata. |
| Contract serialization | Serialize only team-level readiness, distributions, coverage counts, explanations, limitations, refusal state, and metadata. |
| API exposure | Expose a future Team Operations endpoint after a separate API contract phase. |
| Frontend client | Normalize available, data-limited, fail-closed, refused, and unavailable states. |
| Dashboard surface | Present a summary-first readiness panel with expand-on-demand evidence. |

The recommended future implementation should not extend the certified V2
endpoint as the first choice. A separate Team Operations endpoint keeps the
certified V2 bullpen-state contract stable while still reusing its evidence
patterns.

## Proposed Domain Module Structure

Likely future backend files:

```text
backend/team_operations/__init__.py
backend/team_operations/bullpen_readiness.py
backend/team_operations/bullpen_readiness_contracts.py
backend/team_operations/bullpen_readiness_governance.py
backend/team_operations/bullpen_readiness_assembly.py
backend/api/team_operations.py
backend/tests/test_team_operations_bullpen_readiness_domain.py
backend/tests/test_team_operations_bullpen_readiness_api_contract.py
backend/tests/test_team_operations_bullpen_readiness_governance.py
```

Planned domain objects:

| Object | Purpose |
|--------|---------|
| `BullpenReadinessAssessment` | Top-level team-level readiness response. |
| `ReadinessStatus` | Allowed readiness status vocabulary. |
| `ConstraintSummary` | Neutral counts and reasons for current constraints. |
| `WorkloadPressureSummary` | Team-level workload category counts and explanation. |
| `CoverageInventory` | Neutral roster and coverage counts. |
| `HandednessCoverage` | Left/right/unknown throwing-hand counts. |
| `AvailabilityDistribution` | Counts by existing availability status. |
| `ReadinessTrustMetadata` | Trust, governance, limitations, explanations, and refusal metadata. |
| `ReadinessFreshnessMetadata` | Data-through, sync, stale, missing, and generated timestamp metadata. |
| `ReadinessRefusal` | Fail-closed and refusal reason details. |

The domain layer should use dataclasses or equivalent structured objects before
serialization so tests can validate governance boundaries before API exposure.

## Proposed API Endpoint Plan

Preferred future endpoint:

```text
GET /api/team-operations/v3/bullpen-readiness
```

Required query parameters should be minimal:

| Parameter | Status | Notes |
|-----------|--------|-------|
| `team_id` | Optional initially, required if multi-team ambiguity exists | Uses existing team identifiers only. |
| `limit` | Optional internal safety limit | Must not become a priority or ranking control. |

Forbidden request parameters:

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
- `prediction`
- `matchup`
- `leverage_context`
- `save_prediction`
- `injury_prediction`
- `performance_prediction`

If forbidden parameters are present, the future endpoint should fail closed and
return refusal metadata.

Alternative endpoint strategy:

```text
GET /api/recommendations/v2/bullpen-state
```

This should not be the preferred first implementation path because it would
expand a certified V2 recommendation contract. Any V2 extension would require a
separate contract review, regression review, certification review, and rollout
decision.

## Proposed Response Contract

The future response should be team-level and governance-safe:

```json
{
  "capability": "team_operations_bullpen_readiness",
  "scope": "team_bullpen_readiness",
  "ranking_applied": false,
  "selection_made": false,
  "contract_state": "available",
  "generated_at": "ISO-8601 timestamp",
  "team": {
    "team_id": 111,
    "team_name": "Team Name",
    "team_abbreviation": "ABC"
  },
  "readiness": {
    "status": "Operationally Constrained",
    "status_code": "operationally_constrained",
    "summary": "Team-level readiness is constrained by current workload distribution.",
    "basis": [
      "availability_distribution",
      "workload_pressure",
      "freshness_metadata",
      "trust_metadata"
    ]
  },
  "availability_distribution": {
    "available": 0,
    "monitor": 0,
    "limited": 0,
    "avoid": 0,
    "unavailable": 0,
    "unknown": 0
  },
  "workload_pressure": {
    "pressure_state": "moderate",
    "elevated_count": 0,
    "moderate_count": 0,
    "low_count": 0,
    "unknown_count": 0
  },
  "coverage_inventory": {
    "active_pitcher_count": 0,
    "current_workload_data_count": 0,
    "missing_workload_data_count": 0
  },
  "handedness_coverage": {
    "left_handed_count": 0,
    "right_handed_count": 0,
    "unknown_count": 0
  },
  "constraints": [],
  "explanations": [],
  "limitations": [],
  "freshness": {},
  "trust_metadata": {},
  "refusal": {
    "refused": false,
    "reason_codes": []
  },
  "fail_closed": {
    "failed_closed": false,
    "reason_codes": []
  }
}
```

Contract requirements:

- `ranking_applied` must be `false`.
- `selection_made` must be `false`.
- no pitcher-level ranking may be present
- no pitcher-level selection may be present
- no pitcher recommendation may be present
- no quality-based ordering may be present
- no best, preferred, or recommended labels may be present
- no game outcome, injury, save, or performance prediction may be present
- no matchup advice may be present
- no hidden priority fields may be present

If the contract cannot truthfully preserve these requirements, the future
endpoint must fail closed.

## Allowed Input Data

Allowed inputs remain limited to current BaseballOS public-data and certified
governance surfaces:

| Input Area | Allowed Data |
|------------|--------------|
| Roster | Team id, team name, team abbreviation, active flag, pitcher id, MLB id, pitcher name, position, throwing hand. |
| Fatigue | Existing fatigue score, fatigue risk tier, component evidence, calculated timestamp. |
| Workload | Days since last appearance, recent appearances, recent pitch counts, recent innings, latest workload date. |
| Availability | Existing availability status, confidence, data state, reasons, limitations, deterministic inputs. |
| Freshness | Data-through date, last successful sync, latest sync status, latest fatigue calculation timestamp, generated timestamp. |
| Trust | Confidence, limitations, explanations, refusal reasons, fail-closed metadata, governance metadata. |
| V2 evidence | Certified V2 team bullpen context and inventory evidence as source context only. |

Allowed inputs must be deterministic, auditable, and explainable.

## Prohibited Input Data

Prohibited inputs:

- injury reports
- transaction reports
- team-reported availability
- medical information
- illness information
- travel information
- bullpen warm-up activity
- bullpen phone activity
- manager intent
- coach intent
- live game state
- score, inning, base/out state, or leverage context
- opponent matchup context
- win probability
- save opportunity prediction
- future performance projection
- Statcast, Hawk-Eye, Stuff+, biomechanics, or pitch-quality models
- prospect grades
- prospect development data
- unreviewed external feeds
- manual readiness overrides
- hidden priority fields

These inputs require separate data-source, metadata, failure-mode, refusal,
test, certification, and rollout review before any future use.

## Readiness Status Calculation Plan

Allowed readiness statuses:

| Status | Status Code | Planned Trigger |
|--------|-------------|-----------------|
| Operationally Stable | `operationally_stable` | Current data is fresh, trust metadata is complete, and constrained inventory is low. |
| Operationally Constrained | `operationally_constrained` | Meaningful availability, workload, freshness, or coverage constraints exist, but evidence remains sufficient. |
| Operationally Stressed | `operationally_stressed` | Elevated concentration of unavailable, avoid, limited, elevated workload, or stale evidence exists. |
| Data Limited | `data_limited` | Data is stale, partial, low-confidence, incomplete, or coverage-limited. |
| Refused | `refused` | Required evidence or governance metadata is missing, unsafe, or unsupported. |

Calculation boundaries:

- The status is team-level/context-level only.
- The status must not score pitchers.
- The status must not order pitchers by quality.
- The status must not identify a pitcher to use.
- The status must not predict future performance or health.
- The status must not incorporate game-state or matchup advice.

The calculation should evaluate distributions and counts, not pitcher
preference.

## Constraint Detection Plan

Planned constraint categories:

| Constraint | Detection Basis |
|------------|-----------------|
| Workload constraint | Elevated or compressed current workload counts. |
| Availability constraint | Counts in Monitor, Limited, Avoid, Unavailable, or Unknown. |
| Freshness constraint | Stale, historical, missing, incomplete, or unknown data state. |
| Trust constraint | Missing confidence, limitations, explanations, refusal, or governance metadata. |
| Coverage constraint | Missing roster, workload, handedness, or active pitcher coverage. |
| Refusal constraint | Any fail-closed or explicit refusal condition. |
| Governance constraint | Forbidden input or output fields detected. |

Constraint output should include:

- constraint id
- category
- severity
- affected team-level area
- count when available
- explanation
- limitation
- recovery note when available

Constraints must not advise which pitcher to use.

## Workload Pressure Summary Plan

The future workload pressure summary should use public workload and fatigue
evidence only.

Planned categories:

| Category | Meaning |
|----------|---------|
| Low | Current workload evidence shows low recent pressure. |
| Moderate | Current workload evidence shows moderate pressure or some cautionary usage. |
| Elevated | Current workload evidence shows elevated recent usage, high fatigue band, or compressed usage count. |
| Unknown | Workload evidence is missing or stale. |

Planned output:

- pressure state
- category counts
- missing workload data count
- latest workload date
- explanation
- limitations

The workload pressure summary must not infer injury, fatigue beyond the
existing formula, or future performance.

## Coverage Inventory Plan

Coverage inventory should summarize current team-level bullpen evidence.

Planned fields:

- active pitcher count
- pitcher records with current workload data
- pitcher records missing workload data
- pitcher records with current availability status
- pitcher records missing availability status
- roster coverage limitations
- coverage explanation

Coverage inventory must remain neutral. It must not become a depth chart,
preference list, role certainty claim, or pitcher selection surface.

## Handedness Coverage Plan

Handedness coverage should use public roster throwing-hand fields only.

Planned fields:

- left-handed active pitcher count
- right-handed active pitcher count
- switch or unknown handedness count if applicable
- missing throwing-hand count
- roster source limitation

Handedness coverage must not become matchup advice. It may describe roster
coverage counts only.

## Availability Distribution Plan

Availability distribution should reuse the existing Availability Engine status
vocabulary:

- Available
- Monitor
- Limited
- Avoid
- Unavailable
- Unknown

Planned fields:

- count by status
- total count
- confidence distribution when available
- data-state distribution when available
- explanation
- limitations

The distribution must not rank pitchers inside a status. If members are shown
in a future UI expansion, ordering must be alphabetical or stable source order
and explicitly documented as non-ranking.

## Trust Metadata Plan

Required trust metadata:

- scope
- capability
- confidence
- confidence reasons
- data state
- source evidence state
- governance state
- generated timestamp
- limitations
- explanations
- refusal reasons
- trust validation errors
- `ranking_applied`
- `selection_made`

Required values:

```text
ranking_applied === false
selection_made === false
```

Trust metadata must be present on available, data-limited, refused, and
fail-closed responses.

## Freshness Metadata Plan

Required freshness metadata:

- data-through date
- latest workload date
- last successful sync
- latest sync status
- latest fatigue calculation timestamp
- generated timestamp
- freshness state
- stale data warning
- missing data warning
- freshness limitations

Freshness rules:

- sync timestamp must not replace data-through date
- stale data must reduce confidence, qualify the output, or trigger refusal
- missing data must reduce confidence, qualify the output, or trigger refusal
- unknown freshness must not be displayed as complete readiness

## Refusal/Fail-Closed Plan

Future implementation must fail closed when:

- required team or bullpen data is missing
- trust metadata is absent
- freshness metadata is absent
- refusal metadata is required but absent
- current workload data is stale beyond the accepted window
- source evidence is malformed
- unsupported input fields are present
- forbidden output fields would be produced
- ranking behavior would be implied
- selection behavior would be implied
- prediction behavior would be implied
- best, preferred, or recommended behavior would be implied
- confidence is too low to support a readiness summary

Fail-closed responses should preserve:

- capability
- scope
- `ranking_applied === false`
- `selection_made === false`
- confidence
- data state
- freshness
- limitations
- explanations when available
- refusal reasons
- fail-closed reason codes

Refusal is a valid output. Unsupported gaps must not be filled with invented
baseball logic.

## Explainability Plan

Every readiness output should explain:

- assigned readiness status
- status basis
- availability distribution basis
- workload pressure basis
- coverage inventory basis
- handedness coverage basis when available
- freshness state
- trust limitations
- refusal or fail-closed condition when present

Explanations should be attached to the output they qualify. Static methodology
text is not enough.

## Frontend Integration Plan

Likely future frontend files:

```text
frontend/src/utils/api.js
frontend/src/components/team-operations/TeamOperationsBullpenReadinessPanel.jsx
frontend/src/components/team-operations/TeamOperationsBullpenReadinessView.js
frontend/src/components/dashboard/Dashboard.jsx
frontend/tests/teamOperationsBullpenReadiness.test.mjs
```

Planned frontend client responsibilities:

- request the future Team Operations endpoint
- normalize available, data-limited, refused, fail-closed, and unavailable
  states
- reject missing governance metadata
- reject forbidden ranking, selection, prediction, and decision-language fields
- expose freshness, trust, limitations, explanations, and refusal details
- preserve V2 and V1 regression behavior

The frontend plan should not reuse visual patterns that imply a pitcher order
or final action.

## Dashboard Presentation Plan

Preferred presentation:

- one Team Operations Bullpen Readiness panel on Dashboard
- summary-first readiness status
- visible data-through and generated timestamps
- availability distribution counts
- workload pressure summary
- coverage and handedness counts
- visible trust and governance metadata
- expand-on-demand explanations, limitations, and refusal details
- fail-closed and refused states shown as valid states

Dashboard presentation must avoid:

- leaderboard layouts
- numbered pitcher lists
- winner badges
- first-choice styling
- pitcher cards sorted by quality
- best/preferred/recommended labels
- visual hierarchy that selects a pitcher

## Accessibility Plan

Future implementation should require:

- accessible panel heading
- clear status label
- text equivalent for readiness state
- text equivalent for every distribution and count group
- color-independent readiness and constraint indicators
- keyboard access to expanded details
- stable focus order
- live-region messaging for loading, fail-closed, refused, and unavailable
  states
- accessible labels for trust, freshness, limitations, explanations, and
  refusal metadata
- mobile layout review at 320 px, 375 px, 390 px, and 768 px

Accessibility evidence should be included before certification eligibility.

## Test Strategy

Future backend tests should cover:

- domain object serialization
- allowed readiness statuses
- availability distribution counts
- workload pressure counts
- coverage inventory counts
- handedness coverage counts
- trust metadata presence
- freshness metadata presence
- refusal metadata presence
- fail-closed responses
- stale data behavior
- missing data behavior
- malformed evidence behavior
- low-confidence behavior
- forbidden request fields
- forbidden response fields
- `ranking_applied === false`
- `selection_made === false`
- no pitcher ranking behavior
- no pitcher selection behavior
- no prediction behavior
- no best/preferred/recommended behavior

Future frontend tests should cover:

- client normalization
- available rendering
- data-limited rendering
- fail-closed rendering
- refused rendering
- unavailable rendering
- trust metadata visibility
- freshness metadata visibility
- limitation visibility
- explanation visibility
- refusal visibility
- prohibited display language
- no leaderboard or ordered-choice rendering
- keyboard and accessible label behavior
- V1 and V2 regression safety

Exact future test names should be created during the implementation phase and
recorded in the lifecycle evidence packet.

## Certification Strategy

Certification should require evidence that:

- allowed inputs are documented and used
- prohibited inputs are absent
- the API contract is implemented exactly after approval
- response metadata is complete
- readiness status remains team-level/context-level
- no pitcher-level ranking exists
- no pitcher-level selection exists
- no pitcher recommendation exists
- no prediction behavior exists
- no best/preferred/recommended behavior exists
- fail-closed behavior works
- stale and missing data are handled safely
- frontend rendering preserves governance boundaries
- accessibility validation is complete
- lifecycle evidence packet is updated
- rollout review is completed before production exposure

Certification must occur before the capability is called production-ready.

## Rollout Strategy

Future rollout should use staged governance gates:

1. API contract and certification requirements approved.
2. Backend domain foundation implemented and tested.
3. API route implemented and contract-tested.
4. Frontend client implemented and tested.
5. Dashboard panel implemented and accessibility-tested.
6. Certification review completed.
7. Lifecycle evidence packet updated.
8. Production rollout decision completed.
9. Post-rollout monitoring and boundary review completed.

No rollout should occur until certification and rollout review are complete.

## Risks And Mitigations

| Risk | Mitigation |
|------|------------|
| Readiness status is interpreted as pitcher guidance | Keep status team-level and attach limitations that the user remains responsible for decisions. |
| Future endpoint expands certified V2 behavior accidentally | Prefer a separate Team Operations endpoint and require a separate API contract review. |
| Coverage inventory becomes a hidden depth chart | Use counts, neutral groupings, and non-ranking ordering only. |
| Handedness coverage becomes matchup advice | Present only left/right/unknown counts with limitation text. |
| Workload pressure becomes injury or performance inference | Tie output to public workload and existing fatigue evidence only. |
| Missing freshness metadata is overlooked | Fail closed or mark Data Limited with visible warnings. |
| Frontend visual hierarchy implies a selected pitcher | Prohibit leaderboard, winner, first-choice, and quality-sorted layouts. |
| Tests verify happy paths but not governance boundaries | Require forbidden-field, metadata, refusal, and display-language tests. |

## Implementation Sequence

Recommended future sequence:

1. Create the Phase 4 API contract and certification requirements document.
2. Define approved request and response schemas.
3. Define forbidden request and response field validation.
4. Create backend Team Operations domain objects.
5. Add backend assembly from existing roster, fatigue, availability, workload,
   freshness, and trust evidence.
6. Add governance validation and fail-closed behavior.
7. Add API route only after the contract is approved.
8. Add backend contract and governance tests.
9. Add frontend API normalization only after API contract tests pass.
10. Add Dashboard readiness panel with summary-first presentation.
11. Add frontend rendering, prohibited-language, and accessibility tests.
12. Complete certification review.
13. Update lifecycle evidence packet.
14. Complete rollout decision review.

## Governance Boundaries

The certified governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

V3 Phase 3 explicitly reaffirms:

- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best option behavior exists
- no preferred option behavior exists
- no recommended option behavior exists

The implementation plan prohibits:

- pitcher ranking
- pitcher selection
- pitcher recommendation
- quality-based ordering
- best labels
- preferred labels
- recommended labels
- game outcome prediction
- injury prediction
- save prediction
- performance prediction
- matchup advice
- hidden priority outputs

Any readiness calculation must be team-level/context-level only and must not
produce a pitcher-level recommendation, ranking, ordering, selection, or
decision command.

## Validation

Validation required for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-3-readiness-plan
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

Root `npm test` is not required for V3 Phase 3. If no root `package.json`
exists, that is expected and is not a project failure.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 4 Team Operations Bullpen Readiness API Contract And Certification Requirements
```

The next milestone should remain documentation and contract planning unless
implementation is explicitly authorized. It should define the exact future API
contract, response schema, forbidden fields, certification requirements, and
evidence requirements before runtime work begins.
