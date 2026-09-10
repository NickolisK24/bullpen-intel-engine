# Recommendation Engine V1 Frontend Display Contract

## 1. Frontend Display Objective

This contract defines how future frontend surfaces must display candidate-level
Recommendation Engine V1 output safely and honestly.

The frontend may display the structured response from
`POST /api/recommendations/candidate`. It must not reinterpret, recalculate,
rank, compare, or select pitchers. BaseballOS may show category eligibility,
cautionary guidance, avoidance output, or refusal output. It must not imply that
BaseballOS made the final pitching decision.

The frontend display must preserve these invariants:

- candidate-level evaluation only
- deterministic backend output
- visible confidence
- visible freshness
- visible explanations
- visible limitations
- visible refusal reasons
- `ranking_applied=false`
- `selection_made=false`

## 2. Explicit Non-Goals

This contract does not authorize:

- frontend UI implementation
- backend logic changes
- API behavior changes
- database changes
- multi-candidate ranking
- bullpen ranking displays
- final pitcher selection displays
- scoring formulas
- performance forecasts
- injury, medical, illness, or team-reported availability claims
- matchup modeling
- simulator integration
- dashboard integration
- public API publishing

This contract is display planning only.

## 3. Required Visible Fields

Every future recommendation display must make these fields visible to the user:

- candidate name when available
- candidate identifier when useful for audit or support
- team context when available
- outcome: recommendation or refusal
- primary category and category code when present
- assigned categories
- blocked categories or unavailable category context when present
- availability status
- confidence level
- confidence reasons when present
- freshness state
- data-through date when present
- latest successful sync when present
- explanations
- limitations
- refusal reason when present
- no-ranking state
- no-selection state

Fields may be organized by visual priority, but they must not be hidden behind
separate documentation pages.

## 4. Required Trust Indicators

The frontend must show trust indicators near the category or refusal outcome.

Required trust indicators:

- confidence level
- availability status
- freshness state
- data-through date when present
- limitation count or visible limitation text
- refusal reason when present

Trust indicators must distinguish data quality from baseball performance. A
high-confidence result means BaseballOS has enough trusted input for the stated
candidate-level policy output. It does not mean the candidate is guaranteed to
be the right baseball choice.

## 5. Required Freshness Indicators

Freshness must be visible on every recommendation, caution, avoidance, and
refusal state.

Required freshness display:

- freshness state label
- data-through date when present
- last successful sync when present
- latest sync status when present
- freshness limitation when data is stale, missing, incomplete, historical, or
  unknown

The frontend must keep data-through date separate from sync timestamp. A recent
sync timestamp must not be presented as proof that baseball workload data is
current.

## 6. Required Explanation Display

Explanations must be shown as first-class content, not only as diagnostics.

Explanation display requirements:

- show each explanation message returned by the API
- preserve stable explanation codes for audit, support, or expandable details
- keep explanation wording tied to the backend response
- show why category eligibility passed or failed
- show why a refusal failed closed
- show caution reasons before encouraging any use

The frontend must not generate new baseball reasoning outside the backend
response. It may format or group explanations, but it must not add unsupported
claims.

## 7. Required Limitation Display

Limitations must be visible for every state.

Required limitation themes:

- public workload data only
- not a medical or injury conclusion
- not a performance forecast
- not team-reported availability
- no private clubhouse, travel, warm-up, illness, or manager-intent context
- no guarantee that a pitcher will or will not pitch
- user remains responsible for the final decision
- no ranking, comparison, or final selection

Limitations may appear in a compact list, expandable panel, or inline trust
strip, but the presence of limitations must be obvious without requiring the
user to leave the recommendation surface.

## 8. Required Refusal Display

Refusal is a normal trust-first outcome and must have a first-class display
state.

Required refusal display:

- clear refusal label
- refusal reason
- freshness state
- confidence state
- availability state when available
- explanations
- limitations
- blocked categories when available
- no-ranking and no-selection indicators

Safe refusal labels include:

- "Insufficient trusted data"
- "Recommendation refused"
- "Current recommendation unavailable"
- "Freshness check failed"
- "Confidence too low for recommendation"

Refusal must not be displayed as an error unless the transport layer actually
failed.

## 9. Required Category Display

The frontend must present categories as eligibility or caution labels, not as
final selections.

Required category handling:

- show `category` and `category_code` when returned
- show assigned categories as candidate-level eligibility
- show blocked categories with reasons when available
- distinguish positive categories from cautionary and avoidance categories
- keep `BULLPEN_STRESS_ALERT` out of candidate-level display unless future
  policy explicitly authorizes candidate-level behavior

Category display must never imply that category eligibility selected the final
pitcher.

## 10. Required Metadata Display

The frontend must preserve and expose policy metadata at an appropriate display
level.

Required visible metadata:

- "No final pitcher selection made"
- "No bullpen ranking applied"

Required audit metadata, visible in details or support/debug surfaces:

- policy identifier
- policy version
- engine version
- response mode
- candidate pipeline state
- policy document reference when appropriate
- contract document reference when appropriate

The frontend must treat `ranking_applied=false` and `selection_made=false` as
display requirements, not only backend implementation details.

## 11. Prohibited UI Claims

The frontend must not show or imply:

