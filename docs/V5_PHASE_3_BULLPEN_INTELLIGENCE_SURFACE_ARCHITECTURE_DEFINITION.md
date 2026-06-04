# BaseballOS V5 Phase 3 - Bullpen Intelligence Surface Architecture Definition

## Phase Status

Phase status:

```text
V5_PHASE_3_BULLPEN_INTELLIGENCE_SURFACE_ARCHITECTURE_DEFINITION_APPROVED
```

Certification roadmap status:

```text
V5_PHASE_3_ARCHITECTURE_APPROVED
```

Capability track:

```text
V5_BULLPEN_INTELLIGENCE_SURFACE
```

Implementation status:

```text
PLANNING_ONLY
```

V5 Phase 3 approves only the Bullpen Intelligence Surface architecture
definition. It defines the intended observation lifecycle, domain architecture,
builder architecture, evidence architecture, trust architecture, severity
architecture, fail-closed architecture, frontend surface architecture, and
governance protection layer before implementation begins.

This phase does not authorize backend code, frontend code, APIs, schemas,
database changes, tests, runtime behavior changes, ranking behavior, selection
behavior, recommendation behavior, prediction behavior, pitcher advice, matchup
advice, or automated decision-making.

## 1. Architecture Purpose

The Bullpen Intelligence Surface architecture defines how existing trusted
BaseballOS state may eventually become governed observations without creating a
new decision system.

The architecture separates five responsibilities:

1. Trusted platform state remains the source of truth.
2. Observation builders transform supported state into descriptive statements.
3. Evidence references preserve traceability to the source state.
4. Trust, freshness, confidence, and limitation metadata qualify the statement.
5. Frontend surfaces display observations without ranking, selection,
   recommendation, prediction, or advice.

The architecture exists to make V5 observation surfacing deterministic,
explainable, suppressible, and governable. It does not change availability
classification, readiness calculation, workload pressure calculation,
freshness logic, trust logic, explanation behavior, or any Recommendation
Engine behavior.

Required preserved governance flags:

```text
ranking_applied === false
selection_made === false
```

## 2. Observation Lifecycle

The governed observation lifecycle is:

```text
Trusted Platform State
-> Observation Builder
-> Governed Observation
-> Explanation Layer
-> Frontend Intelligence Surface
```

Lifecycle responsibilities:

| Stage | Responsibility | Governance boundary |
| --- | --- | --- |
| Trusted Platform State | Existing V1-V4 outputs, freshness metadata, trust metadata, limitations, refusal state, fail-closed state, and certification records. | No new source authority is created. |
| Observation Builder | Deterministically evaluates whether a supported observation can be assembled from trusted state. | Builders may describe state but may not rank, select, recommend, predict, or advise. |
| Governed Observation | Carries type, severity, title, summary, evidence, freshness, confidence, limitations, explanation reference, and governance metadata. | Output remains observational, descriptive, trust-aware, explainable, non-prescriptive, and non-predictive. |
| Explanation Layer | Provides or references supporting V4 or source explanation evidence. | Observations without required explanation support fail closed. |
| Frontend Intelligence Surface | Displays observations, limitations, freshness, confidence, and explanation access. | UI hierarchy must not imply pitcher preference, usage priority, or decision automation. |

Any lifecycle stage may suppress an observation when source evidence, freshness,
confidence, trust metadata, or explanation support is unsafe or incomplete.

## 3. Observation Domain Architecture

Future V5 domain objects should be deterministic logical contracts, not new
decision engines.

Expected domain concepts:

| Concept | Purpose | Governance requirement |
| --- | --- | --- |
| BullpenObservation | A single descriptive observation derived from trusted platform state. | Must include governance metadata and must not contain ranking, selection, recommendation, prediction, matchup, or pitcher-usage fields. |
| ObservationType | Controlled vocabulary matching the authorized Phase 2 observation families. | Unknown or unsupported types fail closed. |
| ObservationSeverity | Controlled display severity for surfacing state importance. | Severity is not pitcher rank, pitcher priority, or usage advice. |
| ObservationEvidence | Traceable source references supporting the observation. | Evidence must point to existing trusted BaseballOS state. |
| ObservationLimitation | Freshness, confidence, data-state, trust, refusal, or source limitation visible to the user. | Limitations must not be hidden when they qualify an observation. |
| ObservationCollection | A bounded set of governed observations for a snapshot or request. | Empty, unsafe, unsupported, or incomplete collections must fail closed instead of inventing intelligence. |

Authorized observation types should remain aligned to the Phase 2 taxonomy:

- inventory
- readiness
- workload pressure
- constraints
- freshness
- trust
- availability movement
- snapshot change

