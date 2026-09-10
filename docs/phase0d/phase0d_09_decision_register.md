# Phase 0D-09 Decision Register

Status: superseded by `docs/phase0d/decision_register.md` for resolved 0D-09
exit decisions. This file is retained as the pre-exit carry-forward register.

## Purpose

This register carries forward decisions that Phase 0D family branches identify
but do not resolve. Phase 0D-09 confirms or rejects public-candidate posture and
integration paths; it does not silently widen earlier family scope.

## 0D-07 Carried Decisions

### Handedness Exposure

Current decision:

- no handedness-exposure rule is registered in 0D-07
- no batter handedness exists in current stored BaseballOS data
- no 0D-07 object infers batter side from names, event text, pitch data, or
  outside knowledge

Possible future path:

- a scoped foundation addendum could evaluate MLB Stats API people endpoint
  coverage and legality before any handedness evidence is considered

0D-09 decision needed:

- confirm no handedness exposure leaves Phase 0D, or authorize a separate
  future foundation addendum

### Opener And Bulk Patterns

Current decision:

- no opener rule is registered in 0D-07
- no bulk rule is registered in 0D-07
- no label is inferred from appearance order, innings, or games started

0D-09 decision needed:

- keep opener/bulk patterns deferred, or define a future source-backed
  foundation with explicit limits

### Permanently Internal Entry-Context Band Rules

Current decision:

- `appearance_entry_band` is permanently internal
- `pitcher_entry_band_distribution` is permanently internal
- 0D-07 enforces the lock at registration and emitted-object levels

0D-09 decision needed:

- confirm the lock; do not revisit public-candidate status for these two rules

### Observation Classification Preconditions

Rules eligible for later review only if all preconditions remain intact:

- `appearance_finish_context`
- `pitcher_save_hold_window`
- `pitcher_finish_usage_observation`
- `pitcher_multi_inning_usage_observation`
- `pitcher_first_reliever_usage_observation`

Preconditions:

- observation grammar only
- floors intact
- mechanical band names only when referenced
- no composed summary labels
- no quality label
- no prediction label
- no availability label
- no manager-intent label

0D-09 decision needed:

- decide whether any observation remains internal or can move to
  public-candidate review with these constraints still enforced

### Reliever/Starter Partition

Current decision:

- 0D-07 does not create a reliever/starter partition
- `team_active_reliever_count` remains the 0D-06 UNKNOWN contract
- usage observations do not become roster membership or roster role authority

0D-09 decision needed:

- keep the partition unavailable, or require a future authorized source before
  any roster partition can exist

## 0D-08 Carried Decisions

### Team-Level Band Aggregation

Current decision:

- no team-level aggregation over `appearance_entry_band` is registered in 0D-08
- no team-level aggregation over `pitcher_entry_band_distribution` is registered
  in 0D-08
- lock inheritance remains intact for both rules

0D-09 decision needed:

- confirm the lock inheritance remains intact, or require a separately scoped
  future branch before any team-level band aggregation can exist

### Appearance Team Attribution

Current decision:

- same-date roster snapshot authority is the mandatory precedent for appearance
  team attribution
- play-by-play fielding team is corroboration only when events exist
- snapshot/play-by-play disagreement is excluded as `attribution_conflict`
- missing same-date snapshot authority is excluded as `attribution_unknown`
- opponent strings are never attribution authority

0D-09 decision needed:

- carry this attribution method forward for any future family that composes
  team-level appearance evidence

### Basis Disclaimer

Current decision:

- Rule 1 basis claims must state that the set is appearance-evidenced
- Rule 1 basis claims must state that the team's roster reliever count remains
  unknown by design
- `team_active_reliever_count` remains UNKNOWN by contract

0D-09 decision needed:

- keep the disclaimer as a public-language precondition for any future
  composition read

### Rule 5 Emission Policy Dependency

Current decision:

- Rule 5 depends on the 0D-04 emission policy
- once the 0D-04 family ran for a window date, absence of `outing_clean`,
  `outing_traffic`, and `outing_context_unknown` is provably neither
- changing that 0D-04 policy is a breaking change for Rule 5

0D-09 decision needed:

- confirm this dependency before any public-candidate review of Rule 5

### Deferred Scope Reaffirmation

Current decision:

- the reliever/starter partition remains locked
- handedness remains deferred
- opener/bulk remains deferred
- base-state remains deferred
- bequeathed traffic remains deferred

0D-09 decision needed:

- keep these items outside Phase 0D exit unless a separate authorized source
  foundation is approved
