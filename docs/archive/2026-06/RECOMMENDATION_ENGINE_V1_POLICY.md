# Recommendation Engine V1 Policy

## 1. Purpose

Recommendation Engine V1 moves BaseballOS from availability intelligence into
decision-support intelligence while preserving the trust rules that already
govern fatigue, freshness, and availability.

The engine may recommend workload-informed bullpen options. It must not decide
for the user, imply private team knowledge, or present public workload data as a
complete baseball decision.

BaseballOS recommends; it does not decide. The user remains the decision maker.

## 2. Scope

This policy defines the allowed behavior for Recommendation Engine V1 before
any implementation work begins.

V1 recommendations are limited to current bullpen decision support derived from
BaseballOS trust surfaces:

- fatigue score and fatigue components
- Availability Engine V1 status
- availability confidence, reasons, limitations, and data state
- recent workload, rest, pitch volume, and appearance compression
- sync metadata, data-through date, and freshness state
- pitcher roster and team context already tracked by BaseballOS

This document governs recommendation eligibility, exclusions, confidence,
freshness, refusal behavior, categories, explanations, limitations, prohibited
claims, and future expansion boundaries.

It does not define scoring formulas, ranking formulas, database schema, API
contracts, frontend presentation, or implementation tests.

## 3. Non-Goals

Recommendation Engine V1 does not provide:

- injury predictions
- medical, illness, or team-reported availability conclusions
- performance forecasts
- ERA projections
- save projections
- generated baseball opinions or editorial baseball takes
- black-box rankings
- private clubhouse, travel, warm-up, or manager-intent inference
- automated lineup, roster, or pitching-change decisions
- implementation logic, backend routes, frontend UI, database changes, or
  behavior tests

## 4. Eligibility Rules

A pitcher is eligible for V1 recommendation consideration only when all required
trust inputs are present and current enough for decision support.

Required eligibility conditions:

- The pitcher is a tracked current-season pitcher in BaseballOS.
- The pitcher has a known team context for the requested recommendation scope.
- The pitcher has workload history sufficient to compute availability.
- The pitcher has an Availability Engine V1 output with status, confidence,
  data state, reasons, limitations, and deterministic inputs.
- The data-through date is available and passes the current freshness policy.
- The recommendation can explain why the pitcher is included or excluded using
  deterministic BaseballOS inputs.

Eligibility is not a claim that the pitcher will be used, should be used, is
healthy, is on the active game roster, or is preferred by the team.

## 5. Exclusion Rules

V1 must exclude a pitcher from positive recommendation categories when any of
the following conditions apply:

- Availability status is `Avoid` or `Unavailable`.
- Availability confidence is low or unknown.
- Data state is stale, missing, historical, incomplete beyond allowed policy, or
  unknown.
- The pitcher lacks enough workload history to support an explanation.
- The pitcher identity, team, roster context, or latest workload date is
  ambiguous.
- The category would require information BaseballOS does not possess.

Excluded pitchers may still appear in cautionary categories only when the data
is trusted enough to explain the caution. If the data is not trusted, V1 must
refuse rather than produce a caution label from weak evidence.

## 6. Availability Influence

Availability Engine V1 status is a gate, not a hidden ranking score.

Recommendation Engine V1 must not override availability. It may only layer
decision-support wording on top of availability output that is already
deterministic, explainable, and current.

Availability influence by status:

| Availability status | Recommendation effect |
| --- | --- |
| `Available` | May be considered for positive workload-based categories when confidence and freshness pass. |
| `Monitor` | May be considered for positive or cautionary categories only when the explanation clearly names the monitoring reason. |
| `Limited` | Must not be presented as a normal-use option; may appear only in `Use With Caution` or broader stress context. |
| `Avoid` | Must not appear in positive categories; may appear in `Avoid Tonight` or team stress context. |
| `Unavailable` | Must not appear as a usable option; may appear only as an unavailable workload constraint in team stress context. |

Freshness or confidence failures take precedence over all status-based
recommendations.

## 7. Confidence Requirements

Every recommendation must carry an explicit confidence state inherited from, or
more conservative than, the underlying availability and freshness state.

V1 confidence policy:

- High confidence is required for positive categories that name a preferred
  option.
- Medium confidence may support cautionary guidance when the uncertainty is
  explained.
- Low or unknown confidence must fail closed and refuse current
  recommendation output.
- Recommendation confidence must never exceed availability confidence.
- Missing explanation detail must lower confidence or trigger refusal.

Confidence is a trust statement about BaseballOS data quality and policy
coverage. It is not a probability that the recommendation will be correct.

## 8. Data Freshness Requirements

Recommendation Engine V1 must be freshness-aware by default.

Required freshness rules:

- Current recommendations require a trusted data-through date.
- Sync timestamp and data-through date must remain distinct.
- A recent sync timestamp cannot substitute for missing or stale baseball data.
- Stale, missing, historical, or unknown freshness state must suppress current
  recommendations.
- If the latest sync failed but prior trusted data remains available, the
  output must disclose that condition and may recommend only if the
  data-through date still passes freshness policy.
- If freshness cannot be explained to the user, the engine must refuse.

V1 must never present stale workload context as current bullpen guidance.

## 9. Refusal Conditions

V1 must refuse to produce a recommendation when trusted data is insufficient.

Refusal is required when:

- required workload, availability, confidence, or freshness inputs are missing
- data state is stale, missing, historical, or unknown
- confidence is low or unknown
- the requested category is outside V1 scope
- all candidates are excluded from the requested category by availability or
  data policy
- the explanation would require private team, medical, injury, travel, warm-up,
  manager-intent, or performance information
- the user asks for a forecast, projection, prediction, or team decision
- the recommendation cannot include mandatory limitations

Acceptable refusal wording must be direct and trust-first:

```text
BaseballOS cannot make a current recommendation because trusted current
workload data is insufficient.
```

Refusal must not be softened into speculative guidance.

## 10. Recommendation Categories For V1

The final V1 recommendation categories are:

### Best Available Arm

Identifies the primary workload-available option under BaseballOS policy. This
category is allowed only for high-confidence, fresh, explainable candidates
whose availability status is `Available` or carefully qualified `Monitor`.

This label must not mean best pitcher, best matchup, best projected
performance, or team-preferred reliever.

### Freshest High-Leverage Arm

Identifies the freshest workload-eligible arm to consider for a high-leverage
planning context. This category is allowed only when workload freshness,
availability status, and confidence pass policy.

This label must not imply leverage skill, role certainty, manager intent, or
game-specific matchup superiority.

### Lowest Current Workload Risk

Identifies the eligible pitcher with the least current workload concern under
BaseballOS inputs. This category is limited to workload risk. It does not
measure injury risk, performance risk, command risk, matchup risk, or role fit.

### Use With Caution

Identifies pitchers whose workload signals do not require full avoidance but
make normal use questionable. This category is appropriate for `Monitor` or
`Limited` outcomes when the reasons and limitations are clear.

### Avoid Tonight

Identifies pitchers whose current public workload profile makes use tonight a
clear workload concern. This category is appropriate for `Avoid` and may include
`Unavailable` as a stronger workload constraint.

This label must not imply injury, roster inactivation, or a team-reported
decision.

### Bullpen Stress Alert

Identifies team-level bullpen stress when enough pitchers are constrained by
availability, workload, confidence, or freshness policy that the bullpen picture
itself requires caution.

This category is a team-context warning, not an individual usage command.

## 11. Mandatory Explanations

Every V1 recommendation must explain itself in user-visible language.

Required explanation fields:

- recommendation category
- pitcher or team scope
- availability status
- availability confidence
- data state
- data-through date
- last successful sync when available
- primary workload reasons
- relevant limitations
- deterministic inputs used for the recommendation
- refusal reason when no recommendation is allowed

Positive recommendations must also explain why excluded nearby options were not
selected when that context is necessary to avoid overclaiming.

Cautionary recommendations must name the exact workload or data-state concern
that created the caution.

## 12. Mandatory Limitations

Recommendation output must include limitations whenever a user could reasonably
mistake the result for a complete baseball decision.

Mandatory limitation themes:

- Based on public workload data tracked by BaseballOS.
- Not a medical or injury conclusion.
- Not a performance forecast.
- Not a team-reported availability status.
- Does not know bullpen warm-ups, travel, illness, clubhouse context, or manager
  intent.
- Does not guarantee the pitcher will or will not pitch.
- The user remains responsible for the final decision.

Limitations must be attached to the recommendation result, not hidden in a
separate methodology page.

## 13. Prohibited Recommendation Claims

V1 must not claim or imply:

- a pitcher is injured, healthy, cleared, shut down, or team-unavailable
- a team will use or will not use a pitcher
- a manager should make a specific pitching change
- a pitcher is guaranteed safe to use
- a pitcher is the best baseball option independent of workload context
- a pitcher is likely to allow or prevent runs
- a pitcher is likely to earn a save, hold, win, or loss
- a recommendation is based on private team information
- stale or incomplete data is current
- confidence is a win probability, performance probability, or medical risk
  probability
- ranking is valid without explanations and limitations

Recommendation wording must avoid command language that removes the user's
judgment.

## 14. Governance Standards

Recommendation Engine V1 is governed by the same trust-first standards as the
Availability Engine.

Governance requirements:

- Policy must precede implementation.
- Recommendation behavior must be deterministic.
- Category assignment must be explainable and auditable.
- Fail-closed behavior is required when trusted data is insufficient.
- Implementation, when authorized, must be centralized rather than duplicated
  across routes or UI components.
- Thresholds, category rules, and refusal rules must be versioned or documented
  when changed.
- Any future behavior tests must verify policy boundaries, explanation presence,
  freshness handling, confidence handling, and refusal conditions.
- Reports or audits must distinguish policy validation from live product
  authorization.
- Category wording must not change silently.

No future implementation may bypass this policy by presenting recommendation
language as availability, methodology, or dashboard copy.

## 15. Future Expansion Boundaries

Future work may extend Recommendation Engine policy, but expansion requires a
separate documented decision before implementation.

Out-of-scope until separately governed:

- role-aware recommendations
- usage simulation
- matchup-aware recommendations
- rest-of-series planning
- postseason-specific policy
- trade, roster, or transaction guidance
- injury/news feed integration
- private or paid data integrations
- performance projection models
- public API recommendation contracts
- frontend recommendation surfaces

Future modules may consume availability classifications only if they preserve
the same trust rules: deterministic behavior, visible explanations, visible
limitations, freshness transparency, confidence disclosure, and fail-closed
refusal when trusted data is insufficient.
