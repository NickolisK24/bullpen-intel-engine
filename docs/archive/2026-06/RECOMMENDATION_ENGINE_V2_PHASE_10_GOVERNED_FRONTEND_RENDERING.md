# Recommendation Engine V2 Phase 10 Governed Frontend Rendering

## Status

Recommendation Engine V2 Phase 10 Governed Frontend Rendering is complete.

This phase adds governed frontend rendering for the normalized V2 bullpen-state
client output introduced in Phase 9.

Phase 10A Desktop Layout Remediation is also complete and documents the
desktop readability fix in:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_10A_DESKTOP_LAYOUT_REMEDIATION.md`

Phase 10B Bullpen Selected Pitcher Layout Remediation is also complete and
documents the selected-pitcher detail readability fix in:

- `docs/RECOMMENDATION_ENGINE_V2_PHASE_10B_BULLPEN_SELECTED_PITCHER_LAYOUT_REMEDIATION.md`

The rendered endpoint source remains:

```text
GET /api/recommendations/v2/bullpen-state
```

Phase 10 does not change backend V2 behavior, create new backend routes, rank
pitchers, select pitchers, predict outcomes, or change Recommendation Engine
V1.

## Frontend Rendering Paths

The V2 governed rendering layer is implemented in:

- `frontend/src/components/recommendations/RecommendationV2BullpenStatePanel.jsx`
- `frontend/src/components/dashboard/Dashboard.jsx`
- `frontend/src/components/recommendations/index.js`
- `frontend/src/index.css`

The dashboard consumes the Phase 9 client helper:

- `getRecommendationV2BullpenState`

The rendered panel uses only normalized client output. It does not render raw
unsafe response payloads.

## Rendered V2 Sections

The governed panel renders:

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

The panel is descriptive only. It exposes bullpen intelligence and visibility,
not automated pitcher choice.

## Desktop Layout Remediation

Phase 10A fixes the desktop layout defect where viewport-based internal grids
could squeeze trust, freshness, explanation, refusal, inventory, and context
sections when the panel had less usable width than the full desktop viewport.

The panel now uses container-aware layout classes so internal sections respond
to the panel width rather than the browser width. This preserves readable
metadata cards and avoids word-by-word wrapping in constrained desktop
columns.

Phase 10B applies the same container-aware readability principle to the
Bullpen selected-pitcher detail surface and embedded recommendation trust
panel. The Bullpen layout remediation changes presentation only and does not
change backend behavior, API behavior, recommendation logic, or Recommendation
Engine V1 behavior.

## Fail-Closed and Unavailable Behavior

The panel renders fail-closed states explicitly when the client reports
`fail_closed`.

When the client reports `unavailable`, the panel:

- renders a contract-unavailable state
- shows diagnostic counts
- withholds bullpen-state details
- avoids rendering unsafe candidate, inventory, or team-context output

The panel does not fabricate confidence, freshness, limitations, explanations,
refusal reasons, trust metadata, or governance flags.

## Governance Compliance

The frontend rendering layer preserves:

```text
ranking_applied === false
selection_made === false
```

The panel avoids:

- ranking UI
- selection UI
- prediction UI
- best/preferred/recommended pitcher UI
- score-ordered UI
- winner-style UI
- visual hierarchy that implies a final pitcher choice

The panel formats backend neutral-ordering shorthand as governed display copy
instead of exposing ranking-related shorthand to users.

## Test Coverage

Phase 10 frontend test coverage is implemented in:

- `frontend/tests/recommendationV2Rendering.test.mjs`

Coverage includes:

- available-state rendering
- fail-closed rendering
- unavailable-state rendering
- trust metadata visibility
- freshness metadata visibility
- limitation visibility
- explanation visibility
- refusal metadata visibility
- neutral candidate group rendering
- forbidden display-language scan
- unsafe display-language suppression
- loading and error rendering

Existing frontend tests continue to cover Recommendation Engine V1 frontend
behavior.

## V1 Preservation

Recommendation Engine V1 remains unchanged.

This phase did not modify:

- V1 recommendation engine behavior
- V1 recommendation API route semantics
- V1 candidate evaluation behavior
- V1 response contract
- V1 frontend candidate-evaluation behavior

The V1 guarantees remain active:

```text
ranking_applied = false
selection_made = false
```

## Phase 11 Readiness Boundary

Future V2 Phase 11 work should validate mobile and accessibility behavior for
the governed V2 rendering layer after the completed Phase 10A and Phase 10B
layout remediations.

Phase 11 should preserve trust, freshness, refusal, limitation, explanation,
no-ranking, and no-selection guarantees across mobile layout and assistive
technology surfaces.
