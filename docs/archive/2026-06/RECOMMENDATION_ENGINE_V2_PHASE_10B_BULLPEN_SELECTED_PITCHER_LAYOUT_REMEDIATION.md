# Recommendation Engine V2 Phase 10B Bullpen Selected Pitcher Layout Remediation

## Status

Recommendation Engine V2 Phase 10B Bullpen Selected Pitcher Layout
Remediation is complete.

This phase fixes the Bullpen page selected-pitcher desktop layout where the
right-side detail and recommendation trust surface could become too narrow on
common desktop widths.

Phase 10B does not change backend behavior, API behavior, recommendation
logic, ranking behavior, selection behavior, prediction behavior, or
Recommendation Engine V1 behavior.

## Defect Remediated

When a pitcher was selected on the Bullpen page, the table and detail surface
used fixed desktop widths that left the detail panel cramped.

Observed issues included:

- narrow selected-pitcher detail content
- word-by-word text wrapping
- squeezed recommendation trust metadata
- cramped refusal and explanation sections
- table, pitcher card, and recommendation content competing for width

## Frontend Paths

The remediation updates:

- `frontend/src/components/bullpen/Bullpen.jsx`
- `frontend/src/components/bullpen/PitcherDetail.jsx`
- `frontend/src/components/recommendations/RecommendationPitcherDetailSection.jsx`
- `frontend/src/components/recommendations/RecommendationPanel.jsx`
- `frontend/src/index.css`
- `frontend/tests/recommendationPitcherDetailSection.test.mjs`

## Layout Approach

The Bullpen selected-pitcher layout now keeps the table and detail surface
stacked through common desktop widths, then uses a readable fixed-width detail
rail only on wider desktop screens.

The embedded recommendation detail surface now uses component container width
for internal layout decisions.

The remediation applies:

- full-width detail behavior at constrained desktop widths
- selected-state page width expansion on wide desktops
- a readable `2xl` detail rail width
- `min-width: 0` safeguards on nested detail and recommendation cards
- container-aware recommendation panel grids
- controlled text wrapping for trust, freshness, refusal, explanation,
  limitation, and metadata copy

This avoids forcing viewport-width grid columns inside a constrained
selected-pitcher detail panel.

## Governance Compliance

The selected-pitcher recommendation surface continues to preserve:

```text
ranking_applied === false
selection_made === false
```

The remediation does not introduce:

- ranking UI
- selection UI
- prediction UI
- best/preferred/recommended pitcher UI
- score-ordered UI
- winner-style UI
- backend route changes
- API contract changes

## V1 Preservation

Recommendation Engine V1 candidate evaluation behavior remains unchanged.

This phase changes layout only. It does not modify:

- V1 recommendation engine behavior
- V1 recommendation API semantics
- V1 candidate evaluation requests
- V1 response parsing
- V1 governance flags

## Test Coverage

Phase 10B extends frontend test coverage in:

- `frontend/tests/recommendationPitcherDetailSection.test.mjs`

The added guardrail verifies that the Bullpen selected-pitcher surface no
longer uses the cramped fixed desktop split and that embedded recommendation
content uses container-aware layout classes.

## Phase 11 Readiness

Phase 11 mobile and accessibility validation may resume after Phase 10B.

Future Phase 11 work should validate both governed V2 dashboard rendering and
Bullpen selected-pitcher detail rendering across mobile, tablet, desktop,
keyboard, and assistive technology surfaces while preserving trust, freshness,
refusal, limitation, explanation, no-ranking, and no-selection guarantees.
