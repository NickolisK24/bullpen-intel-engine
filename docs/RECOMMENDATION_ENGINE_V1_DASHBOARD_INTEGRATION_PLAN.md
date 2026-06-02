# Recommendation Engine V1 Dashboard Integration Plan

## 1. Dashboard Integration Objective

Recommendation Engine V1 dashboard integration should expose candidate-level
recommendation evaluation from the existing BaseballOS frontend without
changing backend policy meaning or expanding the recommendation surface beyond
one pitcher at a time.

The integrated dashboard experience must let a user choose one pitcher
candidate, request evaluation, and inspect the returned recommendation or
refusal output with confidence, freshness, explanations, limitations,
categories, and metadata visible.

The dashboard must preserve:

- candidate-level evaluation only
- no bullpen ranking
- no final pitcher selection
- visible confidence
- visible freshness
- visible explanations
- visible limitations
- visible refusal reasons
- `ranking_applied=false`
- `selection_made=false`

## 2. Explicit Non-Goals

This plan does not authorize:

- dashboard implementation
- frontend behavior changes
- backend behavior changes
- API behavior changes
- database changes
- multi-candidate recommendation requests
- bullpen comparison
- ranked recommendation lists
- final pitcher selection
- scoring formulas
- performance forecasting
- injury, medical, illness, or team-reported availability claims
- matchup guidance
- simulator integration
- team-level recommendation output
- public recommendation publishing

This document is planning only.

## 3. Recommended Dashboard Location

V1 should integrate Recommendation Engine display inside the existing pitcher
detail workflow, not as a top-level dashboard ranking section.

Recommended location:

- existing surface: `frontend/src/components/bullpen/PitcherDetail.jsx`
- placement: below `AvailabilitySummary` and above deeper workload breakdowns
- component: existing `frontend/src/components/recommendations/RecommendationPanel.jsx`
- data source: the same single pitcher detail payload already used by the
  detail panel, normalized into the candidate request shape

This location keeps the evaluation tied to exactly one candidate the user has
already selected. It also places recommendation context next to availability,
fatigue, freshness, reasons, and limitations without implying that the bullpen
was ranked.

## 4. Recommended Navigation And Location Strategy

Dashboard navigation should remain conservative for V1.

Recommended strategy:

- Do not add a primary top-level navigation item for V1 dashboard integration.
- Keep existing Dashboard and Bullpen navigation unchanged during the first
  integration step.
- Let users arrive at Recommendation Engine output by opening a pitcher detail
  panel from an existing bullpen or dashboard pitcher row.
- If a future entry point is needed, use a neutral label such as "Candidate
  Evaluation" or "Evaluate Candidate" from a pitcher-specific context only.
- Do not add a dashboard card that lists recommended pitchers.
- Do not add a dashboard-wide recommendation summary.

The integrated view may include a compact section heading inside pitcher detail:

```text
Candidate Evaluation
```

The heading must not say or imply that the candidate has been selected as the
final pitcher.

## 5. Candidate Selection Workflow

V1 candidate selection should reuse existing user intent: the user selects a
single pitcher from an existing BaseballOS pitcher surface.

Recommended workflow:

1. User opens the Bullpen page or a dashboard pitcher row.
2. User selects exactly one pitcher.
3. Existing pitcher detail data loads.
4. The detail surface offers a neutral candidate evaluation action.
5. The action builds one candidate payload from existing pitcher, availability,
   confidence, freshness, and workload data.
6. The frontend calls `evaluateRecommendationCandidate(candidate)` once.
7. `RecommendationPanel` renders success, caution, refusal, loading, error, or
   empty state from controlled response state.

Evaluation trigger:

- user-initiated by default
- no automatic evaluation for every pitcher row
- no bulk request for a bullpen list
- no background precomputation of multiple candidates

Refusal output must render in the same location as success output. It is a
normal trust-first outcome, not an application failure.

## 6. Data Flow Architecture

Dashboard integration should use a one-way data flow:

1. Existing pitcher detail request loads pitcher, current fatigue,
   availability, recent logs, and freshness context.
2. A frontend mapping helper builds one candidate object from the selected
   pitcher detail payload.
3. The helper sends the candidate through `evaluateRecommendationCandidate()`.
4. The API route returns the structured Recommendation Engine response.
5. `RecommendationPanel` renders response state from props.

Data flow rules:

- Do not duplicate recommendation request construction in multiple components.
- Do not compute categories in the dashboard.
- Do not derive refusal reasons in the dashboard.
- Do not mutate availability, confidence, freshness, or workload values before
  calling the API.
- Do not send arrays of candidates.
- Do not cache responses in a way that hides freshness changes.

The dashboard should treat backend response fields as authoritative for
recommendation display.

## 7. Frontend Component Integration Boundaries

Recommended component boundaries:

| Component | Responsibility |
| --- | --- |
| `PitcherDetail` | Own selected pitcher context and existing detail loading state. |
| Candidate mapper helper | Convert one pitcher detail payload into one candidate request object. |
| Recommendation request controller | Own candidate evaluation trigger, loading state, response, and transport error state. |
| `RecommendationPanel` | Render response, refusal, loading, error, and empty states from controlled props. |

Boundary rules:

- `RecommendationPanel` remains presentational and independently testable.
- `PitcherDetail` may coordinate request state but must not compute policy
  output.
- Candidate mapper helpers may normalize field names only.
- No component may rank, compare, sort, or choose pitchers.
- No dashboard component may hide trust, freshness, limitation, or refusal
  fields returned by the API.

## 8. API Integration Boundaries

Dashboard integration must use the existing API contract:

```text
POST /api/recommendations/candidate
```

API integration rules:

- Send exactly one candidate per request.
- Use `evaluateRecommendationCandidate()` from `frontend/src/utils/api.js`.
- Preserve the existing request shape.
- Preserve the existing response shape.
- Treat 200 refusal responses as valid Recommendation Engine outcomes.
- Treat transport failure separately from policy refusal.
- Do not add new API routes.
- Do not modify backend route behavior.
- Do not add database writes.

The frontend may add a candidate mapping helper and request-state controller,
but it must not change the API contract.

## 9. Required Visible Trust Fields

Every API-backed dashboard recommendation display must show:

- candidate name
- availability status
- confidence level
- confidence reasons when present
- limitation text or limitation count with details
- no-ranking status
- no-selection status

Required visible labels:

- "Confidence"
- "Availability"
- "No bullpen ranking applied"
- "No final pitcher selection made"

Trust fields should be adjacent to the candidate evaluation status. They must
not be relegated to a separate methodology page.

## 10. Required Visible Freshness Fields

Every API-backed recommendation display must show freshness.

Required freshness fields:

- freshness state
- data-through date when present
- latest successful sync when present
- latest sync status when present
- freshness limitation when stale, missing, incomplete, historical, or unknown

The dashboard must distinguish data-through date from sync timestamp. A recent
sync timestamp must not be used as proof that baseball workload data is current.

## 11. Required Explanation Display

Dashboard integration must show backend explanations as first-class content.

Explanation display rules:

- Show every explanation message returned by the API.
- Keep stable explanation codes available in details or audit expansion when
  useful.
- Keep caution explanations visible before any category label can be read as
  positive guidance.
- Refusal explanations must remain visible with the refusal reason.
- Do not add unsupported baseball reasoning in the frontend.

Explanations should stay near the result, not behind a separate route.

## 12. Required Limitation Display

Limitations must be visible for success, caution, refusal, loading fallback,
error, and empty states.

Required limitation behavior:

- Show limitations from the API response.
- Preserve no-ranking and no-selection limitations.
- Preserve user-decision limitation.
- Preserve public-workload-data limitation.
- Do not rely only on static methodology documentation.
- Do not hide limitations behind hover-only interactions.

Limitations may be compact, but their presence must be obvious.