Future domain contracts may define field names, serialization details, and
validation helpers only in an authorized implementation phase.

## 4. Observation Builder Architecture

Observation builders should be deterministic, source-bounded, and side-effect
free. They should read existing trusted state, decide whether a supported
observation can be assembled, attach evidence and limitations, and return a
governed observation or a suppressed/fail-closed result.

Expected builder families:

| Builder family | Allowed source state | Allowed output |
| --- | --- | --- |
| Inventory builder | Current bullpen inventory counts, availability distribution counts, roster coverage, existing V2/V3 inventory metadata. | Inventory expansion, contraction, coverage, or data-limited observations. |
| Readiness builder | V3 Team Operations Readiness state, readiness constraints, readiness confidence, freshness, limitations, and explanation references. | Current readiness, readiness degradation, readiness limitation, or refusal observations. |
| Workload pressure builder | Existing fatigue state, workload pressure signals, recent usage compression, rest buffers, and workload explanations. | Grouped workload pressure and workload limitation observations. |
| Constraint builder | Availability, readiness, workload, roster coverage, confidence, freshness, explanation, refusal, and fail-closed constraints. | Constraint summary and limitation observations. |
| Freshness builder | Data-through date, latest workload date, last successful sync, sync status, generated timestamp, stale-data indicators, missing-data indicators, and freshness protection metadata. | Freshness protection, stale-data, sync, and missing-freshness observations. |
| Trust builder | Confidence metadata, trust metadata, source evidence state, governance metadata, limitations, refusal reasons, fail-closed state, and explanation references. | Trust warning, confidence limitation, source evidence limitation, and suppression observations. |
| Availability movement builder | Current and previous trusted availability distributions, comparable status vocabularies, snapshot timestamps, freshness metadata, and confidence metadata. | Availability expansion, contraction, bucket movement, no-material-change, or movement-unavailable observations. |
| Snapshot change builder | Current and previous trusted platform snapshots, inventory counts, readiness state, workload pressure state, freshness state, trust state, and explanation references. | Snapshot changed, unchanged, changed-area, or change-unavailable observations. |

Builder rules:

- Builders may not sort pitchers into preferred order.
- Builders may not select pitchers.
- Builders may not recommend pitchers.
- Builders may not predict outcomes.
- Builders may not infer manager intent.
- Builders may not introduce external source authority.
- Builders may not raise observation trust above the source trust.
- Builders must suppress unsupported, stale, low-confidence, unexplained, or
  unsafe observations.

## 5. Evidence Architecture

Every surfaced observation must be traceable to existing trusted BaseballOS
state.

Evidence responsibilities:

- identify the source platform area
- reference the relevant snapshot, payload, or explanation evidence
- expose generated time and data-through or workload dates when applicable
- preserve freshness and confidence context
- record limitation or refusal reasons when data is degraded
- support explanation access for each observation type
- prove that the observation was derived from allowed V1-V4 state

Evidence may reference:

- V1 Availability Engine classifications and explanation metadata
- V2 governed bullpen-state metadata with ranking and selection disabled
- V3 Team Operations Readiness summaries and constraints
- existing fatigue and workload pressure signals
- existing freshness, sync, confidence, trust, refusal, and fail-closed metadata
- certified V4 explanation references
- governance certification records
- current and previous trusted platform snapshots

Unsupported evidence conditions must suppress the observation. V5 must not fill
missing evidence with baseball assumptions, private data inference, matchup
models, performance projections, or unreviewed external feeds.

## 6. Trust Architecture

V5 trust is inherited from source state. An observation may never be more
trusted, fresher, or more confident than the weakest required source evidence
supporting it.

Trust responsibilities:

- preserve source freshness status
- preserve source confidence status
- preserve source trust status
- preserve source limitations
- surface stale, missing, refused, low-confidence, or fail-closed states
- attach explanation support when required
- suppress observations when trust state is absent or unsafe

Trust states should distinguish:

- supported
- limited
- data limited
- stale
- missing
- refused
- fail-closed
- unsupported

When trust is limited, the limitation must be visible with the observation. V5
must not present stale, missing, incomplete, or low-confidence data as fully
current or fully supported.

## 7. Severity Architecture

Observation severity is a display qualifier for descriptive state, not a rank,
priority list, recommendation, or action queue.

Allowed severity vocabulary:

| Severity | Meaning | Example pattern |
| --- | --- | --- |
| Informational | State is present and safely descriptive. | `Inventory unchanged.` |
| Monitor | State merits visibility because evidence shows a notable condition or limitation. | `Freshness protection is active.` |
| Elevated | Evidence shows increased pressure, contraction, degradation, or limitation. | `Workload pressure is elevated across the current bullpen inventory.` |
| Significant | Evidence shows a material limitation, fail-closed state, or broad degraded support. | `Observation support is unavailable because required source evidence is incomplete.` |

