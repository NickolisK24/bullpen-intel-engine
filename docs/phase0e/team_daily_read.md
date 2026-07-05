# Phase 0E-03 Team Daily Read

## Scope

This branch adds `team_daily_read` v1 as the second production composed read.

It is internal only. No public payload, API, UI, board, dashboard snapshot, What
Changed, Tonight, frontend, copy, label, or methodology behavior changes in this
branch. The Phase 0B legal/source gate blocks all public surfacing.

Additional guardrail: 0E-03 must not add new evidence rules, migrations,
read-citation tables, team states, colors, tiers, scores, grades, ranks, labels,
team quality/depth language, availability inference, health inference, role
assignment, manager intent, pressure/leverage language, or public behavior
changes.

## Definition

"The team daily read bundles, for one team on one product day, the stored facts
describing its recent relief context: the recent relief contributor composition
(an appearance-evidenced set — not the team's roster reliever count, which
remains unknown by design), how much relief work the team has had to cover,
public roster and transaction facts, calendar facts where present, and a map of
how complete the underlying data is. Relief work is defined per game as pitching
by pitchers who did not start that game. Every component cites stored evidence
objects. The read deliberately concludes nothing: it assigns no team state,
quality, depth, trust, availability, readiness, or prediction, carries no score,
grade, rank, color, or tier, and degrades honestly when evidence is missing,
stale, partial, contradictory, or below threshold."

Classification: `INTERNAL_ONLY_FOR_NOW`.

## Population

Subject: `team_day`.

Population: every team present in the current roster snapshot authority for the
product date. The builder uses distinct `team_id` values from each team's latest
`roster_status_snapshots.snapshot_date <= D`.

Every snapshot-present team gets a read every product day, including off days.
Missing required component evidence degrades the read; it never deletes the team
read.

## Component Contract

| Component | Required | Allowed evidence types | Degradation and limitations |
| --- | --- | --- | --- |
| `contributor_composition_component` | yes | `team_relief_contributor_basis`, `team_relief_rest_distribution`, `team_relief_density_usage_count`, `team_relief_workload_concentration`, `team_relief_outing_context_mix`, `team_relief_finish_spread` | Missing basis makes the component unknown. Lower-bound basis passes through partial. Conflict evidence passes through conflict. The denominator disclaimer is preserved verbatim on every build. |
| `exposure_component` | yes | `team_bullpen_share_of_outs`, `team_bullpen_outs_window`, `team_bullpen_pitches_window`, `team_reliever_appearances_window`, `team_short_start_count_window` | Lower-bound and unknown facts pass through from cited evidence. The appearances-not-distinct-arms limitation rides cited counts. |
| `calendar_component` | no | `team_consecutive_game_days`, `team_doubleheader_today`, `team_recent_doubleheader`, `team_off_day_yesterday`, `team_off_day_tomorrow`, `team_calendar_density` | Calendar facts where present. Absence on off days is normal and never degrades the read because this component is optional. |
| `roster_churn_component` | yes | `team_active_pitcher_census`, `team_public_il_count`, `team_transaction_churn_window`, `team_transaction_category_counts_window`, `team_option_recall_churn`, `team_roster_movement_churn`, `team_depth_delta_daily`, `team_roster_changes_explained`, `team_roster_changes_unexplained` | Missing or stale snapshot facts pass through unknown. Transaction coverage gaps pass through partial. Unexplained changes are stored facts, not defects. |
| `slate_data_completeness_component` | yes | `inherited_traffic_fact` for the `outing_context_unknown` rule when present; citations optional | Always complete. Lists component states and reason codes, source-family coverage categories, slate coverage, and transaction coverage. No numeric confidence, percentage, grade, weight, or ranking. |

Required component completeness controls read completeness by the 0E-01 weakest
required-component rule. The optional calendar component never degrades the read.

## Disclaimer Preservation

The contributor component must carry this text verbatim in component limitations:

`This set is appearance-evidenced; the team's roster reliever count remains unknown by design.`

## Member-Read Rollup Deferral

Member-read rollup is deferred to Phase 0E-05. 0E-03 does not extend the 0E-01
contract. Components cite `evidence_objects` only through
`composed_read_evidence_citations`; no component cites a composed read, and no
read-citation table, foreign key, or `allowed_read_types` registry support is
added.

The rollup question belongs on the 0E-05 agenda alongside the headline-state
decision.

## Wording Note

The read type is `team_daily_read`. Definitions use mechanical relief wording
anchored to the per-game basis: "Relief work is defined per game as pitching by
pitchers who did not start that game." The roster reliever count remains unknown
by design.

## Sync Integration

`PHASE0E_READ_BUILD` controls both reliever and team read builds. Team reads
build after reliever reads. A team-read failure is fail-soft, records a dead
letter, and does not roll back committed reliever reads.

Manual build:

```bash
python backend/scripts/build_composed_reads.py --date YYYY-MM-DD
```

## Exclusions

The read does not consume:

- `appearance_entry_band`
- `pitcher_entry_band_distribution`
- `team_active_reliever_count`
- pitcher-subject evidence types, except the inherited completeness device when
  present
- diagnostics not listed in the component table
- composed reads

This branch adds no evidence rule, migration, read-citation mechanism,
team-state label, score, grade, rank, color, tier, public payload, API, UI, copy,
or methodology surface.
