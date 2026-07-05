# Phase 0D Decision Register

## Purpose

This register records Phase 0D-09 exit decisions. It classifies unresolved
subjects from the Phase 0D family branches without changing runtime behavior,
posture, evidence emission, public surfaces, or schema.

## Resolved Decisions

### Reliever/Starter Partition

State: RESOLVED-REFUSED for V4.

Decision:

- `team_active_reliever_count` stays contract-locked UNKNOWN.
- BaseballOS V4 does not create a reliever/starter roster partition.
- Unlock requires a future foundation-level authority decision outside V4
  scope.

### Base-State / Runners At Entry

State: RESOLVED-RATIFIED.

Decision:

- Boxscore-only inherited attribution is accepted for V4.
- The 0C-style base-state addendum is optional future foundation work, not a V4
  exit requirement.

Capability cap:

- no per-inning clean/traffic granularity
- no bequeathed traffic
- no entry-band traffic axis
- this cap remains until a future base-state addendum is deliberately reopened

### Bequeathed Traffic

State: DEFERRED.

Decision:

- Bequeathed traffic is chained to the future base-state addendum.
- It is never derived from successor-inherited-runner joins.

### Handedness Exposure

State: DEFERRED.

Decision:

- Handedness exposure is not stored.
- Unlock requires a scoped foundation addendum sourcing batter side from the
  Stats API people endpoint.
- That addendum inherits legal posture and correction policy review.
- An evidence-design branch must follow any approved foundation addendum.
- Handedness is never proxied.

### Opener/Bulk Patterns

State: DEFERRED permanently as a label.

Decision:

- Opener/bulk labels are intent-laden and stay out of Phase 0D.
- Underlying facts remain independently citable.
- Any future return must use a registered deterministic definition with
  intent-free naming.

### Team-Level Entry-Band Aggregation

State: REJECTED while the posture lock stands.

Decision:

- No team-level aggregation over `appearance_entry_band` is built.
- No team-level aggregation over `pitcher_entry_band_distribution` is built.
- None is permitted while the 0D-07 posture lock stands.

### Pressure/Leverage Vocabulary

State: REJECTED permanently for rule ids, evidence types, claims, and public
copy.

Decision:

- Roadmap references are historical context only.
- Registered rule ids, evidence types, claims, and public copy must use
  approved Phase 0D language instead.

### Appearance Team-Attribution Method

State: RATIFIED as binding precedent.

Decision:

- Team attribution uses dated roster snapshot authority.
- Play-by-play fielding-team data is corroboration only.
- Opponent strings are never attribution authority.
- Attribution failures exclude and cite the failed inputs.

### Contributor-Set Vs Roster-Reliever Distinction

State: RATIFIED.

Decision:

- The denominator disclaimer is a public-language precondition bound to every
  composition read.
- Required disclaimer:
  `This set is appearance-evidenced; the team's roster reliever count remains unknown by design.`

### 0D-04 Emission-Policy Coupling

State: RATIFIED.

Decision:

- `team_relief_outing_context_mix` depends on the 0D-04 emission policy.
- After the 0D-04 family ran for a window date, absence of `outing_clean`,
  `outing_traffic`, and `outing_context_unknown` means provably neither.
- Any 0D-04 policy change is a breaking change requiring a coordinated version
  bump of `team_relief_outing_context_mix`.
- Existing pin test:
  `test_rule5_emission_policy_pin_provably_neither_bucket`.

## Deferred And Rejected Scope

DEFERRED and REJECTED are decision-register states only. No registered Phase 0D
rule carries either classification.
