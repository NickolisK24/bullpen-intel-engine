# BaseballOS V3 Phase 2 - Team Operations Bullpen Readiness Capability Definition

## Decision

Status:

```text
V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION_COMPLETE
```

Capability defined:

```text
TEAM_OPERATIONS_BULLPEN_READINESS
```

Recommended next milestone:

```text
BaseballOS V3 Phase 3 Team Operations Bullpen Readiness Implementation Plan
```

V3 Phase 2 defines Team Operations Bullpen Readiness as a governed
intelligence layer that summarizes the operational state of a bullpen from
existing BaseballOS workload, availability, freshness, trust, and roster
coverage evidence.

This phase is planning and documentation only. It does not implement runtime
behavior.

## Phase Purpose

The purpose of V3 Phase 2 is to define the Team Operations Bullpen Readiness
capability before implementation.

This definition answers:

```text
What may BaseballOS say about team bullpen readiness, what must it refuse to
say, what data may it use, what metadata must be visible, and how does it stay
non-ranking, non-selection, and non-predictive?
```

This phase converts the V3 Phase 1 product direction into a capability
contract that can be evaluated before any implementation work is authorized.

## Scope

In scope:

- Team Operations Bullpen Readiness capability definition
- user-facing purpose
- baseball operations purpose
- allowed inputs
- prohibited inputs
- allowed outputs
- prohibited outputs
- readiness concepts
- readiness status vocabulary
- constraint vocabulary
- coverage vocabulary
- workload vocabulary
- trust metadata requirements
- freshness metadata requirements
- refusal metadata requirements
- fail-closed requirements
- explainability requirements
- governance boundaries
- API contract planning
- frontend presentation planning
- testing requirements
- accessibility requirements
- certification requirements
- risks and mitigations
- non-goals
- recommended next milestone

Out of scope:

- implementation work
- runtime behavior changes
- backend logic changes
- frontend runtime changes
- API contract changes
- database schema changes
- fatigue formula changes
- recommendation logic changes
- lifecycle promotion
- production rollout
- ranking behavior
- selection behavior
- prediction behavior
- best option behavior
- preferred option behavior
- recommended option behavior

## Relationship To V2.5 Governance Closeout

V2.5 Phase 29 closed governance hardening and found BaseballOS ready to resume
product capability planning under existing governance gates.

V3 Phase 2 uses the V2.5 governance closeout as entry criteria:

- lifecycle movement still requires checklist review
- evidence packets remain required before production eligibility
- ownership, citation, retention, and test mapping remain required
- operational monitoring gaps remain non-blocking for planning only
- ranking, selection, prediction, and decision-language boundaries remain
  unchanged

V3 Phase 2 does not reopen V2.5 governance closeout. It uses that governance
system to define a future capability safely before implementation.

## Relationship To V3 Phase 1 Product Decision

V3 Phase 1 selected the next product direction:

```text
TEAM_OPERATIONS_BULLPEN_READINESS_PLANNING
```

V3 Phase 1 selected that direction because it had the strongest combination of
evidence fit, data availability, baseball operations value, portfolio value,
implementation feasibility, and governability.

V3 Phase 2 is the next planning layer. It defines the selected capability, but
it does not authorize implementation.

## Capability Definition

Team Operations Bullpen Readiness is a governed intelligence layer that
summarizes the operational state of a bullpen from trusted BaseballOS data.

It may describe:

- bullpen readiness state
- operational constraints
- workload pressure
- handedness coverage
- role or coverage inventory
- availability distribution
- freshness and trust limitations
- refusal conditions
- explainable contributing factors

It must not describe:

- which pitcher to use
- which pitcher is best
- which pitcher is preferred
- which pitcher is recommended
- which pitcher will perform best
- which pitcher will be selected by a team
- predicted game outcomes
- predicted injuries
- predicted saves
- predicted performance

The capability is team-level operations visibility. It is not an automated
pitching decision system.

## User-Facing Purpose

The user-facing purpose is to help a user understand the current bullpen
operational picture quickly and honestly.

The capability should help answer:

- Is the bullpen operationally stable, constrained, stressed, or unsupported by
  current data?
- How many pitchers are in each availability status?
- Where are workload constraints concentrated?
- Is there current left/right-handed coverage from public roster data?
- Does the current roster and workload evidence support a readiness summary?
- What freshness, trust, and data limitations qualify the summary?
- Why did BaseballOS summarize the bullpen this way?
- When must BaseballOS refuse to show a readiness summary?

The user remains responsible for the final baseball decision.

## Baseball Operations Purpose

