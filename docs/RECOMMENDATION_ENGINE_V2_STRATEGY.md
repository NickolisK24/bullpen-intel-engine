# Recommendation Engine V2 Strategy

## 1. Executive Summary

Recommendation Engine V2 is the next BaseballOS recommendation planning
milestone after the completed, certified, and production-ready Recommendation
Engine V1.

This document defines strategy and scope only. It does not authorize V2
implementation, recommendation behavior changes, API behavior changes,
frontend behavior changes, or new recommendation logic.

The governance-boundary companion document is:

- `docs/RECOMMENDATION_ENGINE_V2_GOVERNANCE_BOUNDARIES.md`

The architecture companion document is:

- `docs/RECOMMENDATION_ENGINE_V2_ARCHITECTURE.md`

V2 exists to explore broader bullpen and team context while preserving the
trust contract certified in V1:

- deterministic behavior
- explainability
- trust visibility
- governance
- auditable outcomes
- fail-closed principles
- user control over the final baseball decision

BaseballOS may organize workload and availability intelligence. BaseballOS
must not become the decision maker.

## 2. Current Certified Baseline

The current certified baseline is Recommendation Engine V1.

Recommendation Engine V1 is certified for candidate-level evaluation in the
pitcher detail workflow. It evaluates one pitcher candidate at a time and
exposes category eligibility or refusal output using trusted BaseballOS
surfaces:

- Availability Engine V1 status
- availability confidence
- freshness state
- data-through date
- explanations
- limitations
- refusal reasons
- deterministic workload inputs

The certified V1 trust guarantees are:

```text
ranking_applied=false
selection_made=false
```

These guarantees are intentional trust protections. They make clear that
BaseballOS has not ranked the bullpen, has not selected a pitcher, and has not
replaced the user's judgment.

V2 planning must preserve this baseline.

## 3. Why V2 Exists

Recommendation Engine V1 proved that BaseballOS can move from availability
intelligence into decision-support intelligence without hiding uncertainty or
claiming unsupported baseball knowledge.

V2 exists because candidate-level evaluation is not the full bullpen planning
problem. Users also need to understand broader bullpen state:

- how many trusted options are currently available
- where workload stress is concentrated
- whether leverage resources are thin
- whether recent usage is uneven across the bullpen
- which groups of pitchers satisfy the same transparent eligibility criteria
- what readiness context should be visible before a human decision is made

V2 should explore these broader views while keeping V1's no-ranking and
no-selection restrictions intact.

## 4. Strategic Vision

Recommendation Engine V2 should become the planning foundation for
trust-first bullpen intelligence beyond a single candidate.

The strategic vision is not an automated pitching-change system. It is a
clearer decision-support layer that helps a user see:

- bullpen inventory
- workload distribution
- availability constraints
- leverage-resource visibility
- team-level stress
- grouped candidate eligibility
- why BaseballOS can or cannot support each view with trusted data

The system should remain deterministic and explainable. It should prefer
refusal or limitation disclosure over unsupported baseball opinions.

## 5. V2 Goals

V2 planning may define future capabilities that:

- expose bullpen-state intelligence
- improve bullpen inventory visibility
- show bullpen stress awareness
- expose leverage resource visibility
- show workload distribution visibility
- support grouped eligibility reporting
- support bullpen readiness reporting
- broaden recommendation explainability
- preserve visible confidence, freshness, limitations, and refusal reasons
- distinguish organizing information from ranking information
- keep the user as the final decision maker

V2 should make the bullpen picture easier to audit, not harder.

## 6. V2 Non-Goals

V2 does not yet include:

- pitcher rankings
- pitcher ordering
- automated pitcher selection
- game outcome prediction
- injury prediction
- save prediction
- performance forecasting
- opaque recommendation scores
- unsupported baseball opinions
- private clubhouse, medical, travel, warm-up, or manager-intent inference
- hidden composite ranking formulas
- changes to certified V1 behavior
- implementation of new backend, API, or frontend behavior in this milestone

These exclusions are product trust boundaries, not missing implementation
details.

## 7. Trust Boundaries

V2 must remain bounded by public workload and BaseballOS availability evidence
unless future governance explicitly adds and certifies new data sources.

Required trust boundaries:

- Policy and scope must precede implementation.
- Deterministic rules must be documented before use.
- Any grouped or team-level output must explain its inputs.
- Confidence and freshness must stay visible.
- Limitations must stay attached to the output they qualify.
- Refusal must remain a valid outcome.
- Stale, missing, low-confidence, or unsupported data must fail closed.
- Recommendation wording must not imply team intent or private knowledge.
- V2 must not silently convert organization into ranking.
- The user remains responsible for the final baseball decision.

Any future V2 implementation must prove that these boundaries are preserved
before production authorization.

## 8. Bullpen-Level Intelligence Definition

Bullpen-level intelligence describes the current state of one bullpen as a
group, using BaseballOS workload, availability, confidence, and freshness
surfaces.

Allowed bullpen-level intelligence may include:

- counts of pitchers by availability status
- counts of pitchers by recommendation eligibility group
- counts of available leverage arms when the criteria are documented
- recent workload distribution across the bullpen
- bullpen stress indicators based on constrained availability
- readiness summaries based on trusted current data
- grouped refusal or limitation reasons when current data is insufficient

Bullpen-level intelligence must not claim:

