# Phase 0D-05 - Starter Exposure And Calendar Density Evidence

## Scope

This document defines the internal-only team-level starter-exposure and
calendar-density evidence family for Phase 0D-05.

The family uses stored `team_game_pitching_splits` rows as the authority for
team-game starter, reliever, and calendar context facts. It writes through the
existing Phase 0D evidence contract and the existing `evidence_objects` and
`evidence_citations` tables. No new evidence table is expected.

This branch adds no public API, payload, UI, frontend, or public copy behavior.

## Registered Rules

All rules are version `v1`, default to `internal_only`, and use
`subject_type=team` with the MLB/team integer id as `subject_id`.

1. `team_bullpen_share_of_outs v1`
2. `team_bullpen_outs_window v1`
3. `team_bullpen_pitches_window v1`
4. `team_reliever_appearances_window v1`
5. `team_short_start_count_window v1`
6. `team_consecutive_game_days v1`
7. `team_doubleheader_today v1`
8. `team_recent_doubleheader v1`
9. `team_off_day_yesterday v1`
10. `team_off_day_tomorrow v1`
11. `team_calendar_density v1`

### RULE 1 - team_bullpen_share_of_outs v1

Definition:
Of all outs the team's pitchers recorded over the trailing 7-day and 14-day
windows ending on the evidence date, the share recorded by relievers:

`sum of bullpen_outs_recorded / sum of total_team_outs`

A share is stated only when:

- the window is team-valid
- every included split row is complete
- `bullpen_outs_recorded` is known for every included game
- `total_team_outs` is known for every included game
- denominator is nonzero

A window with any missing, partial, unknown, excluded, or unsafe component
yields `UNKNOWN`. Ratios never render as lower-bound partials.

Claim states:

- bullpen outs sum
- total team outs sum
- calculated share
- window length
- evidence date

This describes recent distribution of work. It carries no pressure, fatigue,
readiness, availability, or quality meaning.

Thresholds:

- `window_days`: 7 and 14

### RULE 2 - team_bullpen_outs_window v1

Definition:
Total outs recorded by the team's relievers across the team's final games in
the trailing 7-day and 14-day windows.

Complete when:

- the window is team-valid
- every included split row is complete
- `bullpen_outs_recorded` is known

When split rows are missing, partial, unknown, or unsupported by the
readiness/coverage framework:

- state the total as a lower-bound `PARTIAL` over complete rows only
- cite excluded games or rows where known
- name the reason

Thresholds:

- `window_days`: 7 and 14

### RULE 3 - team_bullpen_pitches_window v1

Definition:
Total pitches thrown by the team's relievers across the trailing 7-day and
14-day windows.

State a total only when:

- the window is team-valid
- every included split row is complete
- `bullpen_pitches_thrown` is known for every included game

If any bullpen pitch component is unknown:

- emit `UNKNOWN`
- cite known-pitch game count
- cite known-value subtotal
- label the subtotal as a subtotal of known values
- never render known subtotal as the total

Thresholds:

- `window_days`: 7 and 14

### RULE 4 - team_reliever_appearances_window v1

Definition:
The sum of per-game `relievers_used_count` across the team's final games in the
trailing 7-day and 14-day windows.

This is reliever appearances, not distinct arms. The same reliever appearing on
consecutive days counts each time. Distinct-arm counting belongs to later team
structure composition, not this rule.

When split rows are missing, partial, or unknown:

- emit lower-bound `PARTIAL` over complete rows
- cite exclusions

Required limitation on every object:
`Relievers used is an appearance count, not a distinct-arm count; the same pitcher can count once per game.`

Thresholds:

- `window_days`: 7 and 14

### RULE 5 - team_short_start_count_window v1

Definition:
How many of the team's final games in the trailing 7-day and 14-day windows had
a start shorter than five innings.

Short start threshold:

- `starter_outs_recorded <= 14`

A five-inning start records 15 outs. A short start is therefore an identified
starter recording 14 outs or fewer.

Unknown starter identity or unknown starter outs:

- exclude the game from the count
- cite the exclusion
- emit lower-bound `PARTIAL` when applicable

This is descriptive, not a pressure/fatigue/readiness conclusion.

Claim states:

- count
- threshold
- excluded games if any
- window length

Thresholds:

- `window_days`: 7 and 14
- `short_start_max_outs`: 14

### RULE 6 - team_consecutive_game_days v1

Definition:
The team's count of consecutive game days entering the evidence date, from the
stored calendar context of that date's final game or games.

Use:

- `consecutive_game_day_count_entering`

Emit for teams with a final game on the evidence date.

Doubleheader games share one value.

Unknown or stale calendar context emits `UNKNOWN` with
`calendar_context_unavailable` or `calendar_context_stale`.

Do not recompute streak locally.

### RULE 7 - team_doubleheader_today v1

Definition:
The team played two or more final games on the evidence date, based on per-game
split rows carrying doubleheader flag/code and game numbers.

Per-game rows are never merged into a day aggregate.

Claim cites each game.

Emit when true, or `UNKNOWN` when rows exist but calendar context cannot
confirm the doubleheader relationship.

### RULE 8 - team_recent_doubleheader v1

Definition:
The team played a doubleheader on at least one day within the trailing 7-day
window ending on the evidence date.

Claim cites doubleheader day or days and games.

Emit when present, or `UNKNOWN` when window rows needed to decide are missing
or calendar context is unknown.

Thresholds:

- `window_days`: 7

### RULE 9 - team_off_day_yesterday v1

Definition:
The team had no game on the day before the evidence date, from the stored
`off_day_before` calendar fact of the evidence date's final game or games.

This is a completed-schedule fact.

Emit when true, or `UNKNOWN` when calendar context is unknown or stale.

### RULE 10 - team_off_day_tomorrow v1

Definition:
No game appears on the team's schedule for the day after the evidence date,
from the stored `off_day_after` calendar fact.

This is a schedule fact as of the last schedule ingestion. It predicts nothing
about usage.

Every object carries this limitation:
`Schedule fact as of last ingestion; postponements, makeups, and rescheduling can change tomorrow's schedule.`

### RULE 11 - team_calendar_density v1

Definition:
A bundle of counted calendar facts for the team over the trailing 7-day window
ending on the evidence date:

- final games played
- distinct game days
- off days
- doubleheader days
- consecutive game-day streak entering the evidence date

Each component is cited to stored rows. Components are independently
degradable.

Do not combine these into a single number, score, grade, label, or rank.

Thresholds:

- `window_days`: 7

## Authoritative Fields

| Area | Authoritative fields |
| --- | --- |
| Team identity | `team_id`, `mlb_game_pk`, `game_date` |
| Starter exposure | `starter_identity_status`, `starter_outs_recorded` |
| Reliever exposure | `bullpen_outs_recorded`, `bullpen_pitches_thrown`, `relievers_used_count`, `total_team_outs` |
| Split validity | `split_completeness_status`, `split_reason_codes`, provenance fields |
| Calendar context | `doubleheader_flag`, `doubleheader_code`, `game_number`, `off_day_before`, `off_day_after`, `consecutive_game_day_count_entering`, `postponed_or_makeup_indicator`, `suspended_resumed_linkage_status`, `calendar_context_status` |

Source readiness and slate coverage remain consumer gates and window-boundary
support. The evidence family does not use `game_logs`, raw play-by-play, or
play-by-play-derived base state as inputs.

## Product-Day And Window Behavior

Windows are inclusive of the evidence date:

- 7-day window: `[D-6, D]`
- 14-day window: `[D-13, D]`

Window validity is team-scoped, not league-scoped. This differs from 0D-02
pitcher workload windows, which reason about pitcher rows against league slate
coverage. 0D-05 sums team-game split rows for one team and degrades from the
stored split/calendar status on those team rows.

Doubleheaders:

- per-game split rows are summed individually
- never merge into one row for game counts
- doubleheader day counts once for distinct-game-day and streak facts
- doubleheader day counts twice for game counts if two games were played
- cite both games

Suspended/resumed games:

- count once on their 0C-attributed product day
- ambiguous linkage degrades validity-requiring metrics with
  `ambiguous_resumed_game_in_window`
- resolved linkage carries the resumed-game limitation

Off days:

- lower calendar-density counts
- drive RULES 9 and 10 from stored calendar fields

Unknown starter identity or unknown starter outs:

- excluded from short-start count
- cited as excluded input
- lower-bound partial where applicable

Unknown bullpen outs or total outs:

- fail closed to `UNKNOWN` for the affected metric
- use `bullpen_component_unknown`

Unknown bullpen pitches:

- pitch total is `UNKNOWN`
- known-value subtotal is labeled as a subtotal, never as a total

Calendar context missing or stale:

- RULES 6-11 degrade to `UNKNOWN`
- use `calendar_context_unavailable` or `calendar_context_stale`
- do not recompute schedule math locally

## Counts-Vs-Ratios Degradation Grammar

Counts may emit lower-bound `PARTIAL` when rows are missing, partial, unknown,
or excluded. Rendered claims must say "at least". Excluded games/rows must be
cited when known and listed in the trace.

Ratios never emit lower-bound partials. If any required component is missing,
partial, unknown, or excluded, emit `UNKNOWN` and do not render a percentage.

Pitch totals are `UNKNOWN` when any pitch component is NULL. Known count and
known-value subtotal may render only as subtotal evidence.

Calendar density does not create a composite score or label.

## Expected-Team-Game And Missing Split Row Limitation

The current codebase exposes global source-readiness counts for expected
team-game split rows, but it does not expose a safe team-scoped expected final
team-game set for a product-day window that 0D-05 can consume without inventing
a new coverage layer.

Therefore this branch does not reconstruct missing team games from `game_logs`,
play-by-play rows, or ad hoc schedule queries. It computes over available split
rows and degrades only when existing split/readiness/calendar fields identify
incompleteness.

Missing expected team-game detection is deferred to 0D-09 or a future
source-coverage refinement.

## Reason Codes

- `split_row_missing`
- `split_row_partial`
- `split_row_unknown`
- `starter_identity_unknown`
- `starter_outs_unknown`
- `bullpen_component_unknown`
- `unknown_pitch_count_in_window`
- `share_denominator_unavailable`
- `ambiguous_resumed_game_in_window`
- `calendar_context_unavailable`
- `calendar_context_stale`
- `window_precedes_coverage_history`
- `no_final_game_on_date`
- `source_family_not_ready`

## Citation Requirements

Every included split row is cited with exact fields used.

Excluded rows are cited with `citation_role=excluded_input` and their status.

Calendar rules cite split rows carrying the calendar facts.

No object emits without split-row citations in this branch.

## Computation Trace

Trace payloads record:

- game rows consulted
- inclusion/exclusion decisions
- reasons for exclusions
- per-window arithmetic
- counts-versus-ratio degradation choice
- pitch subtotal logic
- calendar field reads
- doubleheader handling
- suspended/resumed handling
- missing expected team-game support decision

A reviewer should be able to replay the derivation from the trace alone.

## Explicit Non-Claims

This family makes no claims about:

- pressure or leverage
- fatigue, readiness, or availability
- opener/bulk labels
- starter quality judgments
- rotation quality judgments
- prediction of tonight/tomorrow usage
- travel inference
- roster/IL/churn
- role usage observations
- team bullpen structure composition
- distinct-arm counting
- public product surfaces
- frontend UI
- public API or copy changes
- score, rank, or grade
- league-comparison framing
- pitch-level or Statcast data

## Sync And Recompute

The existing fail-soft Phase 0D evidence stage builds this family after 0D-04
when `PHASE0D_EVIDENCE_BUILD` is enabled. Exceptions are dead-lettered and
logged while sync continues.

Corrections or re-derivations of cited `team_game_pitching_splits` rows can
mark dependent evidence through `mark_dependent_evidence_for_recompute`.
Rebuilds refresh only marked evidence keys and preserve prior rendered-claim
provenance in the computation trace.
