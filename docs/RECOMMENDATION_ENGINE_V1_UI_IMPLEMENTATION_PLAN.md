# Recommendation Engine V1 UI Implementation Plan

## Implementation Status

The Recommendation Engine V1 UI shell, controlled response-state rendering, and
selected-pitcher detail integration are implemented for candidate-level
evaluation only. The integrated flow uses a visible Evaluate Candidate action,
calls the one-candidate frontend client, and preserves confidence, freshness,
availability, explanations, limitations, category fields, refusal output,
`ranking_applied=false`, and `selection_made=false`.

No bullpen ranking, multi-candidate comparison, scoring behavior, final pitcher
selection, backend behavior change, API behavior change, or database change is
implemented by the UI work.

## 1. UI Objective

Recommendation Engine V1 UI should display candidate-level recommendation
evaluation from `POST /api/recommendations/candidate` without changing the
meaning of the backend response.

The UI must help a user inspect whether one pitcher is eligible for
policy-approved categories, should be handled with caution, should be avoided,
or cannot be evaluated because trusted data is insufficient. BaseballOS
recommends; it does not decide. The user remains responsible for the final
decision.

The UI must preserve:

- candidate-level evaluation only
- no final pitcher selection
- no bullpen ranking
- visible confidence
- visible freshness
- visible limitations
- visible refusal reasons
- `ranking_applied=false`
- `selection_made=false`

## 2. Explicit Non-Goals

This plan does not authorize:

- frontend UI implementation
- backend behavior changes
- API behavior changes
- database changes
- multi-candidate recommendation requests
- bullpen ranking displays
- scoring formulas
- final pitcher selection
- role-aware recommendations
- matchup guidance
- simulator integration
- team-level stress dashboard integration
- injury, medical, illness, or team-reported availability claims
- performance forecasts

This document is implementation planning only.

## Current Implementation Status

The Stage 1 UI shell and Stage 2 controlled state rendering are implemented in
`frontend/src/components/recommendations/RecommendationPanel.jsx`.

The panel:

- reserves visible sections for candidate status, category eligibility,
  explanations, limitations, trust/freshness, refusal output, and metadata
- renders success, caution, refusal, loading, error, and empty states from
  controlled props
- consumes candidate-level response shape through the frontend recommendation
  client helper without making live requests during render
- displays assigned categories, blocked categories, confidence, freshness,
  availability, refusal reasons, explanations, limitations, and no-ranking/
  no-selection metadata
- uses safe candidate-level copy
- has render tests in `frontend/tests/recommendationPanel.test.mjs`
- does not add a route, navigation item, candidate selector, dashboard panel,
  live request workflow, ranking, scoring, comparison, or final pitcher
  selection

The dashboard integration planning document is
`docs/RECOMMENDATION_ENGINE_V1_DASHBOARD_INTEGRATION_PLAN.md`. It recommends
embedding future V1 dashboard display inside the existing single-pitcher detail
workflow, with dashboard implementation remaining a separate future step.

## 3. Where The UI Should Live

The future UI should live under the existing frontend application structure:

- route candidate: `/recommendations`
- page directory: `frontend/src/components/recommendations/`
- shared API client: `frontend/src/utils/api.js`
- shared UI primitives: `frontend/src/components/UI/`

The route should be added only when page-level UI implementation is authorized.
Until then, no navigation or route should be added.

The recommended first surface is a standalone candidate evaluation page rather
than a bullpen dashboard panel. This keeps V1 scoped to one candidate at a time
and reduces the risk of implying bullpen ranking. Later, the Bullpen page may
link into the candidate evaluation surface for a selected pitcher, but it must
not render a ranked recommendation list.

## 4. Candidate Selection And Input Assumptions

The first UI should assume candidate data comes from existing BaseballOS
pitcher and availability surfaces.

Candidate input assumptions:

- The UI evaluates exactly one candidate per API call.
- Candidate payloads are assembled from existing pitcher, team, availability,
  confidence, freshness, and workload fields.
