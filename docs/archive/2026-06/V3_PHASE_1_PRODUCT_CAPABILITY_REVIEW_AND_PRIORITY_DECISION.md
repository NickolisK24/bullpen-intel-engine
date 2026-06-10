# BaseballOS V3 Phase 1 - Product Capability Review and Priority Decision

## Decision

Status:

```text
V3_PHASE_1_PRODUCT_CAPABILITY_REVIEW_AND_PRIORITY_DECISION_COMPLETE
```

Recommended product direction:

```text
TEAM_OPERATIONS_BULLPEN_READINESS_PLANNING
```

Recommended next milestone:

```text
BaseballOS V3 Phase 2 Team Operations Bullpen Readiness Capability Definition
```

Phase 1 recommends a constrained Team Operations Intelligence direction focused
on bullpen readiness, workload distribution, availability distribution, and
team-level stress visibility. The recommendation is not a ranking, selection,
prediction, or automated decision system. It is a planning decision only.

## Phase Purpose

The purpose of V3 Phase 1 is to review BaseballOS after V2.5 governance
closeout and decide the best next product capability direction from current
evidence.

This phase is neutral by design. It does not assume that the next direction is
Prospect Pipeline, Bullpen Intelligence V3, Recommendation Engine expansion,
Team Operations Intelligence, Game Context Intelligence, or any other product
path before reviewing the current program state.

The review question is:

```text
What product capability should BaseballOS plan next, based on evidence,
current strengths, known gaps, data availability, governance risk,
implementation risk, portfolio value, and baseball operations value?
```

## Scope

In scope:

- current certified production capabilities
- prototype, experimental, and legacy surface review
- Recommendation Engine V1 and V2 gap assessment
- Availability Engine gap assessment
- Dashboard and Bullpen Intelligence gap assessment
- Prospect Pipeline assessment
- Team Operations Intelligence assessment
- Game Context Intelligence assessment
- additional product paths discovered from repository and documentation review
- comparative option matrix
- implementation, governance, data, portfolio, and baseball operations review
- recommended next product direction
- explicit non-goals
- recommended next milestone

Out of scope:

- runtime behavior changes
- recommendation logic changes
- fatigue formula changes
- API contract changes
- frontend runtime behavior changes
- feature implementation
- production scope expansion
- lifecycle promotion
- prototype promotion
- ranking behavior
- selection behavior
- prediction behavior
- best option behavior
- preferred option behavior
- recommended option behavior

## Current BaseballOS Product State

BaseballOS is currently a trust-first bullpen intelligence platform focused on
public workload data, fatigue transparency, availability visibility,
freshness-aware decision support, and governed recommendation boundaries.

The completed platform foundation includes:

- MLB Stats API roster and pitching game-log ingestion
- deterministic fatigue scoring
- Availability Engine V1
- dashboard freshness and coverage transparency
- durable sync metadata
- bullpen and pitcher detail workflows
- team bullpen views
- Methodology reference surface
- Recommendation Engine V1 candidate-level evaluation
- certified Recommendation Engine V2 bullpen-state intelligence
- lifecycle governance, evidence governance, ownership, citation mapping, and
  stewardship closeout

V2.5 Phase 29 closed governance hardening and authorized V3 product capability
planning only. It did not authorize V3 implementation.

## Current Certified Production Capabilities

Current certified and accepted production capabilities include:

| Capability | Current Status | Evidence |
|------------|----------------|----------|
| Dashboard | Production | Phase 19 surface inventory; README; project state. |
| Bullpen | Production | Phase 19 surface inventory; README; project state. |
| Fatigue Engine | Production foundation | README; project state; backend tests. |
| Availability Engine V1 | Complete production foundation | `docs/BULLPEN_AVAILABILITY_ENGINE_V1.md`; project state. |
| Recommendation Engine V1 candidate API and panel | Certified / Production Ready | `docs/RECOMMENDATION_ENGINE_V1_COMPLETION_CERTIFICATION.md`. |
| Recommendation Engine V2 bullpen-state API | Certified / Production Ready | `docs/RECOMMENDATION_ENGINE_V2_FORMAL_CERTIFICATION.md`; Phase 16 rollout decision. |
| Dashboard V2 Bullpen State panel | Certified / Production Ready | V2 formal certification; Phase 16 rollout decision; Phase 17 monitoring review. |
| Bullpen fatigue APIs and read APIs | Production | Phase 19 surface inventory. |
| Freshness and sync visibility | Production foundation | README; project state; sync metadata reports. |

