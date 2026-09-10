# BaseballOS V4 Phase 18 - Explanation API Frontend Integration Planning

## Phase Status

Phase status:

```text
V4_PHASE_18_EXPLANATION_API_FRONTEND_INTEGRATION_PLANNING_COMPLETE
```

Capability track:

```text
V4_EVIDENCE_AND_EXPLANATION_LAYER
```

Planning status:

```text
PLANNING_ONLY
NO_FRONTEND_IMPLEMENTATION
NO_BACKEND_IMPLEMENTATION
NO_API_IMPLEMENTATION
NO_DASHBOARD_CHANGES
```

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_19_FRONTEND_EXPLANATION_SURFACE_IMPLEMENTATION
```

Phase 18 defines how certified V4 explanation API payloads should be integrated
into future frontend surfaces. It does not implement frontend code, backend
code, API routes, Dashboard changes, route exposure changes, rollout approval,
or new explanation types.

## 1. Frontend Integration Scope

Phase 18 plans frontend integration for certified V4 explanation payloads only.

In scope:

- Availability explanation frontend access
- Team Operations Readiness explanation frontend access
- shared explanation UI patterns
- progressive disclosure
- compact governance display strategy
- limitation and fail-closed display strategy
- frontend contract expectations for certified explanation API responses
- future frontend test requirements

Out of scope:

- frontend implementation
- Dashboard redesign
- backend implementation
- API route implementation
- new explanation API routes
- uncertified explanation types
- Recommendation Explanations
- Risk Distribution Explanations
- recommendation behavior
- ranking behavior
- selection behavior
- prediction behavior
- pitcher-level advice
- matchup advice
- decision automation

Frontend explanation surfaces may explain existing governed states. They may
not decide what the user should do.

Every future frontend explanation surface must preserve and display where
appropriate:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

## 2. Candidate User Surfaces

| Candidate surface | Purpose | User value | Clutter risk | Governance risk | Recommended usage |
| --- | --- | --- | --- | --- | --- |
| Pitcher detail view | Explain a single pitcher's current availability state. | Gives focused context without expanding team-level dashboard rows. | Low if shown behind an action. | Moderate because pitcher-level surfaces can feel like advice if phrased poorly. | Recommended for Availability Explanations with neutral "Why this state?" access. |
| Availability status badge/card | Attach explanation access near existing availability status. | Helps users understand the state they already see. | Medium if every badge expands inline. | Moderate because repeated controls can imply comparison. | Use a compact action or icon button, not inline full evidence. |
| Operational Readiness section | Explain current team readiness context. | Connects V3 readiness status to certified V4 explanation evidence. | Low if summary-only by default. | Low when kept team-level. | Recommended primary home for Team Operations Readiness explanations. |
| Team readiness card | Add a focused explanation action to readiness summary. | Keeps explanation near the state being explained. | Medium if all scopes render by default. | Low when grouped by scope and neutral language. | Recommended with a single default summary and expandable scope list. |
| Evidence drawer | Present reasons, evidence, limitations, trust, freshness, confidence, and governance in one place. | Keeps dashboard short while retaining auditability. | Low by default, medium when open. | Low if labels remain explanatory. | Recommended for detailed explanation payloads. |
| "Why this state?" button | Open explanation details from status surfaces. | Clear user action without adding page length. | Low. | Low if button text stays neutral. | Recommended primary trigger language. |
| Explanation modal | Focus attention on one explanation. | Useful for narrow contexts and mobile if implemented accessibly. | Low by default. | Low if not used to compare pitchers. | Acceptable for pitcher detail or narrow flows. |
| Expandable detail panel | Inline progressive disclosure under a summary. | Useful where drawer infrastructure is not available. | Medium if many panels are stacked. | Moderate if repeated across pitcher lists. | Use sparingly; prefer one open explanation at a time. |

Not recommended:

- full evidence blocks directly on the Dashboard by default
- explanation tables for all pitchers at once
- side-by-side comparison surfaces for pitcher explanations
- visual priority indicators that compare explanation quality
- sort controls that order pitchers by explanation content

## 3. Default Visibility Strategy

Default frontend visibility should be short and operational.

Visible by default:

- short explanation summary
- explanation type
- state explained
- first primary reason or primary reason count
- limitation presence indicator
- trust/freshness/confidence status chips when already available in the
  response
- compact `explanation_only` governance indicator
- neutral "Why this state?" action

Not visible by default:

- full evidence list
- all reason objects
- all limitation objects
- full governance object
- debug-like timestamps
- certification notes
- large audit blocks
- raw route metadata unless needed for an unavailable state
- repeated governance prose across every card

Default visibility should help the user understand that an explanation exists
without turning the Dashboard into an evidence report.

## 4. Progressive Disclosure Strategy

Deeper explanation content should be accessed through explicit user action.

Recommended disclosure patterns:

- drawer for full explanation details from Dashboard or readiness surfaces
- modal for focused pitcher-detail explanation review
- accordion sections inside the drawer or modal
- expandable evidence panel only for narrow contexts where drawer or modal
  behavior is not available

Recommended detail structure:

1. Summary
2. Reasons
3. Evidence
4. Limitations
5. Freshness / Trust / Confidence
6. Governance

Disclosure rules:

- keep one explanation detail surface open at a time when possible
- lazy-load explanation payloads after the user asks for details
- never show all pitcher explanations inline by default
- keep fail-closed states concise but visible
- keep governance visible as a compact strip, with full governance object behind
  details

## 5. Availability Explanation UI Plan

Availability explanations should appear near the availability state they
explain, but should not become pitcher selection guidance.

Recommended surfaces:

- pitcher detail view
- availability status card or badge action
- high-fatigue or availability table row action only if it does not create
  ranking, comparison, or priority cues

Recommended interaction:

- show a compact "Why this state?" action near the availability state
- fetch the explanation lazily after the user activates the action
- open a drawer or modal with summary, reasons, evidence, limitations,
  freshness, trust, confidence, and governance
- keep the explanation scoped to the selected pitcher and current availability
  state

Availability explanation UI must not:

- compare pitchers by explanation content
- label a pitcher as best, preferred, recommended, safer, or optimal
- tell the user to use or avoid a pitcher
- imply hidden priority ordering
- provide matchup guidance

Unknown or missing pitcher handling:

- show an unavailable explanation state
- show returned limitations and refusal metadata
- preserve governance indicators
- do not fabricate a summary or evidence list
- do not fall back to another pitcher or team-level explanation

## 6. Team Readiness Explanation UI Plan

Team Operations Readiness explanations should appear in or near the existing
Operational Readiness section.

Recommended primary action:

```text
Why this state?
```

Recommended default scope:

```text
readiness_state
```

Certified scopes available for future UI access:

- `readiness_state`
- `workload_state`
- `coverage_state`
- `freshness_state`
- `trust_state`

Recommended grouping:

| Scope | UI grouping | Default visibility |
| --- | --- | --- |
| `readiness_state` | Current readiness summary | Summary visible; details behind action. |
| `workload_state` | Workload pressure contributors | Hidden by default; accessible in details. |
| `coverage_state` | Coverage and handedness contributors | Hidden by default; accessible in details. |
| `freshness_state` | Freshness contributors | Chip visible when limited; details behind action. |
| `trust_state` | Trust and confidence contributors | Chip visible when limited; details behind action. |

Data-limited or degraded states should:

- show the readiness state and concise summary by default
- expose limitation count or limited-state indicator
- show returned limitations in the drawer or modal
- avoid presenting limitations as instructions
- avoid telling the user what decision to make

## 7. Fail-Closed UI Strategy

Future frontend surfaces must treat fail-closed API responses as first-class
safe states.

Fail-closed UI requirements:

- do not fabricate explanation content
- show a clear unavailable or limited explanation message
- show returned limitations when available
- show returned refusal metadata when available
- preserve governance language
- keep `explanation_only` visible where appropriate
- avoid fallback content that implies a recommendation
- avoid hiding the fail-closed state behind generic loading or error language

Recommended fail-closed language:

```text
Explanation unavailable for this state.
```

Recommended supporting language:

```text
Required explanation inputs were unavailable or not certified for this request.
```

Prohibited fail-closed behavior:

- inventing reasons
- inventing evidence
- substituting another scope without user action
- showing an empty "healthy" state
- recommending next actions
- using red/green language that implies a pitcher should or should not be used

## 8. Governance UI Strategy

Governance must remain visible without bloating the page.

Recommended approach:

- compact governance strip in the explanation detail surface
- concise default label such as `Explanation only`
- full governance object available in drawer or modal details
- do not repeat the full governance object on every Dashboard card
- use consistent neutral wording across Availability and Team Readiness
  explanations

Required governance values:

```text
ranking_applied === false
selection_made === false
recommendation_made === false
prediction_made === false
decision_scope === "explanation_only"
advice_scope === "none"
```

Recommended visible wording:

```text
Explanation only. No ranking, selection, recommendation, or prediction.
```

Governance display must not imply:

- the explanation selects a pitcher
- the explanation recommends a pitcher
- the explanation predicts performance
- the explanation ranks options
- the explanation is a decision instruction

## 9. UX Anti-Regression Rules

The Dashboard was previously consolidated to avoid reading like a certification
or audit report. V4 explanation frontend integration must preserve that
improvement.

Anti-regression rules:

- do not add full explanation blocks directly to the Dashboard by default
- do not display full evidence lists inline by default
- do not repeat full governance text across multiple large sections
- do not add certification notes as default Dashboard content
- do not create one explanation card per pitcher on the main Dashboard
- do not create comparison tables for explanation content
- prefer drawers, modals, or compact expandable panels for evidence detail
- keep the first viewport focused on operational state
- keep readiness summary and availability summary concise
- show limitation indicators without making every limitation a top-level block
- make detailed evidence discoverable without forcing it into the scroll path
- preserve mobile page length by lazy-loading and collapsing detail surfaces

The UI should feel like an operational dashboard first and an evidence review
surface second.

## 10. Frontend Contract Requirements

Future frontend code should consume the certified API envelopes without
loosening contract expectations.

Required fields to normalize:

- `status`
- `explanation_type`
- `certification_status`
- `route_status`
- `explanation`
- `limitations`
- `refusal`
- `governance`

Explanation object fields expected when `status === "ok"`:

- `explanation_id`
- `scope`
- `subject_type`
- `subject_id`
- `state_explained`
- `summary`
- `primary_reasons`
- `supporting_evidence`
- `limitations`
- `freshness`
- `trust`
- `confidence`
- `governance`
- `generated_at`

Fail-closed response handling:

- accept `status: "unavailable"`
- require `explanation: null`
- preserve `limitations`
- preserve `refusal`
- preserve envelope-level `governance`
- mark missing or malformed governance as unsafe

Frontend normalization must not:

- add recommendation fields
- infer rank from evidence
- sort pitchers by explanation content
- hide unsupported or uncertified scope failures
- treat malformed governance as valid

## 11. Testing Requirements

Future frontend implementation should include tests for:

- rendering a concise explanation summary
- opening and closing the explanation drawer or modal
- rendering evidence only after user action
- rendering reasons after user action
- rendering limitations
- rendering freshness, trust, and confidence metadata
- rendering fail-closed unavailable responses
- rendering governance-safe messaging
- preserving `ranking_applied === false`
- preserving `selection_made === false`
- preserving `recommendation_made === false`
- preserving `prediction_made === false`
- preserving `decision_scope === "explanation_only"`
- preserving `advice_scope === "none"`
- refusing or degrading malformed governance metadata
- avoiding best/preferred/recommended language
- avoiding ranking, selection, prediction, recommendation, pitcher advice, and
  matchup advice language
- keeping Dashboard rendering stable when explanation UI is absent, closed, or
  fail-closed
- ensuring keyboard access for drawer/modal triggers and close controls
- ensuring mobile layout keeps explanation details collapsed by default
- preventing full evidence lists from rendering inline by default

Implementation should also include a regression check that the Dashboard first
viewport remains focused on operational status, not full evidence blocks.

## 12. Implementation Readiness Decision

Implementation readiness decision:

```text
READY_FOR_V4_PHASE_19_FRONTEND_EXPLANATION_SURFACE_IMPLEMENTATION
```

Rationale:

- the backend explanation integrations are certified with non-blocking
  observations
- the Explanation API layer is certified with non-blocking observations
- certified explanation types and scopes are known
- safe default visibility and progressive disclosure rules are defined
- fail-closed UI behavior is specified
- governance display expectations are defined
- dashboard length and clutter risks are explicitly controlled by
  anti-regression rules
- future frontend tests are defined before implementation begins

Phase 18 does not authorize frontend implementation by itself. It authorizes a
future implementation prompt to build only the planned governed frontend
explanation surface.

Recommended next milestone:

```text
V4 Phase 19 - Frontend Explanation Surface Implementation
```
