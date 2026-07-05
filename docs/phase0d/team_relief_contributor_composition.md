# Phase 0D-08 - Team Relief Contributor Composition

## Purpose

This family composes already stored internal evidence into team-level
observations over the recent relief contributor set. It remains
`internal_only` and does not create public product language, public API fields,
UI surfaces, or a roster partition.

Roadmap note: this family implements the master plan's "team bullpen structure
composition" item as internal-only team relief contributor composition.

## Denominator

Every rule uses the recent relief contributor set: pitchers with at least one
finality-certified relief appearance attributed to the team in the trailing 14
days.

Every Rule 1 claim carries this denominator disclaimer:

`This set is appearance-evidenced; the team's roster reliever count remains unknown by design.`

`team_active_reliever_count` remains untouched and UNKNOWN by contract.

## Attribution

Appearance team attribution uses same-date roster snapshot authority:

- read the `roster_status_snapshots` row where `pitcher_id` matches and
  `snapshot_date == game_date`
- use that row's `team_id`
- use play-by-play `fielding_team_id` only as corroboration when events exist
- if the same-date roster snapshot is missing, exclude the appearance with
  `attribution_unknown`
- if roster snapshot authority and play-by-play corroboration disagree, exclude
  the appearance with `attribution_conflict`, cite both sides, and dead-letter
  `composition_attribution_conflict`
- never attribute by opponent strings, current pitcher team, nearest snapshot,
  or guessing

## Rules

All six rules are version 1, `internal_only`, subject type `team`, and
product-date scoped.

| Rule id | Evidence type | Definition |
| --- | --- | --- |
| `team_relief_contributor_basis` | `team_relief_contributor_basis` | 14-day basis set, current roster relationship facts, exclusions, coverage lower-bound state, attribution method, and denominator disclaimer. |
| `team_relief_rest_distribution` | `team_relief_rest_distribution` | Basis-set member counts by stored `workload_days_of_rest` bucket: 0, 1, 2, 3+, and unknown. |
| `team_relief_density_usage_count` | `team_relief_density_usage_count` | Basis-set member counts for stored `usage_back_to_back`, `usage_three_in_four`, and `usage_four_in_six` objects, keeping present, absent, and unassessable states separate. |
| `team_relief_workload_concentration` | `team_relief_workload_concentration` | 7-day and 14-day attributed relief out counts, the largest contributor and three largest contributors by cited outs, and shares only when every window appearance is attributed and complete. |
| `team_relief_outing_context_mix` | `team_relief_outing_context_mix` | 7-day counts of attributed appearances with stored `outing_clean`, `outing_traffic`, `outing_context_unknown`, and provably-neither outcomes. |
| `team_relief_finish_spread` | `team_relief_finish_spread` | 14-day distinct basis-member counts for games finished, save opportunity, save, hold, and blown save from per-appearance `appearance_finish_context` objects only. |

## Build Order

The builder runs in two stages:

1. Build Rule 1 basis objects for each team/date.
2. Build Rules 2-6 from the refreshed basis.

Every downstream object cites the basis object with
`citation_role='composition_basis'`.

## Counts And Shares

Counts can degrade to cited lower bounds when attribution exclusions or slate
coverage gaps exist. Shares are emitted only when every appearance in the
window is attributed and complete. Any exclusion makes shares UNKNOWN with
`share_exclusion_present`.

Composition rules enumerate complete sets. Floors belong to pattern
observations, not enumerations.

## Source Consumption

- Rule 2 consumes stored `workload_days_of_rest` evidence.
- Rule 3 consumes stored 0D-02 density pattern evidence and preserves absence
  as false.
- Rule 4 computes only attributed relief out sums locally and cross-checks the
  stored `team_bullpen_outs_window` object.
- Rule 5 consumes stored 0D-04 outing context objects only after the source
  family ran for every window date. After that gate passes, absence of all
  three outing context objects is provably neither.
- Rule 6 consumes only per-appearance `appearance_finish_context` objects.

Locked entry-band objects and floored 0D-07 observation objects are not inputs.

## Reason Codes

- `attribution_unknown`
- `attribution_conflict`
- `appearance_role_unknown`
- `incomplete_slate_day_in_window`
- `basis_lower_bound`
- `member_evidence_unavailable`
- `member_evidence_conflict`
- `outing_family_coverage_gap`
- `concentration_corroboration_mismatch`
- `share_exclusion_present`
- `roster_membership_unknown`
- `source_family_not_ready`

## Guardrails

This branch adds no:

- reliever/starter partition
- roster role claim
- team quality label
- team depth label
- team availability label
- team trust label
- single team state, score, grade, color, or cross-team comparison
- locked-band aggregation
- handedness, opener/bulk, base-state, or bequeathed-traffic work
- public product surface, frontend UI, public API, serializer, dashboard,
  board, or What Changed behavior

Claim templates, rendered claims, fixtures, and evidence objects are linted
against the 0D-08 forbidden vocabulary categories. Literal negative examples
live only in tests that prove rejection.