The certified V2 production scope remains:

```text
GET /api/recommendations/v2/bullpen-state
Dashboard V2 Bullpen State panel
```

## Current Prototype, Experimental, And Legacy Surfaces

Current non-production surfaces from the lifecycle inventory:

| Surface | Classification | Current Finding |
|---------|----------------|-----------------|
| Prospect Pipeline UI | Prototype | Uses illustrative sample data and lacks promotion evidence. |
| Prospect APIs | Prototype | Uses prototype prospect data and lacks trust, freshness, refusal, and fail-closed metadata. |
| Dashboard Pipeline Snapshot | Prototype | Preview only; not a live prospect data product. |
| Fatigue-to-ERA insight | Experimental | Exploratory and correlational; not a prediction. |
| Latest-workload snapshot mode | Experimental | Validation/admin mode; not current availability. |
| MLB passthrough helpers | Experimental | Source helpers without full BaseballOS trust/freshness envelope. |
| Threshold experimentation tooling | Experimental | Offline governance tooling, not runtime product behavior. |
| Metadata-less fatigue array response | Legacy | Compatibility shape without metadata envelope. |
| Standalone recalculation script | Legacy | Older maintenance path retained beside supported admin endpoint. |

Phase 25 classified the current production evidence packets as ready for
stewardship review, but found no prototype, experimental, or legacy surface
ready for lifecycle movement.

## Current Intelligence Gaps

Current intelligence gaps:

- no injury, transaction, news, team-reported availability, warm-up, travel, or
  manager-intent feed
- no Statcast, Hawk-Eye, Stuff+, pitch-quality, or biomechanics model
- limited role-aware starter/reliever handling
- no game context, leverage, inning, score, matchup, or opponent-quality layer
- no real minor-league prospect feed or defensible prospect grade/ETA source
- no runtime telemetry evidence retained for production monitoring artifacts
- no production expansion beyond the certified V2 bullpen-state scope
- no ranking, ordering, final pitcher selection, or predictive decision layer

These gaps should guide V3 planning away from unsupported claims and toward
capabilities that can be supported by current data.

## Recommendation Engine V1/V2 Gap Assessment

Recommendation Engine V1 is certified for one-candidate evaluation. It is
valuable because it connects availability, freshness, confidence,
explanations, limitations, and refusal into a user-triggered decision-support
surface. Its main gap is scope: it evaluates one pitcher at a time and does not
summarize the bullpen as an operations unit.

Recommendation Engine V2 is certified for governed bullpen-state intelligence.
It adds neutral intelligence, inventory visibility, team bullpen context, trust
metadata, freshness metadata, refusal metadata, and fail-closed behavior. Its
main gap is product focus: it has strong internal and dashboard evidence, but
future product direction still needs to decide which capability should be
planned next.

Recommendation expansion options remain sensitive because any movement toward
preference, ordering, or final action increases governance risk. A V3 direction
should use V2 evidence and team context without converting neutral grouping
into ranking or selection.

## Availability Engine Gap Assessment

Availability Engine V1 is a strong product foundation. It is deterministic,
explainable, tested, and integrated into current dashboard, bullpen, and
pitcher detail surfaces.

Availability gaps:

- role-aware starter/reliever handling remains limited
- public workload data cannot prove injury, illness, team availability, travel,
  warm-up activity, or manager intent
- latest-workload snapshot mode is validation-only
- metadata-less fatigue output remains legacy
- availability labels answer individual and team state, but not yet a complete
  operations-readiness workflow

Availability Engine V1 is a good base for V3 because it already has
governance, data availability, tests, and user-facing value. The next product
direction should reuse it rather than bypass it.

## Dashboard/Bullpen Intelligence Gap Assessment

Dashboard and Bullpen are the flagship user-facing surfaces. They already show
fatigue, availability, sync freshness, pitcher detail, team bullpen context,
Recommendation Engine V1 candidate evaluation, and V2 bullpen-state
intelligence.

Gaps:

- current dashboard intelligence is dense and mostly evidence-oriented rather
  than workflow-oriented
- current team bullpen views expose useful workload state, but do not yet frame
  a team operations readiness review as a product workflow
- no retained operational monitoring artifact exists
- no V3 capability has been selected for planning

