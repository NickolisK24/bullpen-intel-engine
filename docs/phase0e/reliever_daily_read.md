# Phase 0E-02 Reliever Daily Read

## Scope

This branch adds the first production composed read: `reliever_daily_read` v1.

The read is internal only. It creates no public payload, API field, UI, board
output, snapshot output, What Changed item, Tonight item, frontend module, copy,
label, or methodology change. The Phase 0B legal/source gate continues to block
all public surfacing.

## Definition

"The reliever daily read bundles, for one pitcher on one product day, the stored
facts a bullpen reader needs: recent workload counts, rest and usage-density
facts, the most recent relief outing's context, finishing/situational facts
where present, public roster and IL facts, eligible usage observations, and a
map of how complete the underlying data is. Every component cites stored
evidence objects. The read deliberately concludes nothing: it assigns no
availability, readiness, health, role, quality, or prediction, carries no single
state, score, grade, or label, and degrades honestly - components with missing,
stale, partial, contradictory, or below-threshold evidence say so instead of
guessing."

Classification: `INTERNAL_ONLY_FOR_NOW`.

## Population

Subject: `pitcher_day`.

Population: pitchers with at least one stored final game-log row where:

- `game_date` is in the product-date window from D-29 through D
- `games_started == 0`

Rows with `games_started IS NULL` are excluded. Starter-only rows are excluded.
Rows before D-29 are excluded.

Cold-arm gap: a rostered pitcher with no relief-scoped appearance in the
trailing window receives no read in this branch. QA review of that gap is
deferred to Phase 0E-05.

## Component Contract

The 0E-01 registry validates evidence-family types. The reliever daily read
builder enforces the exact rule IDs listed below before composing each
component.

| Component | Required | Registry evidence families | Builder rule IDs |
| --- | --- | --- | --- |
| `workload_component` | yes | `workload_recovery_fact` | `workload_window_appearances`, `workload_window_pitches`, `workload_window_outs`, `workload_window_batters_faced`, `outing_multi_inning`, `outing_high_pitch` |
| `rest_component` | yes | `workload_recovery_fact` | `workload_last_final_appearance`, `workload_days_of_rest`, `usage_back_to_back`, `usage_three_in_four`, `usage_four_in_six`, `appearance_short_rest` |
| `recent_outing_component` | yes | `appearance_context_fact`, `inherited_traffic_fact` | `appearance_entry_context`, `appearance_exit_context`, `appearance_order_in_game`, `appearance_innings_spanned`, `appearance_game_phase`, `appearance_inherited_runners`, `appearance_inherited_runners_scored`, `appearance_inherited_traffic_outcome`, `outing_clean`, `outing_traffic`, `outing_context_unknown` |
| `situational_component` | no | `appearance_finish_context`, `pitcher_save_hold_window` | `appearance_finish_context`, `pitcher_save_hold_window` |
| `roster_il_context` | yes | `pitcher_il_placement_context`, `pitcher_il_activation_context`, `pitcher_roster_membership_context` | `pitcher_il_placement_context`, `pitcher_il_activation_context`, `pitcher_roster_membership_context` |
| `usage_observation_component` | no | `pitcher_finish_usage_observation`, `pitcher_multi_inning_usage_observation`, `pitcher_first_reliever_usage_observation` | same as registry families |
| `data_completeness_component` | yes | `inherited_traffic_fact` | `outing_context_unknown` when present; zero-citation component is legal |

Required component completeness controls read completeness by the 0E-01 weakest
required-component rule. Optional components never degrade the read.

## Roster Membership Rule

0E-02 adds `pitcher_roster_membership_context` v1 as a read-scoped evidence rule.
It exists only because it is directly necessary for the reliever daily read. It
is not a roster redesign, public label change, team census rewrite, partition,
or model.

Complete evidence requires a same-day `roster_status_snapshots` row. Older
snapshot rows produce `UNKNOWN` with `snapshot_stale`. Missing snapshot rows
produce `UNKNOWN` with `snapshot_missing`.

Allowed rendered forms:

- `On the active roster per the <date> snapshot (team <id>).`
- `Not on the active roster per the <date> snapshot.`
- `Roster membership unknown: <reason>.`

Classification: `PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE` as eligibility
metadata only. Stored evidence posture remains `internal_only`.

## Data Completeness

`data_completeness_component` is synthesized last. It is always `complete` and
non-scoring. It lists:

- every required component state
- component reason codes when present
- source-family coverage categories
- slate/window coverage validity as inherited from cited component states

It carries no number, percentage, grade, weight, rollup, or public label.
Citation rows are optional. The zero-citation path is asserted by tests.

## Recompute

Superseding or invalidating a cited evidence object marks only dependent
`reliever_daily_read` rows `recompute_needed` through the 0E-01 read citation
table. Rebuilding a marked date supersedes prior rows by `read_key`.

## Sync Integration

Daily sync and postgame refresh run the read-build stage after Phase 0D evidence
builds. The stage is fail-soft and records dead letters on failure.

Operator switch:

- `PHASE0E_READ_BUILD=false` skips composed-read builds.

Manual build:

```bash
python backend/scripts/build_composed_reads.py --date YYYY-MM-DD
```

## Exclusions

The read does not consume:

- `appearance_entry_band`
- `pitcher_entry_band_distribution`
- team-subject evidence families
- diagnostics that are not listed in the component table

This branch does not implement any team-day read, legacy reconciliation audit,
QA harness, headline decision, legal paper, roster redesign, census rewrite,
partition, public payload, API, UI, label, copy, methodology surface, score,
rank, grade, or public read state.