## 13. Required Refusal Display

Refusal is a normal trust-first outcome.

Required refusal display:

- refusal label
- refusal reason
- candidate identity when available
- availability state when available
- confidence state
- freshness state
- blocked categories when available
- explanations
- limitations
- no-ranking status
- no-selection status

Safe refusal labels:

- "Insufficient trusted data"
- "Current recommendation unavailable"
- "Freshness check failed"
- "Confidence too low for recommendation"

Refusal must not be shown as a transport error unless the request itself
failed.

## 14. Required Metadata Display

The dashboard must visibly display:

- `ranking_applied=false` as "No bullpen ranking applied"
- `selection_made=false` as "No final pitcher selection made"

The dashboard may place these fields in a trust strip, but they must remain
visible whenever recommendation response data exists.

Optional audit metadata may appear in details:

- policy identifier
- policy version
- engine version
- response mode
- candidate pipeline state
- policy document reference
- API contract reference
- frontend contract reference

The dashboard must not show or imply selected pitcher metadata.

## 15. Loading And Error States

Loading state:

- Show that one candidate evaluation is in progress.
- Do not display placeholder category eligibility.
- Keep no-ranking and no-selection labels visible if prior API metadata is
  still displayed.
- Avoid row-level spinners for an entire bullpen list.

Error state:

- Show safe transport error copy.
- Do not expose stack traces.
- Do not convert a transport error into policy refusal.
- Provide a retry action only for the same selected candidate.

Empty state:

- Show "No candidate evaluation available" or equivalent safe copy.
- Do not show empty category lists as success.
- Do not invent confidence, freshness, explanation, or limitation values.

## 16. Mobile Integration Expectations

Mobile dashboard integration must preserve trust-first readability.

Mobile requirements:

- Candidate identity, outcome, confidence, freshness, and category or refusal
  reason remain visible without horizontal scrolling.
- Trust fields may wrap but must stay visible.
- Limitations and explanations remain readable in the same panel.
- No-ranking and no-selection indicators remain visible.
- Caution and refusal states remain visually distinct.
- Buttons use reliable touch targets.
- Category labels wrap instead of truncating into misleading text.

Secondary audit metadata may collapse into details, but trust, freshness,
limitations, refusal reasons, and no-selection status must not disappear.

## 17. Accessibility Requirements

Dashboard integration must meet the same accessibility requirements as the
rest of the BaseballOS frontend.

Requirements:

- Use semantic headings for candidate, outcome, trust, freshness, categories,
  explanations, limitations, refusal, and metadata.
- Do not rely on color alone for success, caution, avoidance, refusal, or
  freshness state.
- Provide text labels for any icons.
- Preserve readable contrast for all status labels.
- Make retry actions keyboard accessible.
- Announce loaded recommendation state changes when the selected candidate is
  evaluated.
- Keep focus order predictable when opening pitcher detail or retrying
  evaluation.
- Preserve readable date and time formats.

## 18. Testing Strategy

Recommended tests before dashboard integration merge:

- candidate mapper builds exactly one candidate from pitcher detail data
- missing required candidate fields fail safely before or through the API
- user-triggered evaluation calls `evaluateRecommendationCandidate()` once
- success state renders assigned categories, explanations, limitations,
  confidence, freshness, availability, no-ranking, and no-selection
- caution state renders caution reasons and limitations
- refusal state renders refusal reason, blocked categories, explanations,
  limitations, no-ranking, and no-selection
- loading state does not show placeholder recommendation output
- transport error state does not show policy refusal copy
- empty state remains neutral
- dashboard does not render a ranked list
- dashboard does not render a selected final pitcher
- mobile layout keeps trust and freshness visible
- accessibility checks cover headings, status labels, focus order, and retry
  behavior

Recommended validation:

- `npm run test`
- `npm run build`
- focused backend recommendation API tests only if route behavior is suspected
  to have changed
- `git diff --check`

No test should assert ranking, scoring, comparison, or final pitcher selection.