The baseball operations purpose is to convert current bullpen workload and
availability evidence into an operational snapshot.

The capability should support review of:

- workload distribution
- constrained inventory
- fresh current availability counts
- active roster coverage
- handedness coverage
- position or role coverage from public roster fields
- bullpen stress signals based on public workload evidence
- missing, stale, or insufficient data limitations

The capability should not replace scouting, coaching, medical, travel,
clubhouse, opponent, or live game context.

## Allowed Inputs

Allowed inputs are limited to current BaseballOS public-data surfaces and
certified governance metadata.

Allowed data inputs:

| Input Area | Allowed Inputs |
|------------|----------------|
| Roster | `team_id`, `team_name`, `team_abbreviation`, active flag, pitcher name, pitcher id, MLB id. |
| Coverage | `position`, throwing hand, active pitcher count, available current pitcher count. |
| Fatigue | current fatigue score, fatigue risk tier, fatigue component evidence, calculated timestamp. |
| Workload | days since last appearance, appearances in recent windows, pitches in recent windows, innings in recent windows, last appearance date, last appearance pitch count. |
| Availability | availability status, confidence, data state, reasons, limitations, deterministic inputs. |
| Freshness | last successful sync, latest sync status, data-through date, latest workload date, latest fatigue calculation timestamp. |
| V2 governance metadata | ranking state, selection state, confidence, freshness, limitations, explanations, refusal reasons, fail-closed metadata. |
| Existing team context | certified V2 team bullpen context summaries and current team bullpen read surfaces. |

Allowed inputs must be documented, deterministic, and auditable.

## Prohibited Inputs

Prohibited inputs:

- injury reports
- transaction reports
- team-reported availability
- private clubhouse information
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
- prospect grades or development data
- unreviewed external feeds
- manually invented readiness overrides

If a future phase proposes one of these inputs, governance must reopen for data
source, metadata, failure-mode, refusal, test, and certification review.

## Allowed Outputs

Allowed outputs are descriptive team-level summaries.

Allowed output categories:

| Output Area | Allowed Output |
|-------------|----------------|
| Readiness state | One team-level readiness state with visible explanation and limitations. |
| Availability distribution | Counts by existing availability status. |
| Workload pressure | Summary of current workload compression or elevated workload counts. |
| Constraint summary | Counts and explanations for constrained, stale, missing, or low-confidence data. |
| Handedness coverage | Counts of left-handed and right-handed active pitchers when roster data is available. |
| Role or coverage inventory | Position-based coverage from public roster fields, with limitations if role detail is weak. |
| Freshness state | Data-through date, last successful sync, latest sync status, generated timestamp, and stale/missing limitations. |
| Trust state | Confidence, data state, source evidence state, governance state, limitations, explanations, and refusal reasons. |
| Refusal state | Explicit refusal when current data cannot support the readiness summary safely. |

Allowed outputs must be grouped, counted, summarized, or explained. They must
not order pitchers by preference or imply a final action.

## Prohibited Outputs

Prohibited outputs:

- pitcher rankings
- pitcher ordering by quality
- selected pitcher output
- final pitcher choice
- best pitcher output
- preferred pitcher output
- recommended pitcher output
- winner output
- score-ordered candidate lists
- hidden priority labels
- use-this-pitcher language
- game outcome prediction
- injury prediction
- save prediction
- performance prediction
- matchup advice
- team intent claims
- manager intent claims
- roster or transaction guidance
- unsupported baseball opinions
- visual layouts that imply first, second, or third choice

No output may tell the user who to use.

## Readiness Concepts

Readiness concepts are team-level and descriptive.

The capability may summarize:

- whether current data supports a readiness view
- whether workload constraints are low, moderate, or elevated
- whether availability distribution is balanced or constrained
- whether current coverage is limited by missing or stale data
- whether handedness coverage is visible from public roster data
- whether role or position coverage is visible from public roster data
- whether the capability must refuse because data is stale, missing, unsafe, or
  unsupported

Readiness concepts must not attach superiority, preference, or action guidance
to individual pitchers.

## Readiness Status Vocabulary

Approved readiness status vocabulary:

| Status | Meaning |
|--------|---------|
| Operationally Stable | Current public workload and freshness data support a low-constraint team-level readiness summary. |
| Operationally Constrained | Current public workload data shows meaningful constraints, but the summary remains supported by trusted data. |
| Operationally Stressed | Current public workload data shows elevated concentration of constrained or unavailable inventory. |
| Data Limited | Current data is stale, partial, low-confidence, or incomplete, so the readiness summary must be qualified. |
| Refused | Required data or governance conditions are missing, unsafe, or unsupported, so the readiness summary is withheld. |