Severity rules:

- Severity may order display groups, not pitchers.
- Severity may not imply what a user should do.
- Severity may not imply which pitcher is better, safer, preferred, or selected.
- Severity may not replace confidence, freshness, evidence, or limitation
  metadata.
- Unsupported severity assignments must fail closed.

## 8. Fail-Closed Architecture

Fail-closed behavior is a first-class V5 outcome.

Observations must be suppressed or returned as refused/data-limited when:

- required source evidence is missing
- required freshness metadata is missing
- required trust metadata is missing
- confidence is insufficient without visible limitation text
- explanation support is unavailable for the observation type
- current and previous snapshots are missing or not comparable
- timestamp ordering is unclear
- source state is stale beyond accepted freshness boundaries
- required governance flags are absent
- unsupported external data appears
- observation text would imply ranking, selection, recommendation, prediction,
  matchup advice, role advice, pitcher advice, or automated decision-making

Fail-closed outputs may include:

- no observations
- suppressed observation count
- suppression reason
- data-limited state
- refused observation state
- freshness limitation
- confidence limitation
- explanation-unavailable limitation

Fail-closed outputs must not invent replacement observations.

## 9. Frontend Surface Architecture

Future frontend intelligence surfaces should display governed observations as a
read-only intelligence panel or dashboard section.

Expected display responsibilities:

- group observations by allowed observation family
- show title, summary, severity, freshness, confidence, limitations, and
  explanation access
- make stale, missing, refused, suppressed, or fail-closed states visible
- support empty states without inventing intelligence
- preserve compact governance metadata when needed
- avoid visual hierarchy that implies pitcher preference or a decision

Frontend presentation must not introduce:

- pitcher rankings
- pitcher selections
- pitcher recommendations
- best-arm language
- closer/setup/role advice
- matchup advice
- prediction claims
- action prompts that tell a user what to do
- hidden priority ordering

This phase does not authorize frontend implementation.

## 10. Governance Protection Layer

The V5 governance protection layer should guard observation generation and
presentation against recommendation drift.

Required protections:

- preserve `ranking_applied === false`
- preserve `selection_made === false`
- block ranking fields
- block selected-pitcher fields
- block recommended-pitcher fields
- block prediction fields
- block matchup-advice fields
- block hidden priority fields
- block role-advice fields
- validate allowed observation types
- validate required evidence
- validate freshness and confidence visibility
- validate explanation support
- fail closed on unsafe or unsupported states
- test allowed and forbidden observation language before certification

The governance layer must protect both the future builder path and the future
presentation path. A safe backend observation can still become unsafe if a UI
label, grouping, ordering, or empty-state message implies advice or a decision.

## 11. Phase 4 Boundary

Recommended next milestone:

```text
V5 Phase 4 - Observation Domain And Contracts
```

Expected Phase 4 authorization request:

```text
V5_PHASE_4_OBSERVATION_DOMAIN_AND_CONTRACTS
```

Phase 4 should define backend observation domain contracts, controlled
vocabularies, validation expectations, serialization expectations, suppression
states, and contract-level governance checks. Phase 4 should not build
observation generators, expose API routes, implement frontend surfaces, add
database migrations, change runtime behavior, rank pitchers, select pitchers,
recommend pitchers, predict outcomes, provide matchup advice, provide role
advice, or automate decisions unless a later authorization explicitly changes
that boundary.

## V5 Phase 4 Follow-Up

V5 Phase 4 has completed the backend observation domain and contract
foundation:

- `docs/V5_PHASE_4_OBSERVATION_DOMAIN_AND_CONTRACTS.md`

Phase 4 implements governed observation enum vocabularies, dataclass contracts,
serialization helpers, contract validators, prohibited-language safeguards,
collection serialization, and focused backend tests.

This follow-up does not authorize observation builders, API routes, frontend
UI, database migrations, runtime observation generation, ranking, selection,
prediction, matchup advice, pitcher advice, or automated decision-making.

## Success Criteria

V5 Phase 3 is complete when:

- architecture purpose is defined
- observation lifecycle is defined
- observation domain architecture is defined
- observation builder architecture is defined
- evidence architecture is defined
- trust architecture is defined
- severity architecture is defined
- fail-closed architecture is defined
- frontend surface architecture is defined
- governance protection layer is defined
- Phase 4 boundary is defined
- roadmap and status surfaces are synchronized
- no code changes are made

## Final Boundary

This document authorizes V5 architecture definition only.

It does not authorize:

- backend implementation
- frontend implementation
- API contract changes
- database schema changes
- runtime behavior changes
- tests
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