## 19. Governance Requirements

Dashboard integration must satisfy governance requirements before
implementation merge:

- Candidate-level scope remains explicit.
- Backend response remains source of truth.
- No dashboard component recomputes recommendation policy.
- No ranking or final selection copy appears.
- `ranking_applied=false` remains visible.
- `selection_made=false` remains visible.
- Confidence remains visible.
- Freshness remains visible.
- Limitations remain visible.
- Refusal reasons remain visible.
- Caution and refusal are visually and textually distinct.
- Stale, missing, low-confidence, and unavailable states fail closed in display.
- Documentation is updated before changing dashboard semantics.

Governance review should inspect both copy and visual hierarchy because layout
can imply ranking or final selection even when text does not.

## 20. Future Expansion Boundaries

Future expansion requires separate policy, contract, and implementation
planning.

Deferred expansions:

- dashboard-wide recommendation summary
- bullpen-level recommendations
- multi-candidate comparison
- ranked bullpen lists
- team-level stress recommendation panels
- simulator integration
- role-aware recommendation display
- matchup-aware guidance
- rest-of-series planning
- public consumer surfaces
- external data integration

Any future expansion must preserve deterministic backend output, visible
explanations, visible limitations, freshness transparency, confidence
disclosure, no-ranking/no-selection clarity, and fail-closed behavior when
trusted data is insufficient.

## Recommended V1 Placement Decision

Three options were evaluated for V1 dashboard integration.

### Option A: Dedicated Recommendation Section

Description:

- Add a new dedicated dashboard or route section for Recommendation Engine V1.
- Let the user choose one candidate from that section.
- Render `RecommendationPanel` as the main content.

Benefits:

- Clean separation from existing bullpen and pitcher detail surfaces.
- Easy to keep copy focused on candidate-level evaluation.
- Easier to test as a standalone page.

Risks:

- A dedicated recommendation surface may look like a destination for finding
  the recommended arm.
- Candidate selection may drift toward multi-candidate browsing.
- Additional navigation can make V1 appear broader than candidate-level
  evaluation.

Verdict:

- Useful later, but not recommended for first dashboard integration.

### Option B: Embedded Panel Within Pitcher Detail Workflow

Description:

- Add the recommendation panel to the existing single-pitcher detail workflow.
- Evaluate only the pitcher currently open in detail view.
- Keep recommendation output next to availability, fatigue, recent workload,
  explanations, and limitations.

Benefits:

- Naturally enforces one-candidate context.
- Uses an existing user-selected pitcher instead of creating a candidate search
  workflow.
- Minimizes risk of implying bullpen ranking.
- Keeps trust and workload context nearby.
- Allows refusal and caution output to be interpreted with availability
  evidence visible.

Risks:

- Pitcher detail can become dense if the panel is always expanded.
- The evaluation trigger must remain user-controlled to avoid bulk calls.
- Copy must stay clear that category eligibility is not final selection.

Verdict:

- Recommended for V1 dashboard integration.

### Option C: Availability Page Integration

Description:

- Integrate Recommendation Engine display near availability summaries or
  availability-filtered bullpen views.
- Let users evaluate candidates from availability status context.

Benefits:

- Availability status is a core input to recommendation policy.
- Existing availability displays already emphasize trust, confidence, and data
  state.

Risks:

- Availability summaries can imply group-level sorting or recommendation.
- Filtering by status may look like candidate ranking.
- It creates pressure to evaluate multiple pitchers at once.

Verdict:

- Not recommended for V1. Consider later only after candidate-level dashboard
  behavior has proven safe.

Final recommendation:

```text
Use Option B: Embedded panel within the pitcher detail workflow.
```

Rationale:

Option B best preserves V1 policy boundaries because the user has already
selected exactly one pitcher, the panel can render next to availability and
workload context, and the layout does not require a ranked or comparable
bullpen view. It is the lowest-risk path for exposing candidate-level
Recommendation Engine output in the existing BaseballOS dashboard.