Status labels must be presented as team-level state. They must not be applied
as pitcher recommendations.

## Constraint Vocabulary

Approved constraint vocabulary:

- workload constraint
- recent usage constraint
- availability constraint
- freshness constraint
- data coverage constraint
- confidence constraint
- roster coverage constraint
- handedness coverage constraint
- role coverage constraint
- explanation constraint
- governance constraint

Constraint language must explain why the team-level state is qualified. It
must not tell the user which pitcher to choose.

## Coverage Vocabulary

Approved coverage vocabulary:

- active bullpen count
- current workload-data count
- refreshed pitcher count
- left-handed coverage count
- right-handed coverage count
- position coverage count
- availability coverage count
- stale-data count
- missing-data count
- low-confidence count
- coverage limitation

Coverage vocabulary must use counts, distributions, and limitations. It must
not create depth charts, pecking order, preference lists, or role certainty
that current data does not support.

## Workload Vocabulary

Approved workload vocabulary:

- workload pressure
- recent workload concentration
- appearance compression
- multi-day pitch load
- rest buffer
- elevated workload
- heavy recent workload
- constrained recent workload
- limited current workload evidence
- stale workload evidence
- missing workload evidence

Workload vocabulary must remain tied to public game-log and fatigue evidence.
It must not become injury, performance, or availability-from-team reporting.

## Trust Metadata Requirements

Any future implementation must expose trust metadata for the readiness output.

Required trust metadata:

- confidence
- confidence reasons
- data state
- source evidence state
- governance state
- limitations
- explanations
- refusal reasons
- generated timestamp
- `ranking_applied`
- `selection_made`

Trust metadata must be visible enough for the user to know whether the
readiness summary is supported, limited, or refused.

## Freshness Metadata Requirements

Freshness metadata is mandatory.

Required freshness metadata:

- data-through date
- latest workload date
- last successful sync
- latest sync status
- latest fatigue calculation timestamp
- generated timestamp
- stale-data indicator
- missing-data indicator
- freshness limitations

A sync timestamp must not substitute for the baseball data-through date.
Stale, missing, failed, historical, or unknown data must reduce confidence,
qualify the summary, or trigger refusal.

## Refusal Metadata Requirements

Refusal metadata is mandatory when the capability withholds or downgrades a
readiness output.

Required refusal metadata:

- refusal state
- refusal reason code
- human-readable refusal explanation
- affected output area
- missing or unsafe evidence
- freshness state
- confidence state
- limitations
- recovery or review note when available

Refusal is a valid product outcome. The system should refuse rather than fill
data gaps with unsupported baseball logic.

## Fail-Closed Requirements

The capability must fail closed when:

- required team or bullpen data is missing
- current workload data is stale beyond the accepted freshness window
- fatigue or availability evidence is unavailable for enough pitchers that a
  team-level summary would be misleading
- trust metadata is absent
- freshness metadata is absent
- refusal metadata is required but absent
- forbidden ranking or selection fields appear
- predictive fields appear
- prohibited best, preferred, or recommended behavior appears
- source data includes unsupported private or unreviewed inputs
- confidence is too low to support a readiness summary

Fail-closed behavior may return a refused state, a data-limited state, or an
unavailable capability state. It must not return an unsafe readiness summary.

## Explainability Requirements

Every readiness output must explain:

- what state was assigned
- which data supported the state
- which constraints contributed
- which coverage counts matter
- which workload signals matter
- which freshness state applies
- which trust limitations apply
- whether any refusal or fail-closed condition occurred

Explanations must be attached to the output they qualify. Static methodology
language is not enough for this capability.

## Governance Boundaries

The certified governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

V3 Phase 2 explicitly reaffirms:

- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best option behavior exists
- no preferred option behavior exists
- no recommended option behavior exists

Governance boundaries:

- BaseballOS may summarize team-level readiness.
- BaseballOS may count and explain constraints.
- BaseballOS may expose coverage and freshness limitations.
- BaseballOS may refuse unsupported readiness output.
- BaseballOS must not rank pitchers.
- BaseballOS must not select pitchers.
- BaseballOS must not predict outcomes.
- BaseballOS must not identify a best, preferred, or recommended pitcher.
- The user remains the decision maker.

## API Contract Planning

Future API planning should define a new contract only after this capability
definition is accepted.

API planning must decide:

- whether to extend the existing certified V2 bullpen-state endpoint or define
  a separate V3 endpoint