- The UI does not allow manual editing of availability status, confidence,
  freshness, or workload inputs.
- The UI may allow a user to select a pitcher from an existing team or bullpen
  data set.
- If required candidate fields are missing, the UI must show a refusal or
  unavailable state rather than fabricating inputs.
- Candidate arrays must not be sent to the candidate endpoint.

The UI may reuse `evaluateRecommendationCandidate()` from
`frontend/src/utils/api.js`. It must not duplicate API request shape logic in
component code.

## 5. Recommended Component Boundaries

Recommended future components:

| Component | Responsibility |
| --- | --- |
| `RecommendationPage` | Page shell, team/pitcher selection, request state, and result orchestration. |
| `RecommendationCandidateSelector` | Select exactly one candidate from already-loaded pitcher data. |
| `RecommendationResultPanel` | Render success, caution, avoidance, and refusal states from the API response. |
| `RecommendationTrustStrip` | Display confidence, freshness, availability, no-ranking, and no-selection status. |
| `RecommendationCategoryList` | Display assigned and blocked categories without ranking. |
| `RecommendationExplanationList` | Display backend explanations with stable codes available in details. |
| `RecommendationLimitationList` | Display mandatory limitations near the result. |
| `RecommendationRefusalPanel` | First-class refusal state with reason, trust fields, explanations, and limitations. |
| `RecommendationMetadataPanel` | Optional details for policy, version, response mode, and audit references. |

Component rules:

- Components consume backend response fields.
- Components do not compute recommendation categories.
- Components do not compare candidates.
- Components do not sort or rank candidates.
- Components preserve response field names in view-model helpers where possible.

## 6. Required Visible Trust Fields

Every result state must show:

- candidate name when available
- availability status
- confidence level
- confidence reason when present
- visible limitation text or visible limitation count with expansion
- no-ranking status
- no-selection status

Trust fields should appear close to the result heading, not buried in a footer.

Safe visible labels:

- "Confidence"
- "Availability"
- "No bullpen ranking applied"
- "No final pitcher selection made"

## 7. Required Visible Freshness Fields

Every result state must show freshness.

Required fields:

- freshness state
- data-through date when present
- last successful sync when present
- latest sync status when present
- freshness limitation when freshness is stale, missing, incomplete,
  historical, or unknown

The UI must distinguish data-through date from sync timestamp. A current sync
timestamp must not be treated as current workload data when the data-through
date is stale or missing.

## 8. Required Explanation Display

The UI must show backend explanations as user-facing content.

Explanation display rules:

- Show all explanation messages returned by the API.
- Keep stable explanation codes available in details or audit expansion.
- Group explanations by result state only if messages remain visible.
- Refusal explanations must name the fail-closed reason.
- Caution explanations must appear before any category label can be read as
  positive guidance.

The UI must not add unsupported baseball reasoning.

## 9. Required Limitation Display

Limitations must appear on every success, caution, avoidance, refusal, empty,
and error state.

Required limitation behavior:

- Show mandatory limitations from the API response.
- Keep limitations on the same page or panel as the result.
- Do not rely only on static methodology documentation.
- Preserve the user-decision limitation.
- Preserve no-ranking and no-selection limitations.

Limitations may be displayed as a compact list with an expandable detail area,
but the user must be able to see that limitations exist without leaving the
surface.

## 10. Required Category Display

Category display must be eligibility display, not selection display.

Required behavior:

- Show primary `category` and `category_code` when present.
- Show assigned categories under "Eligible Category" or "Category Eligibility".
- Show blocked categories with reasons when present.
- Distinguish positive categories from `Use With Caution` and `Avoid Tonight`.
- Do not display `Bullpen Stress Alert` as a candidate-level result unless a
  later policy explicitly authorizes it.

The UI must not display category cards as ordered results, winner cards, or
ranked options.

## 11. Required Refusal Display

Refusal is a normal trust outcome and must be visually distinct from transport
errors.

Required refusal content:

- refusal label
- refusal reason
- candidate identity when available
- confidence state
- freshness state
- availability state when available
- blocked categories when available
- explanations
- limitations
- no-ranking status
- no-selection status

