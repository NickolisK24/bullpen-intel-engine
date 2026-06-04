# BaseballOS V5 Phase 2 - Bullpen Intelligence Surface Observation Taxonomy

## Phase Status

Phase status:

```text
V5_PHASE_2_BULLPEN_INTELLIGENCE_SURFACE_OBSERVATION_TAXONOMY_APPROVED
```

Certification roadmap status:

```text
V5_PHASE_2_OBSERVATION_TAXONOMY_APPROVED
```

Capability track:

```text
V5_BULLPEN_INTELLIGENCE_SURFACE
```

Implementation status:

```text
PLANNING_ONLY
```

V5 Phase 2 approves only the Bullpen Intelligence Surface observation taxonomy.
It defines allowed observation families, approved inputs, expected future output
shape, language rules, governance boundaries, and fail-closed requirements
before any implementation begins.

This phase does not authorize backend code, frontend code, APIs, schemas,
database changes, tests, runtime behavior changes, ranking behavior, selection
behavior, recommendation behavior, prediction behavior, pitcher advice, matchup
advice, or automated decision-making.

## 1. Purpose

An observation is a descriptive, evidence-backed statement about existing
BaseballOS bullpen state.

Observations exist to help users notice meaningful bullpen state, movement,
limitations, and trust conditions without converting those signals into a
decision. They turn existing trusted platform outputs into clear language that
can be reviewed, explained, limited, or suppressed.

Observations differ from recommendations because observations describe what the
platform already knows or cannot safely know. Recommendations, selections,
rankings, preferred choices, matchup guidance, and usage instructions tell a
user what to do or imply a decision. V5 may not do that.

V5 observations may answer:

- what current inventory state exists
- what readiness state exists
- what workload pressure state exists
- what constraints qualify the state
- what freshness or trust limitations apply
- what changed between trusted snapshots
- what explanation evidence supports the statement

V5 observations must not answer:

- who to use
- who is best
- who should close
- who should be preferred
- who matches up better
- who will perform better
- what decision a manager should make

## 2. Authorized Observation Families

The official V5 observation families are:

- Inventory Observations
- Readiness Observations
- Workload Pressure Observations
- Constraint Observations
- Freshness Observations
- Trust Observations
- Availability Movement Observations
- Snapshot Change Observations

Each family must remain descriptive, evidence-based, trust-aware, explainable,
non-prescriptive, and non-predictive.

### Inventory Observations

Purpose:

Inventory observations describe current bullpen inventory counts and safe
grouped state.

Allowed inputs:

- active pitcher count
- available current pitcher count
- availability distribution counts
- roster coverage count
- handedness coverage count when already available
- role or position coverage count when already available
- existing trusted V2 and V3 inventory metadata

Allowed outputs:

- inventory count summaries
- inventory expansion or contraction statements
- availability bucket count statements
- coverage limitation statements
- missing inventory evidence statements

Required evidence:

- trusted roster or bullpen inventory source
- generated timestamp
- data-through or workload freshness reference
- availability distribution or coverage source
- confidence and limitation metadata when available

Failure conditions:

- required inventory source is missing
- inventory source is stale beyond accepted freshness boundaries
- active bullpen state is incomplete or ambiguous
- inventory statement would imply a depth chart or preference order
- explanation support is missing for the observation

### Readiness Observations

Purpose:

Readiness observations describe current team-level readiness state and the
visible contributors that qualify it.

Allowed inputs:

- V3 Team Operations Readiness state
- readiness constraints
- readiness confidence metadata
- readiness freshness metadata
- readiness limitations
- readiness explanation references
- fail-closed or refusal metadata

Allowed outputs:

- current readiness state summaries
- readiness degradation or data-limited statements
- readiness contributor statements
- readiness limitation statements
- readiness refusal statements

Required evidence:

- trusted readiness payload
- readiness status or refusal state
- contributing constraint evidence
- freshness and confidence metadata
- explanation reference for the readiness state

Failure conditions:

- readiness payload is missing
- readiness state is unsupported or refused
- confidence is insufficient without visible limitation text
- freshness metadata is missing
- observation would become pitcher advice or action guidance

### Workload Pressure Observations

Purpose:

Workload pressure observations describe grouped workload stress, recent usage
compression, and elevated workload distribution.

Allowed inputs:

- fatigue state
- workload pressure signals
- recent usage counts
- appearance compression evidence
- multi-day pitch load evidence
- rest buffer evidence
- V3 workload pressure summaries
- explanation evidence for workload contributors

Allowed outputs:

- workload pressure elevated or limited statements
- recent usage concentration statements
- grouped workload distribution statements
- workload evidence limitation statements

Required evidence:

- trusted fatigue or workload source
- current calculation timestamp
- workload date or data-through date
- contributing workload signals
- confidence and limitation metadata

Failure conditions:

- workload source is missing or stale
- current calculation timestamp is absent
- workload statement would imply injury risk prediction
- workload statement would identify a preferred or avoided pitcher as advice
- explanation support is missing

### Constraint Observations

Purpose:

Constraint observations describe current constraints that limit bullpen state,
readiness, inventory, workload visibility, or interpretation.

Allowed inputs:

- availability constraints
- readiness constraints
- workload constraints
- roster coverage constraints
- confidence constraints
- freshness constraints
- explanation constraints
- refusal and fail-closed metadata

Allowed outputs:

- constraint summary statements
- constraint count statements
- data-limited qualification statements
- refused or suppressed observation statements
- limitation visibility statements

Required evidence:

- trusted constraint source
- affected output area
- limitation or refusal reason
- freshness and confidence metadata when relevant
- explanation reference when available

Failure conditions:

- constraint reason is not traceable
- affected output area is unclear
- constraint text would become action guidance
- constraint text hides freshness, confidence, or refusal state
- constraint cannot be explained from trusted platform evidence

### Freshness Observations

Purpose:

Freshness observations describe source currency, sync state, data-through state,
and freshness protection.

Allowed inputs:

- data-through date
- latest workload date
- last successful sync
- latest sync status
- generated timestamp
- stale-data indicator
- missing-data indicator
- freshness limitations
- freshness protection metadata

Allowed outputs:

- freshness protection statements
- stale-data limitation statements
- sync status qualification statements
- data-through visibility statements
- missing freshness metadata statements

Required evidence:

- trusted sync or freshness source
- data-through or workload date
- generated timestamp
- source evidence state
- limitation or refusal metadata when freshness is unsafe

Failure conditions:

- freshness source is missing
- sync timestamp is substituted for data-through date
- stale data would be presented as current
- missing data would be presented as complete
- freshness limitation is unavailable for a degraded observation

### Trust Observations

Purpose:

Trust observations describe confidence, source evidence state, governance state,
limitations, and whether an observation is supported, limited, or suppressed.

Allowed inputs:

- confidence metadata
- trust metadata
- source evidence state
- governance metadata
- limitations
- refusal reasons
- fail-closed metadata
- explanation references

Allowed outputs:

- trust-aware warning statements
- confidence limitation statements
- source evidence limitation statements
- governance boundary statements
- suppressed observation statements

Required evidence:

- trusted confidence or trust source
- limitation reason when confidence is degraded
- governance metadata when available
- refusal or fail-closed state when applicable
- explanation reference for the trust limitation

Failure conditions:

- confidence metadata is missing
- trust source is unknown
- limitation reason is absent for low confidence
- governance metadata is absent where required
- observation would hide uncertainty or overstate support

### Availability Movement Observations

Purpose:

Availability movement observations describe movement in availability state or
distribution between trusted snapshots.

Allowed inputs:

- current availability distribution
- previous trusted availability distribution
- availability classifications
- status counts
- snapshot timestamps
- freshness metadata for both snapshots
- explanation evidence for movement where available

Allowed outputs:

- availability inventory contracted statements
- availability inventory expanded statements
- Monitor, Limited, Avoid, or Unavailable bucket movement statements
- no-material-change statements
- movement unavailable statements

Required evidence:

- current trusted snapshot
- previous trusted snapshot
- comparable availability status vocabulary
- timestamps for both snapshots
- freshness and confidence metadata for both snapshots

Failure conditions:

- previous snapshot is missing
- snapshots are not comparable
- snapshot freshness is unsafe
- movement statement would imply pitcher ordering, quality, or preference
- explanation support is unavailable for material movement