- which pitcher should be used
- which pitcher is best
- which pitcher the team will use
- which pitcher is healthy or injured
- which pitcher will perform best

The purpose is to make the bullpen state visible, not to make the final
selection.

## 9. Team-Level Intelligence Definition

Team-level intelligence describes a broader team readiness context derived from
the bullpen picture.

Allowed team-level intelligence may include:

- team bullpen stress awareness
- leverage resource visibility
- current availability distribution
- workload compression across multiple relievers
- uneven workload distribution visibility
- readiness summary language when current data is trusted
- refusal language when current data cannot support a team-level view

Team-level intelligence must not become:

- game outcome prediction
- win probability guidance
- save prediction
- manager-intent inference
- roster or transaction guidance
- matchup advice
- performance forecasting

Team-level context should help the user understand constraints around the
bullpen, not replace the user's decision.

## 10. Prioritization Without Ranking

V2 may need to organize information so users can scan the bullpen efficiently.
That is allowed only when the organization does not become a pitcher ranking,
ordering, or automated selection.

BaseballOS may organize information by transparent groups, counts, statuses,
readiness bands, or workload constraints. V2 must not assert that one pitcher
should be used over another.

Allowed examples:

```text
Three pitchers currently qualify for Fresh High-Leverage Arm criteria.
```

```text
Current bullpen inventory contains two available leverage arms.
```

Not allowed:

```text
Pitcher A should be used over Pitcher B.
```

```text
Pitcher A is the best choice.
```

```text
Pitcher A ranks #1.
```

The distinction is:

- organizing information groups or summarizes known facts
- ranking information orders options by preference or superiority

BaseballOS may organize. BaseballOS must not become the decision maker.

## 11. Candidate Capability Areas

The following areas are valid candidates for future V2 planning. They remain
planning candidates until separately scoped, implemented, tested, and
certified:

- Bullpen inventory visibility: show how many trusted current options exist by
  availability, confidence, freshness, and documented eligibility group.
- Bullpen stress awareness: summarize when too many pitchers are constrained by
  workload, availability, freshness, or confidence.
- Leverage resource visibility: identify the count or group of pitchers meeting
  documented leverage-resource criteria without ranking them.
- Workload distribution visibility: expose whether recent workload is
  concentrated on a small subset of the bullpen.
- Grouped eligibility reporting: show which pitchers qualify for the same
  transparent category or why grouped eligibility cannot be trusted.
- Bullpen readiness reporting: summarize current readiness from trusted data,
  including limitations and refusal states.
- Broader explainability: carry group-level reasons, limitations, freshness,
  and confidence through any future V2 output.

Each capability must define its own allowed statements, prohibited statements,
required data, refusal conditions, and certification evidence before
implementation.

## 12. Deferred V3+ Capabilities

The following capabilities are deferred beyond V2:

- pitcher rankings
- automated pitcher ordering
- automated final pitcher selection
- matchup-aware recommendations
- game outcome prediction
- save prediction
- injury prediction
- performance forecasting
- rest-of-series simulation
- postseason-specific recommendation policy
- transaction, roster, or trade guidance
- private or paid data integrations
- opaque scoring models

Deferring these capabilities protects the V2 scope from becoming an
unsupported prediction or decision system before BaseballOS has the policy,
data, tests, and trust surfaces required to support that behavior.

## 13. Governance Requirements

Future V2 work must follow BaseballOS governance standards:

- Strategy and scope must be documented before implementation.
- Each proposed capability must include explicit goals and non-goals.
- Data inputs must be listed and justified.
- Deterministic rules must be documented.
- Trust fields must remain visible.
- Refusal behavior must be defined before implementation.
- Prohibited claims must be documented.
- Any thresholds, category rules, group definitions, or wording changes must be
  versioned or documented.
- Tests must verify trust boundaries, not just happy paths.
- Documentation must distinguish planning approval from production
  authorization.
- Implementation must remain centralized and auditable if future work is
  authorized.

V2 governance should preserve the V1 rule that policy comes before behavior.

## 14. Certification Requirements

No V2 behavior should be called complete, certified, or production-ready until
certification evidence proves:

- deterministic outcomes
- explainable grouped or team-level output
- visible confidence
- visible freshness
- visible limitations
- visible refusal reasons
- fail-closed behavior for stale, missing, low-confidence, malformed, or
  unsupported data
- preservation of no-ranking behavior
- preservation of no-selection behavior
- no unsupported baseball opinions
- no private team, medical, travel, warm-up, injury, or manager-intent claims
- documentation alignment across policy, implementation, API, frontend, and
  project-state surfaces
- tests covering allowed output and prohibited output

Certification must explicitly preserve:

```text
ranking_applied=false
selection_made=false
```

These values must remain certified guarantees for implemented V2 behavior.

## 15. Recommended Next Planning Phase

The recommended next phase is a focused Recommendation Engine V2 policy and
capability-definition milestone.

That phase should produce a V2 policy document that defines:

- the first V2 capability to pursue
- the exact user problem it addresses
- allowed statements
- prohibited statements
- required inputs
- freshness and confidence requirements
- refusal conditions
- grouping rules
- display requirements
- API contract expectations, if any
- certification evidence required before production use

The first V2 planning phase should prefer a narrow, auditable capability such
as bullpen inventory visibility, grouped eligibility reporting, or bullpen
stress awareness. It should not begin with pitcher ordering, ranking, or
automated selection.