Safe refusal headings:

- "Insufficient trusted data"
- "Current recommendation unavailable"
- "Freshness check failed"
- "Confidence too low for recommendation"

Refusal must not be softened into speculative guidance.

## 12. Required Metadata Display

The following metadata must be visible in the main result or trust strip:

- `ranking_applied=false` as "No bullpen ranking applied"
- `selection_made=false` as "No final pitcher selection made"

The following metadata may be in an expandable audit section:

- policy
- policy version
- engine version
- response mode
- candidate pipeline enabled
- selected pitcher id, which must be empty or null
- policy document reference
- API contract document reference
- frontend contract document reference when useful

The UI must not hide no-ranking and no-selection status behind developer-only
details.

## 13. Loading, Error, And Empty States

Loading state:

- Show that one candidate evaluation is in progress.
- Do not show placeholder categories or placeholder recommendations.
- Preserve page space for trust fields to reduce layout shifts.

Transport error state:

- Show a request failure message.
- Do not transform transport failure into recommendation refusal.
- Keep user-facing wording separate from policy refusal wording.
- Include a retry action only if it repeats the same one-candidate request.

Empty state:

- Show "No candidate evaluation available" or equivalent safe copy.
- Do not show an empty recommendation list as success.
- Do not invent category, confidence, freshness, explanation, or limitation
  values.

Unknown data state:

- Show that trusted recommendation data is unavailable.
- Preserve no-ranking and no-selection labels when an API response exists.

## 14. Mobile Layout Expectations

Mobile layout must preserve trust-first readability.

Mobile requirements:

- The candidate name, outcome, confidence, freshness, and refusal or category
  label must fit without horizontal scrolling.
- Trust strip content may wrap, but it must remain visible.
- Explanation and limitation lists must be readable at small widths.
- Category labels must wrap rather than truncate.
- Refusal and caution states must remain distinct.
- No-ranking and no-selection indicators must remain visible.
- Buttons and expandable controls must have reliable touch targets.

Secondary audit metadata may collapse into details, but trust, freshness,
limitations, refusal reasons, and no-selection status must not disappear.

## 15. Accessibility Expectations

Accessibility requirements:

- Use semantic headings for page, candidate, outcome, trust fields,
  explanations, limitations, refusal, and metadata.
- Do not rely on color alone for success, caution, avoidance, refusal, or
  freshness state.
- Provide text labels for icons.
- Keep status and category labels readable at supported contrast levels.
- Make expandable explanation, limitation, and metadata sections keyboard
  accessible.
- Announce result state changes to assistive technologies when a new response
  loads.
- Preserve readable date and time formats.
- Keep focus order consistent after candidate selection or retry.

Accessibility wording must preserve the same policy meaning as visual wording.

## 16. Styling, Tone, And Copy Guidance

Tone should be direct, restrained, and decision-support oriented.

Allowed-style copy:

- "Candidate Evaluation"
- "Eligible Category"
- "Category Eligibility"
- "Use With Caution"
- "Avoid Tonight"
- "Insufficient trusted data"
- "No bullpen ranking applied"
- "No final pitcher selection made"
- "The user remains responsible for the final decision."

Prohibited-style copy:

- "Best pitcher tonight"
- "Guaranteed safest arm"
- "Projected result"
- "Will perform best"
- "Injury risk"
- "Manager should use"
- "Final recommendation"
- "Ranked number one"

Styling guidance:

- Use status badges for confidence, freshness, availability, ranking status,
  and selection status.
- Use caution styling for `Use With Caution` and refusal styling for refusals.
- Do not use trophy, winner, rank-number, or leaderboard visual treatments.
- Keep component density similar to existing BaseballOS dashboard and bullpen
  surfaces.

## 17. Test Strategy

Recommended frontend tests:

- client helper is called with exactly one candidate
- success response displays confidence, freshness, availability, explanations,
  limitations, assigned categories, no-ranking, and no-selection
