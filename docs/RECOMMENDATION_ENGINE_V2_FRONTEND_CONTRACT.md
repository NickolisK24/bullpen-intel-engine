# Recommendation Engine V2 Frontend Contract

## 1. Executive Summary

This document defines the proposed Recommendation Engine V2 frontend display
contract before implementation.

It is a documentation and contract-design milestone only. It does not
implement V2, create or modify React components, modify API clients, modify
backend behavior, modify frontend behavior, or change certified Recommendation
Engine V1 behavior.

The V2 frontend contract must preserve:

```text
ranking_applied = false
selection_made = false
```

Future UI must not make those backend guarantees meaningless through
presentation. Even when the API does not rank pitchers, the UI must not arrange,
emphasize, label, or describe candidates in a way that suggests ranking,
selection, automated decision-making, "best option" logic, predictive
certainty, or unsupported baseball opinion.

## 2. Relationship to V1 Frontend

Recommendation Engine V1 frontend behavior is certified for candidate-level
evaluation in the pitcher detail workflow. It evaluates one selected candidate
at a time after user action and displays confidence, freshness, availability,
explanations, limitations, category eligibility, refusal reasons,
`ranking_applied=false`, and `selection_made=false`.

This V2 frontend contract does not modify V1 frontend behavior, V1 API client
behavior, V1 Recommendation Panel behavior, V1 routing, V1 copy, or V1
certification.

Future V2 frontend work must remain separate from V1 until explicitly approved
for implementation.

## 3. Relationship to V2 Strategy

The V2 strategy foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`

The strategy allows future exploration of bullpen-level intelligence, bullpen
inventory visibility, bullpen stress awareness, leverage resource visibility,
workload distribution visibility, grouped eligibility reporting, bullpen
readiness reporting, and broader explainability.

This frontend contract defines how those future outputs may be displayed
without turning organization into ranking or turning context into selection.

## 4. Relationship to V2 Governance Boundaries

The V2 governance-boundary document is:

- `docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`

This frontend contract is subordinate to that document. Future UI must preserve
the rule that BaseballOS may group, summarize, and explain, but must not rank,
choose, or decide.

Any UI pattern that implies ranking, selection, prediction, hidden scoring,
unsupported baseball opinion, or final pitcher choice is outside the approved
V2 frontend scope.

## 5. Relationship to V2 Architecture

The V2 architecture foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`

The architecture defines conceptual UI layers such as Trust Strip, Bullpen
Context Panel, Candidate Group Panels, Inventory Panels, Explanation Panels,
and Limitation Panels.

This frontend contract converts those conceptual layers into presentation
rules, copy rules, mobile rules, accessibility rules, testing expectations, and
certification expectations.

## 6. Relationship to V2 API Contract