- "Best pitcher tonight"
- "Guaranteed safest arm"
- "Projected result"
- "Will perform best"
- "Injury risk"
- "Manager should use"
- "System says to use this pitcher"
- "Final recommendation"
- "Bullpen ranking"
- "Ranked number one"
- "Safe to use"
- "Team availability confirmed"
- "Current" when freshness is stale, missing, historical, incomplete, or
  unknown

Prohibited claims also include visual patterns that create the same meaning,
such as winner badges, rank numbers, ordered bullpen lists, or primary action
buttons that tell the user whom to use.

## 12. Safe Labels And Copy Conventions

Allowed-style labels:

- "Candidate Evaluation"
- "Eligible Category"
- "Category Eligibility"
- "Use With Caution"
- "Avoid Tonight"
- "Insufficient trusted data"
- "No final pitcher selection made"
- "No bullpen ranking applied"
- "Freshness"
- "Confidence"
- "Limitations"
- "Explanation"

Safe copy rules:

- Use "eligible for" instead of "selected as".
- Use "candidate-level" when the scope could be confused with bullpen-level
  ranking.
- Use "current trusted workload data" when explaining freshness.
- Use "BaseballOS cannot make a current recommendation" for refusals.
- Use "The user remains responsible for the final decision" in limitations.
- Avoid command language that tells the user what decision to make.

## 13. Success State Display

A success state means the backend emitted candidate-level category eligibility.
It does not mean BaseballOS selected the final pitcher.

Required success state content:

- candidate identity
- outcome label
- eligible category or categories
- confidence indicator
- freshness indicator
- availability status
- explanations
- limitations
- no-ranking indicator
- no-selection indicator

Recommended success heading:

```text
Candidate Evaluation
```

Recommended category prefix:

```text
Eligible Category
```

## 14. Caution State Display

Caution states must be visually and textually distinct from normal positive
category eligibility.

Required caution state content:

- caution label
- availability status that caused caution when available
- confidence state
- freshness state
- caution explanation
- limitations
- no-ranking indicator
- no-selection indicator

Allowed caution labels:

- "Use With Caution"
- "Monitor"
- "Limited-use candidate"

The frontend must not use caution styling as a subtle positive recommendation.
Caution requires the reason to be visible.

## 15. Refusal State Display

Refusal states must be direct and trust-first.

Required refusal state content:

- refusal label
- refusal reason
- candidate identity when available
- blocked categories when available
- confidence state
- freshness state
- availability state when available
- explanations
- limitations
- no-ranking indicator
- no-selection indicator

Recommended refusal copy:

```text
BaseballOS cannot make a current recommendation because trusted current
workload data is insufficient.
```

Refusal must not be softened into speculative guidance.

## 16. Empty Or Unknown State Display

Empty and unknown states must fail closed in the user experience.

Required empty or unknown state behavior:

- do not show an empty recommendation list as a neutral success
- do not show placeholder category eligibility
- do not invent candidate names, categories, reasons, or limitations
- show that trusted data is missing or unavailable
- show no-ranking and no-selection indicators when displaying API output

Safe empty-state labels:

- "No candidate evaluation available"
- "Trusted recommendation data unavailable"
- "Insufficient trusted data"

## 17. Mobile Display Requirements

Mobile layouts must preserve trust visibility.

Required mobile behavior:

- candidate identity, outcome, confidence, freshness, and primary category or
  refusal reason must be visible without horizontal scrolling
- limitations must be reachable from the same card or panel
- explanations must remain readable at small widths
- no-ranking and no-selection indicators must not disappear on mobile
- category labels must wrap rather than truncate into misleading text
- refusal and caution states must remain visually distinct
- touch targets must be large enough for reliable selection

Mobile layouts may collapse secondary audit metadata, but they must not hide
trust, freshness, limitations, refusal reasons, or no-selection status.

## 18. Accessibility Requirements

Recommendation display must be accessible by default.

Accessibility requirements:

- use semantic headings for candidate, outcome, explanation, limitation, and
  metadata sections
- do not rely on color alone to communicate success, caution, avoidance, or
  refusal
- provide text labels for status icons
- keep contrast sufficient for confidence, freshness, caution, and refusal
  labels
- make expandable explanation and limitation sections keyboard accessible
- expose status changes to assistive technologies when responses load or
  refresh
- preserve readable date and time formats
- keep table or list structures navigable on small screens

Accessibility copy must preserve the same policy meaning as the visual display.

## 19. Governance Requirements

Frontend implementation must satisfy these governance requirements before
merge:

- consume the API response instead of recalculating recommendations
- display candidate-level evaluation only
- prove `ranking_applied=false` and `selection_made=false` remain visible
- test success, caution, refusal, stale, low-confidence, unavailable, and
  missing-data states
- test mobile layout for trust, freshness, explanation, limitation, and refusal
  visibility
- test accessibility for status labels and expandable content
- update this contract before changing display semantics
- keep category labels stable unless policy changes first

No frontend implementation may bypass backend policy by turning availability or
category eligibility into final usage guidance.

## 20. Future Expansion Boundaries

Future frontend expansion requires separate policy and contract work before
implementation.

Deferred frontend surfaces:

- bullpen-level recommendation dashboard
- multi-candidate comparison
- ranked bullpen list
- team-level stress summary
- simulator integration
- role-aware recommendation display
- rest-of-series planning display
- matchup-aware guidance
- public recommendation API consumer surface

Expansion must preserve deterministic backend output, visible explanations,
visible limitations, freshness transparency, confidence disclosure, refusal
visibility, and fail-closed behavior when trusted data is insufficient.
