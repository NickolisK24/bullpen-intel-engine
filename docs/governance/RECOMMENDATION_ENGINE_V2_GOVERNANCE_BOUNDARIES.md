# Recommendation Engine V2 Governance Boundaries

## 1. Title

Recommendation Engine V2 Governance Boundaries.

## 2. Purpose

This document defines the governance rules for Recommendation Engine V2 before
any V2 architecture, API contract, frontend contract, or implementation work
begins.

It defines what V2 is allowed to do, what it is restricted from doing without
additional review, what it is forbidden from doing, and what must be certified
before implementation can begin.

This is a documentation and governance milestone only. It does not authorize
V2 logic, backend behavior changes, frontend behavior changes, API behavior
changes, or changes to certified Recommendation Engine V1 behavior.

## 3. Relationship to V1 Certification

Recommendation Engine V1 is complete, certified, and production-ready for
candidate-level evaluation.

The active certified V1 guarantees are:

```text
ranking_applied = false
selection_made = false
```

These guarantees remain active unless a later certified governance process
explicitly changes them.

Until that happens, all V2 planning, architecture, API contracts, frontend
contracts, implementation plans, tests, and certification artifacts must
preserve visible no-ranking and no-selection behavior.

V2 must not weaken V1's candidate-level trust certification. Future V2 output
may add grouped or team-level context only when it keeps the user's decision
authority intact.

## 4. Relationship to V2 Strategy

The V2 strategy foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_STRATEGY.md`

The V2 architecture foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`

The V2 API contract foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md`

The V2 frontend contract foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_FRONTEND_CONTRACT.md`

The V2 certification requirements foundation is:

- `docs/RECOMMENDATION_ENGINE_V2_CERTIFICATION_REQUIREMENTS.md`

That strategy defines the product direction for bullpen-level and team-level
recommendation planning. This governance-boundary document converts that
strategy into decision rules.

All future V2 architecture and implementation proposals must pass this
document before they can be treated as in-scope.

## 5. Core Governance Principle

BaseballOS may group, summarize, and explain trusted bullpen information.

BaseballOS must not rank, choose, or decide.

The user remains the final decision maker. V2 may improve visibility into
bullpen state, inventory, stress, readiness, workload distribution, and
category eligibility, but it must not turn those views into hidden pitcher
selection.

## 6. Allowed V2 Behaviors

V2 may allow the following behaviors when they remain deterministic,
explainable, auditable, and visibly bounded by trust metadata:

- bullpen-state summaries
- bullpen inventory visibility
- grouped eligibility summaries
- stress/readiness indicators
- workload distribution visibility
- leverage resource visibility
- candidate grouping by category
- broader trust/explanation output
- descriptive team-level bullpen context

Allowed V2 behavior must remain descriptive. It may tell the user what
BaseballOS can support from trusted workload and availability evidence. It
must not tell the user which pitcher to use.

## 7. Restricted V2 Behaviors

The following behaviors are restricted. They require additional governance,
architecture review, and certification before implementation:

- candidate ordering
- tie-breaking
- score-like outputs
- priority labels
- urgency labels
- comparative language
- team-level decision guidance
- visual layouts that imply ranking
- sorting that implies preference

Restricted behavior is not approved by this document. A future proposal must
define the exact behavior, data inputs, user-facing wording, failure modes,
metadata, tests, and certification criteria before any implementation begins.

## 8. Forbidden V2 Behaviors

V2 must not include:

- final pitcher selection
- automated pitcher choice
- pitcher ranking
- "best pitcher" claims
- performance forecasting
- injury prediction
- save prediction
- game outcome prediction
- unsupported baseball opinions
- opaque scoring systems
- hidden decision weights

Forbidden behavior must not appear in backend logic, API payloads, frontend
copy, UI layout, documentation, test fixtures, or roadmap wording that implies
current approval.

## 9. Prioritization Without Ranking Rules

V2 may organize information only when organization does not become ranking,
ordering, or selection.

Allowed examples:

```text
Three pitchers currently qualify for Freshest High-Leverage Arm criteria.
```

```text
Current bullpen inventory includes two available high-leverage arms.
```

```text
Bullpen stress is elevated due to limited fresh inventory.
```

Disallowed examples:

```text
Use Pitcher A over Pitcher B.
```

```text
Pitcher A is the top option.
```