The Dashboard and Bullpen surfaces provide the strongest implementation base
for the next phase because they already contain the certified data and trust
patterns needed for a useful V3 product direction.

## Prospect Pipeline Assessment

Prospect Pipeline has visible portfolio value because it broadens BaseballOS
beyond bullpen workload and shows a player-development concept. It has real UI
and API paths:

- `/prospects`
- `/api/prospects/*`
- `frontend/src/components/prospects/`
- `backend/api/prospects.py`
- `backend/models/prospect.py`

However, current evidence strongly limits readiness:

- it uses illustrative, hand-entered sample players
- it is explicitly labeled as a prototype
- it lacks a live minor-league data feed
- it lacks trust, freshness, refusal, and fail-closed metadata
- it uses grade ordering that would need governance before production
- Phase 25 assigns it `BACKFILL_REQUIRED`, not promotion readiness

Prospect Pipeline should not be the first V3 implementation direction. It
should remain a future backfill candidate until evidence, owner, data source,
metadata, and lifecycle review gaps are closed.

## Team Operations Intelligence Assessment

Team Operations Intelligence is the strongest next planning direction if it is
constrained to bullpen readiness and workload operations.

Evidence supporting this path:

- current production data already includes fatigue, availability, freshness,
  sync status, team bullpen views, and team context
- V2 Phase 5 implemented team bullpen context
- V2 certification already protects trust, freshness, refusal, fail-closed,
  anti-ranking, and anti-selection behavior
- current BaseballOS identity is centered on bullpen workload and availability
- the user-facing value is clearer than another governance-only milestone
- the baseball operations value is stronger than UI polish alone

Allowed planning scope should include:

- team bullpen readiness summaries
- workload distribution visibility
- constrained bullpen stress visibility
- resource-group counts when criteria are documented
- freshness-aware refusal when current data cannot support the view
- operating context that helps a user inspect constraints before a human
  decision

This path must not include ranking, selection, prediction, matchup advice,
manager-intent inference, or final pitcher guidance.

## Game Context Intelligence Assessment

Game Context Intelligence has high baseball operations value but is not the
best immediate direction.

Potential value:

- score, inning, leverage, opponent, and matchup context would make bullpen
  planning more realistic
- it could eventually support game-aware operations workflows

Current blockers:

- current stored data is workload and game-log centric, not live game-state
  centric
- leverage and matchup context can create prediction or preference pressure
- additional contracts, data sources, freshness semantics, and refusal behavior
  would be needed
- governance risk is materially higher than team readiness planning

Game Context Intelligence should remain a later planning candidate after a
team operations readiness capability is defined and the data-source plan is
clear.

## Additional Product Paths Discovered

Additional paths discovered during repository and documentation review:

| Path | Evidence | Assessment |
|------|----------|------------|
| Bullpen Intelligence V3 workflow polish | Dashboard and Bullpen are mature surfaces. | Valuable, but should be tied to a clearer operations-readiness capability rather than standalone UI polish. |
| Recommendation Engine expansion | V1 and V2 are certified within strict boundaries. | High risk if it moves toward preference language; useful only as a governed support layer for the selected product direction. |
| Availability Engine role-aware refinement | Known limitation in project state. | Valuable, but it changes classification behavior and should follow a scoped policy phase if chosen. |
| Operational monitoring artifact capture | Phase 28 and Phase 29 classify artifact capture as non-blocking gap. | Useful governance maintenance, but not a product capability direction. |
| Legacy cleanup | Metadata-less fatigue response and standalone recalculation script are legacy. | Maintainability value, low portfolio and user-facing value. |
| Reports, exports, or documented API platform | README lists these as future direction. | Useful later, but less directly tied to current certified intelligence value. |
| Real prospect ingestion | README lists it as future direction. | High portfolio value, but data provenance and lifecycle readiness are currently weak. |

## Evaluation Criteria

The review uses these criteria:

| Criterion | Meaning |
|-----------|---------|
| Evidence fit | How well current docs, tests, data, and production surfaces support the path. |
| User-facing value | Whether the capability would make BaseballOS more useful to a reviewer or operator. |
| Baseball operations value | Whether it answers a meaningful baseball operations question. |
| Data availability | Whether current data can support the capability without unsupported claims. |
| Implementation risk | Whether the likely future implementation can be scoped safely. |
| Governance risk | Whether the path can preserve current trust boundaries. |
| Maintainability | Whether the path fits existing architecture and evidence process. |
| Portfolio value | Whether the path improves the demonstrated product narrative. |