### Snapshot Change Observations

Purpose:

Snapshot change observations describe trusted changes between current and prior
platform snapshots beyond availability movement.

Allowed inputs:

- current trusted platform snapshot
- previous trusted platform snapshot
- inventory counts
- readiness state
- workload pressure state
- freshness state
- trust state
- explanation references

Allowed outputs:

- snapshot state changed statements
- snapshot state unchanged statements
- readiness changed statements
- workload pressure changed statements
- freshness or trust limitation changed statements
- change unavailable statements

Required evidence:

- current trusted snapshot
- previous trusted snapshot
- comparable snapshot schema or documented comparison basis
- timestamps for both snapshots
- trusted source metadata for both snapshots
- explanation reference for the changed area when available

Failure conditions:

- prior snapshot is missing
- snapshot sources are incompatible
- timestamp ordering is unclear
- current or previous snapshot fails trust or freshness checks
- change statement would become prediction, ranking, selection, or advice

## 3. Observation Inputs

V5 observations may only use trusted platform outputs already governed by
BaseballOS.

Approved input areas:

- Availability classifications
- Readiness state
- Fatigue state
- Workload pressure state
- Inventory counts
- Availability distribution counts
- Freshness metadata
- Confidence metadata
- Trust metadata
- Refusal metadata
- Fail-closed metadata
- Limitation metadata
- Explanation evidence
- Certified governance records
- Current and previous trusted snapshots

Approved source surfaces include:

- Availability Engine V1 outputs
- Recommendation Engine V2 governed bullpen-state outputs, with ranking and
  selection disabled
- V3 Team Operations Readiness outputs
- V4 certified explanation outputs and references
- Existing sync and freshness metadata
- Existing governance certification records

V5 observations must not use unreviewed external feeds, private medical data,
clubhouse status, warm-up activity, bullpen phone activity, team travel context,
manager intent, matchup models, performance projection models, or manually
invented overrides.

## 4. Observation Output Requirements

Future implementation should define deterministic observation result models.
This phase does not implement those models.

Expected future fields:

| Field | Requirement |
| --- | --- |
| Observation type | Required controlled vocabulary matching an authorized observation family. |
| Observation title | Required short descriptive title with no recommendation or selection language. |
| Observation summary | Required state-based summary derived from trusted evidence. |
| Evidence | Required evidence list or reference for the observation. |
| Confidence | Required confidence status and reason when confidence is limited. |
| Freshness | Required freshness status and source date references. |
| Limitations | Required when data, confidence, trust, or freshness is incomplete. |
| Explanation reference | Required reference to supporting V4 or source explanation evidence when available. |
| Severity | Optional controlled severity for display priority, not pitcher priority. |
| Suppression reason | Required when an observation is withheld or fails closed. |
| Generated timestamp | Required deterministic generation timestamp or platform timestamp. |
| Governance metadata | Required preservation of no-ranking and no-selection boundaries. |

Required preserved governance flags:

```text
ranking_applied === false
selection_made === false
```

Future output models must not include ranking fields, selected pitcher fields,
recommended pitcher fields, matchup advice fields, prediction fields, hidden
priority fields, or pitcher usage instruction fields.

## 5. Governance Boundary Matrix

| Area | Allowed behavior | Prohibited behavior |
| --- | --- | --- |
| Inventory | `Inventory increased.` | `Use the deeper inventory now.` |
| Availability | `Monitor inventory contracted.` | `Pitcher X should be avoided tonight.` |
| Workload | `Workload pressure elevated.` | `Use Pitcher X because others are tired.` |
| Freshness | `Freshness protections are affecting records.` | `Ignore stale records and use Pitcher Y.` |
| Trust | `Confidence is limited by missing source evidence.` | `Pitcher Y is still the best option.` |
| Readiness | `Readiness is data limited.` | `Manager should use Pitcher Z.` |
| Movement | `Availability inventory contracted since the prior snapshot.` | `This arm is preferred after the change.` |
| Snapshot change | `Current snapshot differs from the prior trusted snapshot.` | `Pitcher Z should close.` |

Allowed examples:

```text
Inventory increased.
```