```text
Pitcher A ranks first.
```

```text
Pitcher A should be prioritized ahead of Pitcher B.
```

The rule is explicit:

- BaseballOS may group, summarize, and explain.
- BaseballOS must not rank, choose, or decide.

Any future feature that could make users infer a preferred pitcher must be
treated as restricted or forbidden until separately governed.

## 10. Explainability Requirements

Every future V2 output must expose:

- why the output exists
- what data supports it
- what limitations apply
- what freshness state applies
- what confidence level applies
- whether any refusal/fail-closed state was triggered

Explanations must be attached to the output they qualify. V2 must not rely on
static methodology pages or hidden rules to explain grouped or team-level
recommendation context.

## 11. Freshness and Data-State Requirements

V2 must preserve the existing BaseballOS trust model for freshness and
data-state visibility.

Future V2 outputs must preserve:

- sync timestamp visibility
- data-through date visibility
- stale data warnings
- missing data warnings
- limitations when freshness is degraded
- refusal or downgraded confidence when data is insufficient

A sync timestamp must not substitute for a trusted baseball data-through date.
Stale, missing, incomplete, historical, failed, or unknown data states must be
visible to the user and must affect confidence or output eligibility.

## 12. Refusal and Fail-Closed Requirements

V2 must refuse, suppress, or downgrade outputs when:

- required data is missing
- freshness is stale beyond accepted thresholds
- workload evidence is incomplete
- category eligibility cannot be explained
- output would imply ranking or selection
- output would exceed certified V2 scope

Refusal is a valid product outcome. If BaseballOS cannot explain a V2 output
from trusted current data, the correct behavior is to withhold the output or
show a refusal reason instead of filling the gap with unsupported baseball
logic.

## 13. UI/UX Governance Requirements

Future V2 UI must not imply ranking through:

- numbered lists
- leaderboard-style layouts
- first/second/third ordering
- "top option" language
- visual emphasis that looks like a recommendation winner
- default sorting by implied quality

Allowed UI patterns may include:

- grouped cards
- neutral category sections
- alphabetic ordering
- status-based grouping
- clear limitation text
- visible trust metadata

Any UI that places one pitcher above another must explain the neutral ordering
rule, such as alphabetic ordering or status grouping. Visual hierarchy must
not create a hidden recommendation winner.

## 14. API Governance Requirements

Future V2 API responses must preserve explicit metadata for:

- `ranking_applied`
- `selection_made`
- `scope`
- `confidence`
- `freshness`
- `limitations`
- `explanations`
- `refusal_reasons`
- `data_state`
- `generated_at`

If ranking is not applied and no selection is made, this must be visible in
the API contract and response metadata:

```json
{
  "ranking_applied": false,
  "selection_made": false
}
```

No future V2 API response may hide ranking or selection state behind omitted
metadata. Scope, confidence, freshness, explanations, limitations, refusal
reasons, data state, and generated-at metadata must remain auditable.

## 15. Testing and Certification Requirements

Future implementation must include tests verifying:

- no ranking is applied
- no selection is made
- refusal states are returned correctly
- stale/missing data degrades or refuses output
- explanations are present
- limitations are present
- freshness metadata is present
- UI does not render ranking or selection language
- API metadata preserves governance fields

Certification must prove both allowed output and prohibited output behavior.
Passing functional tests is not enough if the implementation can still imply
ranking, selection, unsupported prediction, or hidden decision weighting.

## 16. Implementation Gate

Recommendation Engine V2 implementation must not begin until:

1. V2 governance boundaries are documented
2. V2 architecture is documented
3. V2 API contract is documented
4. V2 frontend contract is documented
5. certification criteria are documented
6. the user explicitly approves implementation

This gate applies to backend logic, API behavior, frontend behavior, UI layout,
tests, fixtures, and any code path that would expose V2 recommendation output.

## 17. Summary

Recommendation Engine V2 may expand BaseballOS from candidate-level
recommendation support toward broader bullpen and team-level visibility.

That expansion must remain trust-first. V2 may organize current evidence into
groups, summaries, stress/readiness indicators, and explanations. It must not
rank pitchers, choose pitchers, predict outcomes, hide weights, or present
unsupported baseball opinions.

The active governance default remains:

```text
ranking_applied = false
selection_made = false
```

Future V2 work must pass this document before architecture or implementation
begins.