Scores use a 1-5 scale where 5 is strongest or lowest risk.

## Comparative Option Matrix

| Option | Evidence Fit | User Value | Baseball Ops Value | Data Availability | Implementation Risk | Governance Risk | Maintainability | Portfolio Value | Total |
|--------|--------------|------------|--------------------|-------------------|---------------------|-----------------|-----------------|-----------------|-------|
| Team operations bullpen readiness | 5 | 5 | 5 | 5 | 4 | 4 | 4 | 5 | 38 |
| Bullpen Intelligence V3 workflow polish | 5 | 4 | 4 | 5 | 4 | 5 | 5 | 4 | 37 |
| Availability Engine role-aware refinement | 4 | 4 | 5 | 4 | 3 | 4 | 4 | 4 | 34 |
| Governed recommendation expansion | 4 | 4 | 4 | 4 | 3 | 2 | 3 | 4 | 30 |
| Operational monitoring artifact capture | 5 | 2 | 2 | 4 | 4 | 5 | 4 | 2 | 30 |
| Legacy cleanup and deprecation planning | 3 | 2 | 2 | 5 | 4 | 4 | 5 | 2 | 30 |
| Prospect Pipeline evidence and data backfill | 2 | 4 | 3 | 1 | 2 | 2 | 2 | 5 | 21 |
| Game Context Intelligence | 2 | 5 | 5 | 2 | 2 | 1 | 2 | 5 | 24 |

The matrix does not mean Team Operations Intelligence is already approved for
implementation. It means the best next planning direction is to define a
constrained team operations readiness capability because it has the strongest
combination of evidence fit, operations value, data availability, and portfolio
value.

## Implementation Risk Assessment

Implementation risk by option:

| Option | Risk | Rationale |
|--------|------|-----------|
| Team operations bullpen readiness | Moderate | Can reuse current production surfaces and data, but must define a new workflow carefully. |
| Bullpen Intelligence V3 workflow polish | Low to moderate | Uses existing surfaces, but may not add enough product depth without a clearer capability. |
| Availability Engine role-aware refinement | Moderate | Could change classification semantics and tests. |
| Governed recommendation expansion | High | Easy to drift into preference or decision language. |
| Prospect Pipeline | High | Requires real data-source and metadata foundation. |
| Game Context Intelligence | High | Requires new data, contracts, and governance around game state and matchup context. |
| Operational monitoring artifact capture | Low | Mostly governance/ops work, but not a product direction. |
| Legacy cleanup | Low to moderate | Requires consumer inventory and migration proof. |

## Governance Risk Assessment

Governance risk is lowest where current trust, freshness, refusal, and
fail-closed patterns can be preserved.

Team operations bullpen readiness has acceptable governance risk if the next
phase defines:

- allowed statements
- prohibited statements
- required data
- refusal conditions
- freshness and confidence requirements
- no-ranking validation
- no-selection validation
- no-prediction validation
- no best/preferred/recommended behavior

Recommendation expansion, Game Context Intelligence, and Prospect Pipeline
carry higher governance risk because each could easily create preference,
prediction, unsupported data, or lifecycle-promotion pressure.

## Data Availability Assessment

Current strongest data:

- MLB Stats API rosters
- pitching game logs
- fatigue scores
- availability classifications
- freshness metadata
- sync metadata
- current team and bullpen group context

Current weakest data:

- injuries and transactions
- live game context
- leverage and matchup context
- warm-up activity
- private team intent
- real prospect feed, grades, ETA, and player-development evidence

Team operations bullpen readiness fits the strongest current data. Prospect
Pipeline and Game Context Intelligence depend on weaker or missing data.

## Portfolio Value Assessment

Portfolio value is strongest when the path:

- deepens the product's core identity
- remains demonstrably trustworthy
- shows thoughtful product judgment
- avoids unsupported claims
- uses existing engineering and governance evidence
- creates a clear next implementation story

Team operations bullpen readiness has high portfolio value because it shows a
move from component-level intelligence to an operations workflow while staying
inside the trustworthy bullpen domain.

Prospect Pipeline and Game Context Intelligence also have high narrative value,
but their evidence and data gaps make them less responsible as the first V3
direction.

## Baseball Operations Value Assessment

The strongest baseball operations question BaseballOS can answer with current
evidence is:

```text
What is the current operational readiness of this bullpen from public workload
and freshness data?
```

Team operations bullpen readiness directly addresses that question. It can
help a user inspect:

- how many arms are workload-available
- where workload constraints are concentrated
- whether current data is fresh enough to support a readiness view
- what limitations apply before any human baseball decision
- whether the system must refuse or downgrade confidence

This is more immediately supportable than prospect evaluation, game context,
or recommendation expansion that implies a preferred action.

## Recommended Next Product Direction

Recommended next direction:

```text
TEAM_OPERATIONS_BULLPEN_READINESS_PLANNING
```

The next product direction should be a constrained Team Operations
Intelligence planning milestone focused on bullpen readiness and workload
operations.

This direction should not start with implementation. It should start with a
capability definition document that specifies:

- exact user problem
- in-scope surface or workflow
- allowed statements
- prohibited statements
- required input data
- trust metadata requirements
- freshness metadata requirements
- refusal conditions
- fail-closed behavior
- accessibility and mobile expectations
- backend/API contract expectations if any
- frontend display expectations if any
- test evidence required before implementation
- lifecycle evidence packet requirements

## Rationale For The Recommendation

The recommendation is based on five findings:

1. BaseballOS is strongest in bullpen workload, availability, freshness, and
   trust-first recommendation governance.
2. Current production data can support a team-level readiness workflow without
   adding unsupported private or predictive data.
3. Team operations readiness has higher baseball operations value than a pure
   UI polish or governance maintenance milestone.
4. Prospect Pipeline and Game Context Intelligence have high potential but
   depend on evidence and data that are not currently mature.
5. Recommendation expansion is useful only if it remains neutral, governed, and
   subordinate to a clearly defined product capability.

The recommended path is therefore not "add recommendations." It is "define a
team operations bullpen readiness capability that uses current trusted data and
preserves all governance boundaries."

## Explicit Non-Goals

V3 Phase 1 does not authorize:

- implementation work
- runtime behavior changes
- API contract changes
- frontend behavior changes
- recommendation logic changes
- fatigue formula changes
- lifecycle promotion
- Prospect Pipeline production work
- Game Context Intelligence implementation
- ranking behavior
- selection behavior
- prediction behavior
- best option behavior
- preferred option behavior
- recommended option behavior
- matchup advice
- injury or medical inference
- team intent inference
- manager-intent inference
- private data integration

## Governance Confirmation

The certified Recommendation Engine V2 governance requirements remain:

```text
ranking_applied === false
selection_made === false
```

V3 Phase 1 explicitly confirms:

- no ranking behavior exists
- no selection behavior exists
- no prediction behavior exists
- no best option behavior exists
- no preferred option behavior exists
- no recommended option behavior exists

Any future V3 phase that proposes a product capability must preserve these
boundaries unless a separate governance reopening explicitly evaluates and
approves a changed boundary.

## Validation

Validation required for this phase:

```text
.\backend\venv\Scripts\python.exe -m pytest backend\tests --basetemp .pytest-tmp-v3-phase-1-product-review
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

Root `npm test` is not required for V3 Phase 1. If no root `package.json`
exists, that is expected and is not a project failure.

## Recommended Next Milestone

Recommended next milestone:

```text
BaseballOS V3 Phase 2 Team Operations Bullpen Readiness Capability Definition
```

The next milestone should remain planning-only unless a separate implementation
phase is explicitly authorized. It should define the Team Operations Bullpen
Readiness capability in enough detail to decide whether implementation is
safe, valuable, and governable.

## V3 Phase 2 Follow-Up

V3 Phase 2 has completed the Team Operations Bullpen Readiness capability
definition:

- `docs/V3_PHASE_2_TEAM_OPERATIONS_BULLPEN_READINESS_CAPABILITY_DEFINITION.md`

Phase 2 defines the allowed inputs, prohibited inputs, allowed outputs,
prohibited outputs, readiness vocabulary, constraint vocabulary, coverage
vocabulary, workload vocabulary, trust metadata, freshness metadata, refusal
metadata, fail-closed requirements, explainability requirements, testing
requirements, accessibility requirements, certification requirements, risks,
mitigations, and non-goals for the selected capability.

The next planning milestone after Phase 2 is:

```text
BaseballOS V3 Phase 3 Team Operations Bullpen Readiness Implementation Plan
```

This follow-up does not authorize implementation or runtime behavior changes.
