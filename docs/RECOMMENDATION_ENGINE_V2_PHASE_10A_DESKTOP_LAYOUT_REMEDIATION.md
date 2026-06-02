# Recommendation Engine V2 Phase 10A Desktop Layout Remediation

## Status

Recommendation Engine V2 Phase 10A Desktop Layout Remediation is complete.

This phase fixes the desktop rendering defect in the governed V2 bullpen-state
panel introduced during Phase 10.

Phase 10A does not change backend behavior, API behavior, recommendation logic,
ranking behavior, selection behavior, prediction behavior, or Recommendation
Engine V1 behavior.

## Defect Remediated

The Phase 10 panel could become visually cramped in desktop layouts where the
panel had less usable width than the viewport breakpoint implied.

Observed desktop issues included:

- narrow panel content
- word-by-word text wrapping
- squeezed trust and freshness metadata
- cramped refusal and explanation sections
- metadata cards with insufficient usable width

The pitcher table layout remains unchanged.

## Frontend Paths

The remediation updates:

- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
- `frontend/src/index.css`
- `frontend/tests/recommendationV2Rendering.test.mjs`

## Layout Approach

The V2 panel now uses component container width for internal layout decisions.

The panel applies:

- container-aware metadata grids
- container-aware state, inventory, team-context, and message grids
- `min-width: 0` safeguards on nested cards
- controlled text wrapping for metadata, explanations, limitations, and refusal
  copy
- full-width panel constraints to prevent overlap with adjacent dashboard
  content

This avoids forcing desktop viewport grid columns inside a narrow panel.

## Governed Rendering Preserved

The remediation preserves the governed Phase 10 rendering sections:

- bullpen state
- trust metadata
- freshness metadata
- governance metadata
- inventory visibility
- team context
- neutral candidate groups
- limitations
- explanations
- refusal metadata
- fail-closed state
- unavailable contract state

The panel remains descriptive only. It exposes bullpen intelligence and
visibility, not automated pitcher choice.

## Governance Compliance

The frontend rendering layer continues to preserve:

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

## Test Coverage

Phase 10A extends frontend test coverage in:

- `frontend/tests/recommendationV2Rendering.test.mjs`

The added guardrail verifies that the V2 panel uses container-aware layout
classes for desktop readability and does not rely on the cramped viewport grid
classes that caused the defect.

## Phase 11 Readiness

Phase 11 mobile and accessibility validation may resume after Phase 10A.

Future Phase 11 work should validate the remediated layout across mobile,
tablet, desktop, keyboard, and assistive technology surfaces while preserving
trust, freshness, refusal, limitation, explanation, no-ranking, and
no-selection guarantees.