- caution response displays caution reasons and limitations
- refusal response displays refusal reason, trust fields, explanations,
  limitations, no-ranking, and no-selection
- stale freshness is not displayed as current guidance
- low or unknown confidence is not displayed as positive category eligibility
- unavailable candidate does not display positive category language
- empty state does not display placeholder recommendations
- transport error state does not display policy refusal language
- mobile rendering preserves trust, freshness, and limitation visibility
- accessibility checks cover labels, headings, focus order, and expandable
  details

Recommended backend/API regression checks:

- existing recommendation API tests continue to pass
- API response continues to include required metadata and refusal fields

No UI test should assert ranking, score, comparison, or final selection fields.

## 18. Staged Implementation Sequence

### Stage 1: UI Shell And View Model Boundaries

Create the initial presentational shell and any testable helpers needed to map
API response fields into display-ready labels without changing recommendation
meaning.

Exit criteria:

- shell reserves visible sections for status, categories, explanations,
  limitations, trust/freshness, refusal output, and metadata
- helpers preserve trust, freshness, explanations, limitations, categories,
  refusal, ranking, and selection fields
- helpers reject or flag multi-candidate response assumptions
- no React route or page is added yet

### Stage 2: Result Display Components

Create isolated presentational components for trust strip, categories,
explanations, limitations, metadata, and refusal state.

Exit criteria:

- panel consumes controlled response, loading, error, and empty state props
- components render from fixture responses
- success, caution, refusal, stale, and low-confidence fixtures are covered
- no component performs recommendation logic
- dashboard integration remains out of scope for this stage

### Stage 3: Candidate Evaluation Page

Add a standalone `/recommendations` page that evaluates one candidate at a time.

Exit criteria:

- page uses `evaluateRecommendationCandidate()`
- page sends one candidate per request
- loading, transport error, empty, success, caution, and refusal states are
  present
- route copy follows the frontend display contract

### Stage 4: Bullpen Surface Linkage

Optionally link from existing bullpen pitcher rows or detail panels into the
candidate evaluation page.

Exit criteria:

- link passes or resolves one candidate
- bullpen page does not show ranked recommendations
- no team-level recommendation UI is introduced

### Stage 5: Mobile And Accessibility Pass

Validate responsive layout and accessibility behavior.

Exit criteria:

- mobile layout preserves required trust and freshness fields
- keyboard and screen-reader behavior is covered
- status labels do not rely on color alone

### Stage 6: Governance And Regression Validation

Verify the UI does not overstate recommendation meaning.

Exit criteria:

- prohibited copy is absent
- no ranking or selection UI appears
- limitations remain visible
- stale, missing, low-confidence, and unavailable states fail closed in display
- API behavior remains unchanged

## 19. Risks And Guardrails

Risks:

- A category badge may read like final selection.
- A candidate picker may accidentally become a bullpen ranking view.
- Freshness may be hidden behind secondary metadata.
- Limitations may be treated as static methodology copy instead of result
  content.
- Refusal may be shown as an application error.
- Caution may be styled too similarly to a positive category.
- Component helpers may start recomputing category meaning locally.

Guardrails:

- Display "No bullpen ranking applied" on every API-backed result.
- Display "No final pitcher selection made" on every API-backed result.
- Keep explanations and limitations near the outcome.
- Test refusal as a normal state.
- Keep candidate evaluation one-at-a-time.
- Use backend response fields as source of truth.
- Update policy and contracts before changing category or refusal semantics.

## 20. Future Expansion Boundaries

Future UI expansion requires separate policy, contract, and implementation
planning before build work begins.

Deferred expansions:

- multi-candidate comparison
- bullpen ranking
- team-level stress dashboard
- simulator integration
- role-aware recommendation display
- matchup-aware guidance
- rest-of-series planning
- public recommendation API consumer UI
- external data integration

Any expansion must preserve deterministic backend output, visible explanations,
visible limitations, freshness transparency, confidence disclosure,
no-ranking/no-selection clarity, and fail-closed behavior when trusted data is
insufficient.
