# BaseballOS V4 Phase 6 - Availability Explanation Integration

## Phase Status

Phase status:

```text
V4_PHASE_6_AVAILABILITY_EXPLANATION_INTEGRATION_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Implementation status:

```text
INTERNAL_BACKEND_AVAILABILITY_ADAPTER_ONLY
```

This phase integrates the deterministic V4 Evidence and Explanation builder
with existing Availability Engine outputs. It allows BaseballOS backend code to
construct governed V4 explanations for existing availability states without
changing how those states are calculated.

This phase does not add API routes, frontend UI, dashboard rendering, database
storage, recommendation explanations, readiness explanations, production
certification, or rollout approval.

## Integration Approach

Phase 6 adds an internal adapter:

```text
backend/explanations/availability.py
```

The adapter accepts an existing Availability Engine output dictionary from
`classify_availability(...)` and returns a `V4Explanation`.

The adapter is intentionally one-way:

- it reads existing availability status output
- it maps available evidence into V4 evidence items
- it maps supported conditions into existing V4 reason codes
- it maps known data limits into V4 limitations
- it attaches V4 governance defaults through the Phase 5 builder
- it does not mutate the original availability dictionary
- it does not call Flask routes
- it does not alter API payloads

## Files Added

```text
backend/explanations/availability.py
backend/tests/test_v4_availability_explanation_integration.py
docs/V4_PHASE_6_AVAILABILITY_EXPLANATION_INTEGRATION.md
```

## Files Modified

```text
backend/explanations/__init__.py
README.md
docs/INDEX.md
docs/PROJECT_STATE_2026_06.md
docs/ROADMAP.md
```

## Availability States Covered

The adapter supports the existing Availability Engine status vocabulary:

```text
Available
Monitor
Limited
Avoid
Unavailable
```

Each explanation uses:

```text
scope = availability_state
subject_type = pitcher
state_explained = existing availability status
```

The subject id is caller-provided and required. Missing subject identifiers fail
closed rather than creating ambiguous explanation records.

## Reason Mapping

Phase 6 uses only Phase 4 reason codes.

Supported mappings:

| Availability condition | V4 reason code |
| --- | --- |
| Monitor status | `AVAILABILITY_MONITOR_THRESHOLD_MET` |
| Workload reasons present | `WORKLOAD_RECENT_USAGE_ELEVATED` |
| Stale workload data | `FRESHNESS_STALE_SOURCE` |
| Incomplete workload inputs | `COVERAGE_PARTIAL` |
| Missing evidence or limited confidence | `TRUST_LIMITED` |

No new reason codes were added in this phase.

## Evidence Mapped

The adapter maps evidence only when it is present in the existing availability
output.

Base evidence:

- availability status
- availability confidence
- availability data state

Workload evidence when available:

- fatigue score
- pitches yesterday
- pitches in 3 days
- pitches in 5 days
- appearances in 3 days
- appearances in 5 days
- days of rest
- back-to-back appearance flag
- three appearances in four days flag
- four appearances in five days flag

Freshness and trust references are derived from existing `data_state` and
`confidence` fields. Missing workload evidence is not converted into fabricated
zero-value workload evidence.

## Limitations Supported

The adapter supports Phase 4 limitation types:

```text
missing_data
stale_data
partial_coverage
limited_confidence
insufficient_context
```

Existing Availability Engine limitation text is preserved and mapped into the
closest V4 limitation type. The adapter also adds explicit limitations when
data is missing, stale, incomplete, or confidence is limited.

## Governance Preservation

Every generated availability explanation preserves:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

The adapter does not introduce:

- ranking behavior
- selection behavior
- prediction behavior
- recommendation behavior
- best/preferred arm behavior
- hidden priority ordering
- pitcher-level advice
- matchup advice
- decision automation

V4 may explain an existing availability state.

V4 may not decide what the user should do.

## Behavior Preservation

Phase 6 does not modify:

- `backend/services/availability.py`
- fatigue calculations
- availability thresholds
- status assignment logic
- API routes
- API response shapes
- frontend rendering
- dashboard behavior
- recommendation behavior
- readiness behavior

Focused tests verify that explanation generation does not mutate existing
availability output.

## Test Coverage

Backend tests were added in:

```text
backend/tests/test_v4_availability_explanation_integration.py
```

Coverage verifies:

- Available state explanation generation
- Monitor state explanation generation
- Limited state explanation generation
- Avoid state explanation generation
- Unavailable state explanation generation
- workload evidence mapping
- freshness evidence mapping
- stale-data limitation mapping
- missing-data limitation behavior without fabricated workload evidence
- incomplete-data partial coverage limitation behavior
- governance defaults
- deterministic repeated output
- invalid availability status refusal
- missing subject id refusal
- absence of prohibited ranking, selection, recommendation, prediction,
  best/preferred arm, hidden priority ordering, pitcher-level advice, and
  matchup-advice fields
- preservation of existing availability status outputs

Focused validation also re-ran existing availability tests and V4 deterministic
builder tests.

## Intentionally Not Implemented

Phase 6 intentionally does not implement:

- public API exposure of V4 availability explanations
- frontend client normalization
- Dashboard UI rendering
- Team Operations Bullpen Readiness explanations
- Recommendation Engine explanations
- database persistence
- external data sources
- certification approval
- rollout approval

Future phases must separately review and authorize any API, frontend,
certification, or rollout work.

## Remaining Risks

- V4 availability explanations are internal backend objects only until a future
  API or frontend phase is authorized.
- Reason-code coverage remains intentionally conservative because Phase 6 did
  not add new reason codes.
- Future API exposure must preserve existing availability response compatibility
  or provide a separately documented contract.
- Future UI work must avoid turning the existing `Avoid` availability state into
  user instruction language.

## Recommended Next Milestone

```text
V4 Phase 7 - Availability Explanation Certification Readiness Review
```

The next milestone should review whether the internal availability explanation
adapter is ready for API contract planning or further backend integration. It
should verify governance, determinism, reason-code sufficiency, evidence
coverage, behavior preservation, and certification gaps before public exposure.