```text
Monitor inventory contracted.
```

```text
Workload pressure elevated.
```

```text
Freshness protections affecting records.
```

Forbidden examples:

```text
Use Pitcher X.
```

```text
Pitcher Y is best.
```

```text
Manager should use Pitcher Z.
```

```text
Pitcher Z should close.
```

```text
This arm is preferred.
```

## 6. Observation Language Rules

Allowed language patterns:

- descriptive
- state-based
- evidence-based
- trust-aware
- freshness-aware
- limitation-aware
- non-prescriptive
- non-predictive
- traceable to a supported source

Allowed verbs and phrases:

- increased
- decreased
- contracted
- expanded
- changed
- unchanged
- elevated
- limited
- affected by freshness protection
- supported by current evidence
- limited by current evidence
- unavailable because evidence is incomplete

Forbidden language patterns:

- prescriptive
- comparative ranking
- selection language
- predictive language
- best/preferred/recommended language
- matchup advice
- pitcher usage advice
- closer/setup/role advice
- hidden priority language
- manager-intent language
- unsupported medical or private-data inference

Forbidden verbs and phrases:

- use
- choose
- pick
- rank
- start with
- best
- preferred
- recommended
- should close
- should use
- matchup favors
- likely to perform
- safest arm
- top option
- optimal choice

Observation copy must describe the state, not the decision.

## 7. Fail-Closed Requirements

V5 observations must be suppressed or returned as refused/data-limited when:

- source evidence is missing
- source evidence is stale beyond accepted freshness boundaries
- confidence is insufficient
- trust metadata is missing
- freshness metadata is missing
- inventory state is incomplete
- prior snapshot is required but unavailable
- snapshots are incompatible
- explanation support is missing for an observation type that requires it
- an observation cannot be traced to trusted platform output
- a statement would imply ranking, selection, recommendation, prediction, or
  pitcher advice
- required governance flags are absent
- unsupported external data appears

Fail-closed outcomes are valid V5 outcomes. The surface should withhold unsafe
observations rather than filling gaps with baseball assumptions.

## 8. Future Implementation Guidance

Future V5 phases should proceed in order:

1. Backend observation contracts
2. Observation builders
3. API layer
4. Frontend intelligence surface
5. Governance testing
6. Certification

Backend observation contracts should define deterministic object shapes only
after this taxonomy is accepted.

Observation builders should assemble observations from existing V1-V4 trusted
state without adding new decision logic.

The API layer should expose read-only observations and fail closed when trusted
evidence is incomplete or unsafe.

The frontend intelligence surface should display observations without layouts,
labels, ordering, or visual hierarchy that imply pitcher preference.

Governance testing should cover allowed language, forbidden language,
fail-closed states, trusted-source traceability, freshness limitations,
confidence limitations, explanation references, and no-ranking/no-selection
invariants.

Certification should prove that V5 remains observational, descriptive,
trust-aware, explainable, non-prescriptive, non-predictive, and derived only
from trusted platform state.

## Success Criteria

V5 Phase 2 is complete when:

- observation taxonomy is defined
- observation families are defined
- governance boundaries are documented
- allowed and prohibited language is documented
- fail-closed requirements are documented
- roadmap and status surfaces are synchronized
- no code changes are made

## Recommended V5 Phase 3 Milestone

Recommended next milestone:

```text
V5 Phase 3 - Bullpen Intelligence Surface Backend Observation Contracts
```

Phase 3 should define deterministic backend observation contracts without
building observation generators, API routes, frontend surfaces, database
changes, runtime behavior changes, ranking, selection, recommendation,
prediction, or pitcher advice.

## Final Boundary

This document authorizes V5 observation taxonomy only.

It does not authorize:

- backend implementation
- frontend implementation
- API contract changes
- database schema changes
- runtime behavior changes
- fatigue calculation changes
- availability calculation changes
- recommendation behavior changes
- readiness calculation changes
- explanation behavior changes
- trust logic changes
- freshness logic changes
- ranking behavior
- selection behavior
- recommendation behavior
- prediction behavior
- best-arm language
- closer/setup/role advice
- hidden priority ordering
- pitcher-level advice
- matchup advice
- automated decision-making