The V2 API contract foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`

Future V2 frontend display must honor API metadata and object boundaries,
including:

- `ranking_applied=false`
- `selection_made=false`
- `scope`
- `confidence`
- `data_state`
- `generated_at`
- `freshness`
- `limitations`
- `explanations`
- `refusal_reasons`

The frontend must not hide, rename, reorder, or visually transform API output
in a way that creates ranking or selection semantics the API contract forbids.

## 7. Frontend Contract Goals

The V2 frontend contract should:

- preserve V1 no-ranking and no-selection guarantees
- keep future V2 displays descriptive, explainable, deterministic, auditable,
  trust-first, and fail-closed
- define allowed, restricted, and forbidden UI patterns
- define safe rendering rules for candidate groups, inventory, bullpen state,
  and team context
- require visible or easily accessible trust metadata
- require visible freshness, limitations, explanations, and refusal states
- keep mobile presentation governance-safe
- keep accessibility text governance-safe
- support future frontend certification and test design

## 8. Frontend Contract Non-Goals

This contract does not define or authorize:

- implemented React components
- component props
- API client changes
- route changes
- design-system changes
- backend behavior changes
- API behavior changes
- Recommendation Engine V1 behavior changes
- pitcher ranking UI
- selected-pitcher UI
- score-based cards
- predictive UI
- automated decision flows
- production implementation

No section of this document authorizes V2 frontend implementation.

## 9. Allowed UI Patterns

Future V2 UI may use the following patterns when they remain neutral,
descriptive, explainable, and auditable:

- grouped cards
- neutral category sections
- alphabetic candidate ordering
- stable ID ordering
- stable API ordering when documented as non-ranking
- status-based grouping
- inventory summary panels
- bullpen stress/readiness panels
- team context panels
- trust metadata strips
- limitation panels
- refusal states
- explanation drawers or expandable panels
- visible freshness banners or trust rows
- neutral empty states that preserve refusal or limitation context

Allowed UI patterns must disclose why the displayed group, inventory, or
context exists. They must not suggest that one pitcher is the best, first,
preferred, selected, or automatically recommended choice.

## 10. Restricted UI Patterns

The following UI patterns are restricted and require additional governance
review before implementation:

- visual priority labels
- urgency badges
- color intensity that implies "best"
- sorting by confidence if it implies quality
- ordering by workload risk if it implies preference
- comparison tables
- side-by-side candidate comparisons
- default expanded "winner-like" cards
- emphasis styling that appears to select one pitcher
- pinned candidate cards
- primary action placement on one candidate only
- grouped layouts where the first item appears superior by default

Restricted patterns are not approved by this contract. A future proposal must
document the exact UI behavior, wording, ordering rule, visual hierarchy,
metadata, failure modes, tests, and certification evidence before any
implementation begins.

## 11. Forbidden UI Patterns

Future V2 UI must not include:

- numbered ranking lists
- leaderboard layouts
- "top option" cards
- "best pitcher" banners
- selected/recommended pitcher callouts
- winner badges
- first/second/third labels
- score-based cards
- prediction cards
- "use this pitcher" commands
- UI flows that force a single final choice
- trophy, checkmark, crown, or winner visuals for candidates
- default sorting by implied quality
- preference arrows between candidates
- candidate cards labeled as selected, recommended, preferred, or best

Forbidden UI patterns must not appear in page layout, component names exposed
to users, headings, copy, labels, tooltips, alt text, ARIA labels, testing
fixtures, screenshots, or documentation that implies implementation approval.

## 12. Candidate Group Rendering Rules

Candidate groups may show neutral eligibility categories such as:

```text
Fresh High-Leverage Arms
Available Multi-Inning Arms
Use With Caution
Avoid Tonight
```

Candidate groups must not show:

```text
#1 Pitcher
Top Arm
Best Available
Preferred Option
```

Candidates within groups must use neutral ordering only.

Acceptable ordering:

- alphabetical order
- stable database ID order
- stable API order if contractually non-ranking

Unacceptable ordering:

- implied quality order
- confidence order presented as preference
- workload-risk order presented as recommendation priority
- order based on hidden weights
- order based on expected performance

Candidate group UI must display or make accessible:

- group label
- group description
- eligibility basis
- candidate count
- neutral ordering rule when order could be interpreted as preference
- confidence
- freshness
- explanations
- limitations
- refusal reasons when present

Candidate groups are informational. They are not rankings.

## 13. Inventory Rendering Rules

Inventory displays must be descriptive.

Allowed examples:

```text
High-Leverage Inventory: 2 available arms
```

```text
Multi-Inning Inventory: 1 limited arm
```

```text
Bullpen Stress: Elevated due to limited fresh inventory
```

Forbidden examples:

```text
Use these two arms first
```

```text
Best leverage option
```

```text
Preferred bullpen path
```

Inventory UI may display counts, category labels, member lists, evidence,
limitations, freshness, and confidence. It must not imply which member should
be used first or which bullpen path the user should choose.

## 14. Bullpen State Rendering Rules

Bullpen state displays may show descriptive summaries such as:

- overall status
- stress level
- readiness summary
- inventory summary
- current confidence
- current freshness
- data-state limitations
- refusal state when bullpen state cannot be trusted

Bullpen state displays must not show:

- final pitcher choice
- top candidate
- best available pitcher
- projected outcome
- selected arm
- preferred sequence

Stress/readiness language must explain the workload, availability, freshness,
or limitation evidence behind the status. It must not become a command.

## 15. Team Context Rendering Rules

Team context displays may show descriptive bullpen context such as:

- workload distribution
- availability distribution
- leverage inventory
- readiness indicators
- stress indicators
- explanations
- limitations

Team context displays must not provide:

- team-level decision commands
- matchup advice
- game outcome prediction
- manager-intent inference
- roster guidance
- save prediction
- performance forecasting
- final pitcher selection

Team context should help the user understand bullpen constraints, not replace
the user's baseball decision.

## 16. Trust Metadata Rendering Rules

Every future V2 view must make trust metadata visible or easily accessible:

- confidence
- freshness
- data-through date
- sync timestamp
- data state
- generated-at timestamp
- limitations
- explanations
- refusal reasons when present
- `ranking_applied=false`
- `selection_made=false`

The UI must not hide material limitations behind purely cosmetic interactions.
If an interaction is used to expand details, the collapsed state must still
show that limitations, explanations, freshness, or refusal reasons exist.

Trust metadata should appear close to the output it qualifies. A global
methodology page may supplement trust metadata, but it must not substitute for
contextual visibility.

## 17. Freshness Rendering Rules

The frontend must visibly represent:

- fresh data
- stale data
- degraded freshness
- missing data
- unknown data state

Freshness UI must show:

- sync timestamp when available
- data-through date when available
- stale warning when applicable
- missing data warning when applicable
- degraded confidence when applicable
- refusal or suppression when freshness cannot support output

Stale or degraded data must not look equivalent to complete/current data.

The UI must preserve the existing BaseballOS distinction between operational
sync timestamp and baseball data-through date. A sync timestamp must not be
presented as proof that baseball workload coverage is current.

## 18. Limitation Rendering Rules

Limitations must be visible or easily accessible in every V2 view.

Limitations may explain:

- missing workload evidence
- stale data
- incomplete freshness coverage
- lack of manager intent
- lack of injury or medical context
- lack of bullpen warm-up context
- unsupported scope
- degraded confidence

The UI must not bury blocking limitations behind decorative-only affordances.
If limitations materially affect output trust, the view must surface that fact
without requiring users to infer it from color or placement alone.

## 19. Refusal Rendering Rules

If the API refuses, suppresses, or downgrades output, the UI must render that
state clearly.

The UI must not replace refusal with a generic empty state that hides why
output was unavailable.

Refusal UI must display or make accessible:

- refusal reason
- affected output scope
- freshness state
- data state
- limitations
- available explanations
- confidence impact
- whether output was refused, suppressed, or downgraded

Refusal is a valid BaseballOS product outcome. The UI should make refusal
understandable, not apologetic or invisible.

## 20. Mobile Rendering Requirements

Mobile layouts must preserve non-ranking behavior.

Stacked cards can accidentally imply order. Mobile V2 layouts must therefore:

- use neutral ordering
- document neutral ordering when necessary
- avoid first-card winner presentation
- avoid larger first cards unless every group shares the same treatment
- avoid sticky candidate cards that imply selection
- keep trust metadata reachable without hiding material limitations
- preserve visible stale, degraded, and refusal states
- avoid layouts that force a single final candidate choice

Mobile compression must not remove governance context. If space is limited,
the UI should preserve scope, confidence, freshness, limitations, and refusal
visibility before adding decorative or comparative content.

## 21. Accessibility Requirements

Accessibility text must preserve the same governance boundaries as visible UI.

ARIA labels, screen-reader text, button labels, headings, captions, tooltips,
alt text, test IDs that surface into assistive workflows, and keyboard-focus
announcements must not introduce forbidden recommendation language.

Accessibility labels must not say:

- best option
- top choice
- recommended pitcher
- selected pitcher
- use this pitcher
- ranks first
- preferred arm

Accessibility text may say:

- currently qualifies for
- currently grouped under
- inventory includes
- freshness is stale
- output refused
- limitations are present
- explanation available

Accessible navigation must not force users through candidates in a way that
announces or implies a ranked sequence.

## 22. Copywriting and Language Rules

Allowed language:

```text
Currently qualifies for
Currently grouped under
Inventory includes
Available category
Elevated workload risk
Limited fresh inventory
Freshness is stale
Output refused
Limitations are present
Explanation available
```

Forbidden language:

```text
Best option
Top choice
Use this pitcher
Recommended pitcher
Preferred arm
Ranks first
Should be used
Projected to succeed
Selected pitcher
Winner
```

Copy must distinguish organizing information from ranking information. It may
describe category eligibility, inventory, workload risk, freshness, and
limitations. It must not command, select, rank, predict, or imply unsupported
baseball certainty.

## 23. Visual Hierarchy Rules

The UI must not imply selection through:

- oversized winning cards
- trophy/checkmark winner visuals
- highlighted top card
- rank-like badges
- isolated "best" panels
- sorted columns that imply preference
- dominant candidate placement
- one-card hero layouts for candidate groups
- winner-like color treatment
- primary action treatment on one candidate

Visual emphasis may be used for warnings, refusals, freshness degradation, and
limitations, but not for selecting a candidate.

When visual emphasis is used for trust warnings, the copy must explain the
trust condition. Color alone is not sufficient.

## 24. Empty, Stale, and Degraded States

Future V2 UI must distinguish:

- no qualifying candidates
- output refused
- output suppressed
- data stale
- data missing
- confidence degraded
- explanations unavailable
- scope unsupported

Generic empty states are not sufficient when trust state is material.

Examples of acceptable state framing:

```text
No pitchers currently qualify for this category from trusted current data.
```

```text
Bullpen-state output is refused because data is stale.
```

```text
Inventory visibility is downgraded because workload evidence is incomplete.
```

The UI must preserve `ranking_applied=false` and `selection_made=false` even in
empty, stale, degraded, or refusal states.

## 25. Testing Requirements

Future implementation must test:

- no forbidden copy appears
- no ranking labels render
- no selected/recommended pitcher UI appears
- candidate ordering is neutral
- refusal states render clearly
- freshness states render visibly
- stale and degraded states are visually distinct
- limitations render visibly
- explanations render or are accessible
- trust metadata is accessible
- mobile layout does not imply ranking
- accessibility labels preserve governance language
- UI preserves `ranking_applied=false`
- UI preserves `selection_made=false`

Tests must inspect successful, empty, stale, degraded, and refusal views.

## 26. Certification Requirements

Frontend V2 cannot be certified unless:

- UI preserves `ranking_applied=false`
- UI preserves `selection_made=false`
- all forbidden language is absent
- all required trust metadata is visible or accessible
- stale/degraded states are visually distinct
- refusal states are explicit
- mobile rendering is governance-safe
- accessibility text is governance-safe
- candidate ordering is neutral
- no UI pattern implies a recommendation winner
- V1 frontend behavior remains unchanged

Certification must prove both visual presentation and non-visible
accessibility text preserve V2 governance boundaries.

## 27. Implementation Gate

V2 frontend implementation must not begin until:

1. frontend contract is approved
2. certification requirements are approved
3. user explicitly approves implementation

This document alone does not authorize React component work, API client
changes, frontend behavior changes, backend behavior changes, API behavior
changes, or Recommendation Engine V1 behavior changes.