- required request parameters
- required response metadata
- readiness state shape
- availability distribution shape
- workload pressure shape
- handedness coverage shape
- role or coverage inventory shape
- constraint summary shape
- explanation shape
- limitation shape
- refusal shape
- fail-closed shape
- forbidden field checks
- backward compatibility boundaries

This phase does not approve any API contract or endpoint.

## Frontend Presentation Planning

Frontend presentation planning must preserve neutral team-level visibility.

Future UI planning should define:

- where the readiness surface appears
- whether it belongs on Dashboard, Bullpen, or both
- how readiness state is summarized
- how distributions and counts are displayed
- how constraints are grouped
- how explanations are attached
- how limitations and refusal states are shown
- how freshness and trust metadata remain visible
- how mobile and desktop layouts avoid dense or misleading presentation
- how visual hierarchy avoids hidden ranking

UI must avoid numbered pitcher lists, leaderboard layouts, first-choice
language, and any styling that makes one pitcher look selected.

## Testing Requirements

Future implementation must include tests for:

- allowed readiness states
- refusal states
- data-limited states
- stale data behavior
- missing data behavior
- low-confidence behavior
- trust metadata presence
- freshness metadata presence
- refusal metadata presence
- fail-closed behavior
- forbidden ranking fields
- forbidden selection fields
- forbidden prediction fields
- forbidden best, preferred, or recommended fields
- allowed coverage counts
- handedness coverage from roster data
- workload pressure explanation
- availability distribution rendering
- frontend prohibited-language checks
- accessibility labels and relationships
- V1 and V2 regression safety

Testing must prove boundaries as well as successful output.

## Accessibility Requirements

Accessibility requirements:

- readiness state must have a clear accessible label
- trust and freshness metadata must be reachable by keyboard and screen reader
- refusal state must be announced as a valid state, not as a hidden error
- counts and distributions must have text equivalents
- color must not be the only signal for readiness or constraint state
- expanded details must preserve focus order
- mobile layout must keep metadata and limitations readable
- status vocabulary must be concise and understandable

Accessibility review is required before production eligibility.

## Certification Requirements

Before production eligibility, the capability must complete certification
review proving:

- allowed inputs are documented and used
- prohibited inputs are absent
- allowed outputs are deterministic and explainable
- prohibited outputs are absent
- trust metadata is present
- freshness metadata is present
- refusal metadata is present
- fail-closed behavior works
- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best, preferred, or recommended behavior exists
- API contract tests pass if an API is added
- frontend rendering tests pass if UI is added
- accessibility review is complete
- lifecycle evidence packet is updated
- rollout review is complete if production release is requested

Certification must be completed before the capability is described as
production-ready.

## Risks And Mitigations

| Risk | Mitigation |
|------|------------|
| Readiness state is mistaken for pitcher guidance | Keep readiness team-level, attach limitations, and prohibit pitcher choice language. |
| Coverage inventory becomes a hidden depth chart | Use counts and neutral grouping only; avoid ordered pitcher lists. |
| Handedness coverage is overinterpreted | Present handedness as roster coverage count only, not matchup guidance. |
| Role coverage implies unsupported team roles | Limit role vocabulary to current roster position unless future role data is governed. |
| Workload pressure becomes injury prediction | Preserve public workload limitation text and prohibit medical inference. |
| Freshness metadata is hidden | Require data-through, sync, generated-at, and stale/missing indicators. |
| Missing data produces unsafe summary | Fail closed or mark Data Limited with visible refusal/limitation evidence. |
| Future API expansion bypasses V2 boundaries | Require contract planning, forbidden field checks, and certification review. |
| UI density weakens trust | Use summary-first presentation with visible expansion and metadata anchors. |

## Non-Goals

V3 Phase 2 does not authorize:

- implementation work
- runtime behavior changes
- API contract changes
- frontend behavior changes
- recommendation logic changes
- fatigue formula changes
- database schema changes
- lifecycle promotion
- production rollout
- pitcher ranking
- pitcher ordering by quality
- pitcher selection
- pitcher recommendation
- game outcome prediction
- injury prediction
- save prediction
- performance prediction
- matchup advice
- team intent inference
- manager intent inference
- private data integration
- Prospect Pipeline promotion
- Game Context Intelligence implementation

## Validation

Validation required for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-2-readiness-definition
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

Root `npm test` is not required for V3 Phase 2. If no root `package.json`
exists, that is expected and is not a project failure.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 3 Team Operations Bullpen Readiness Implementation Plan
```

The next milestone should remain planning-only unless implementation is
explicitly authorized. It should translate this capability definition into an
implementation plan with proposed surfaces, API contract options, frontend
presentation options, test plan, lifecycle evidence requirements, and
certification gates.
