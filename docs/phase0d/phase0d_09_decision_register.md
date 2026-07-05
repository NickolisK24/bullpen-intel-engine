# Phase 0D-09 Decision Register

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
